from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Protocol, TypeVar
from uuid import UUID

import httpx
from postgrest import APIError
from postgrest.base_request_builder import APIResponse
from pydantic import BaseModel, ValidationError
from supabase import Client

from app.errors import (
    DuplicateProduct,
    InvalidCheckout,
    OrderNotFound,
    ProductNotFound,
    ShopError,
)
from app.models import CustomerRead, OrderCreate, OrderRead, OrderStatus, ProductRead


PAGE_SIZE = 100
ORDER_SELECT = "*,customer:customers(*),items:order_items(*)"
ReadModel = TypeVar("ReadModel", bound=BaseModel)


class ShopRepository(Protocol):
    def check_connection(self) -> None: ...
    def list_products(self, search: str | None = None) -> list[ProductRead]: ...
    def list_customers(self) -> list[CustomerRead]: ...
    def list_orders(self, customer_id: UUID | None = None) -> list[OrderRead]: ...
    def create_order(self, payload: OrderCreate) -> OrderRead: ...
    def update_order_status(self, order_id: UUID, status: OrderStatus) -> OrderRead: ...


@contextmanager
def database_errors(*, checkout: bool = False) -> Iterator[None]:
    try:
        yield
    except APIError as exc:
        if checkout:
            error = {
                "PT400": InvalidCheckout,
                "PT404": ProductNotFound,
                "PT409": DuplicateProduct,
            }.get(exc.code, ShopError)
            raise error() from None
        raise ShopError() from None
    except (httpx.RequestError, httpx.HTTPStatusError, ValidationError):
        raise ShopError() from None


class SupabaseShopRepository:
    def __init__(self, client: Client) -> None:
        self._client = client

    def check_connection(self) -> None:
        with database_errors():
            self._client.table("products").select("id").limit(1).execute()

    def _list_all(
        self, fetch: Callable[[int], APIResponse], model: type[ReadModel]
    ) -> list[ReadModel]:
        result: list[ReadModel] = []
        offset = 0
        with database_errors():
            while True:
                response = fetch(offset)
                rows = response.data
                if not rows:
                    return result
                result.extend(model.model_validate(row) for row in rows)
                # A server cap may be smaller than our requested range.
                offset += len(rows)
                if response.count is not None and offset >= response.count:
                    return result

    def list_products(self, search: str | None = None) -> list[ProductRead]:
        def fetch(offset: int) -> APIResponse:
            query = self._client.table("products").select("*", count="exact")
            if search is not None:
                literal = (
                    search.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                    .replace("*", "\\*")
                )
                query = query.ilike("name", f"%{literal}%")
            return query.order("name").order("id").range(offset, offset + PAGE_SIZE - 1).execute()

        return self._list_all(fetch, ProductRead)

    def list_customers(self) -> list[CustomerRead]:
        def fetch(offset: int) -> APIResponse:
            return (
                self._client.table("customers").select("*", count="exact")
                .order("created_at", desc=True).order("id")
                .range(offset, offset + PAGE_SIZE - 1).execute()
            )

        return self._list_all(fetch, CustomerRead)

    def list_orders(self, customer_id: UUID | None = None) -> list[OrderRead]:
        def fetch(offset: int) -> APIResponse:
            query = self._client.table("orders").select(ORDER_SELECT, count="exact")
            if customer_id is not None:
                query = query.eq("customer_id", str(customer_id))
            return (
                query.order("created_at", desc=True).order("id")
                .range(offset, offset + PAGE_SIZE - 1).execute()
            )

        return self._list_all(fetch, OrderRead)

    def create_order(self, payload: OrderCreate) -> OrderRead:
        with database_errors(checkout=True):
            response = self._client.rpc(
                "create_order",
                {
                    "p_customer_name": payload.customer_name,
                    "p_customer_email": payload.customer_email,
                    "p_customer_phone": payload.customer_phone,
                    "p_items": [item.model_dump(mode="json") for item in payload.items],
                },
            ).execute()
            return OrderRead.model_validate(response.data)

    def update_order_status(self, order_id: UUID, status: OrderStatus) -> OrderRead:
        with database_errors():
            response = (
                self._client.table("orders").update({"status": status})
                .eq("id", str(order_id)).select(ORDER_SELECT).execute()
            )
            if not response.data:
                raise OrderNotFound()
            return OrderRead.model_validate(response.data[0])
