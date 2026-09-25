from __future__ import annotations

from uuid import UUID

from app.models import CustomerRead, OrderCreate, OrderRead, OrderStatus, ProductRead
from app.repositories import ShopRepository


class OrderService:
    def __init__(self, repository: ShopRepository) -> None:
        self._repository = repository

    def list_products(self, search: str | None = None) -> list[ProductRead]:
        return self._repository.list_products(search=search)

    def list_customers(self) -> list[CustomerRead]:
        return self._repository.list_customers()

    def list_orders(self, customer_id: UUID | None = None) -> list[OrderRead]:
        return self._repository.list_orders(customer_id=customer_id)

    def create_order(self, payload: OrderCreate) -> OrderRead:
        return self._repository.create_order(payload)

    def update_order_status(self, order_id: UUID, status: OrderStatus) -> OrderRead:
        return self._repository.update_order_status(order_id, status)
