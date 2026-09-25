from contextlib import contextmanager
import json
from uuid import UUID

import httpx
import pytest
from supabase import ClientOptions, create_client

from app.errors import DuplicateProduct, InvalidCheckout, OrderNotFound, ProductNotFound, ShopError
from app.models import OrderCreate
from app.repositories import ORDER_SELECT, SupabaseShopRepository


PRODUCT_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"
ORDER_ID = "33333333-3333-3333-3333-333333333333"
ITEM_ID = "44444444-4444-4444-4444-444444444444"
DATE = "2026-01-01T00:00:00+00:00"


def customer_row():
    return {
        "id": CUSTOMER_ID, "name": "Ada", "email": "ada@example.com",
        "phone": None, "created_at": DATE,
    }


def order_row():
    return {
        "id": ORDER_ID, "customer_id": CUSTOMER_ID, "total_amount": 12.5,
        "status": "Pending", "created_at": DATE,
        "customer": customer_row(),
        "items": [
            {"id": ITEM_ID, "order_id": ORDER_ID, "product_id": PRODUCT_ID,
             "quantity": 1, "price": 12.5}
        ],
    }


def product_row(name="Red Bricks"):
    return {
        "id": PRODUCT_ID, "name": name, "description": "Demo", "price": 12.5,
        "stock": 5, "image_url": None,
    }


def response(rows, *, count=None, status=200):
    headers = {"Content-Range": f"0-{max(0, len(rows) - 1)}/{count}"} if count is not None else {}
    return httpx.Response(status, json=rows, headers=headers)


@contextmanager
def repository(handler):
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        client = create_client(
            "https://example.supabase.co", "fake-service-key",
            options=ClientOptions(
                httpx_client=transport, auto_refresh_token=False, persist_session=False
            ),
        )
        yield SupabaseShopRepository(client)


def test_products_search_escapes_wildcards_and_paginates_through_server_cap():
    seen = []

    def handler(request):
        assert request.url.path == "/rest/v1/products"
        assert request.url.params["order"] == "name.asc,id.asc"
        assert request.headers["Prefer"] == "count=exact"
        seen.append((request.url.params["offset"], request.url.params["limit"],
                     request.url.params.get("name")))
        start = int(request.url.params["offset"])
        return response([product_row()] if start < 3 else [], count=3)

    with repository(handler) as repo:
        result = repo.list_products(r"%_*\\")

    assert len(result) == 3
    assert [(offset, limit) for offset, limit, _ in seen] == [
        ("0", "100"), ("1", "100"), ("2", "100")
    ]
    assert all(pattern == r"ilike.%\%\_\*\\\\%" for _, _, pattern in seen)


def test_empty_products_and_customer_query():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/customers"):
            assert request.url.params["order"] == "created_at.desc,id.asc"
            return response([customer_row()], count=1)
        assert "name" not in request.url.params
        return response([], count=0)

    with repository(handler) as repo:
        assert repo.list_products() == []
        assert repo.list_customers()[0].email == "ada@example.com"
    assert paths == ["/rest/v1/products", "/rest/v1/customers"]


def test_orders_are_embedded_and_customer_filter_is_optional():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        assert request.url.path.endswith("/orders")
        assert request.url.params["select"] == ORDER_SELECT
        assert request.url.params["order"] == "created_at.desc,id.asc"
        return response([order_row()], count=1)

    with repository(handler) as repo:
        assert repo.list_orders()[0].items[0].price == 12.5
        assert repo.list_orders(UUID(CUSTOMER_ID))[0].customer.email == "ada@example.com"
    assert "customer_id" not in seen[0]
    assert seen[1]["customer_id"] == f"eq.{CUSTOMER_ID}"


def test_checkout_calls_one_rpc_with_validated_items_and_returns_order():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "POST"
        assert request.url.path == "/rest/v1/rpc/create_order"
        assert json.loads(request.content) == {
            "p_customer_name": "Ada", "p_customer_email": "ada@example.com",
            "p_customer_phone": None,
            "p_items": [{"product_id": PRODUCT_ID, "quantity": 1}],
        }
        return response(order_row())

    with repository(handler) as repo:
        result = repo.create_order(OrderCreate(
            customer_name="Ada", customer_email="ada@example.com",
            items=[{"product_id": PRODUCT_ID, "quantity": 1}],
        ))
    assert result.id == UUID(ORDER_ID)
    assert len(seen) == 1


@pytest.mark.parametrize(("code", "error"), [
    ("PT400", InvalidCheckout), ("PT404", ProductNotFound),
    ("PT409", DuplicateProduct), ("42501", ShopError),
])
def test_checkout_errors_are_mapped_without_exposing_database_details(code, error):
    def handler(request):
        return response({
            "code": code, "message": "private database details",
            "hint": None, "details": None,
        }, status=400)

    with repository(handler) as repo:
        with pytest.raises(error) as raised:
            repo.create_order(OrderCreate(
                customer_name="Ada", customer_email="ada@example.com",
                items=[{"product_id": PRODUCT_ID, "quantity": 1}],
            ))
    assert "private database details" not in str(raised.value)


def test_status_update_returns_embedded_order_and_missing_order_is_404():
    def handler(request):
        assert request.method == "PATCH"
        assert request.url.path == "/rest/v1/orders"
        assert request.url.params["id"] == f"eq.{ORDER_ID}"
        assert request.url.params["select"] == ORDER_SELECT
        assert json.loads(request.content) == {"status": "Completed"}
        return response([{**order_row(), "status": "Completed"}])

    with repository(handler) as repo:
        assert repo.update_order_status(UUID(ORDER_ID), "Completed").status == "Completed"
    with repository(lambda request: response([])) as repo:
        with pytest.raises(OrderNotFound):
            repo.update_order_status(UUID(ORDER_ID), "Completed")


def test_network_errors_return_safe_service_error():
    def handler(request):
        raise httpx.ReadTimeout("private connection details")

    with repository(handler) as repo:
        with pytest.raises(ShopError) as raised:
            repo.list_products()
    assert "private connection details" not in str(raised.value)
