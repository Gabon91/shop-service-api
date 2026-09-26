from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import smtplib
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_order_service
from app.errors import OrderNotFound, ProductNotFound
from app.factory import create_app
from app.models import CustomerRead, OrderCreate, OrderRead, OrderSummaryRead, ProductRead
from app.services import OrderService


class FakeRepository:
    def __init__(self) -> None:
        self.products = [
            ProductRead(
                id=UUID("11111111-1111-1111-1111-111111111111"),
                name="Laptop",
                description="Business laptop",
                price=1200.0,
                stock=3,
                image_url="https://example.com/laptop.png",
            ),
            ProductRead(
                id=UUID("22222222-2222-2222-2222-222222222222"),
                name="Mouse",
                description="Wireless mouse",
                price=25.0,
                stock=10,
                image_url=None,
            ),
        ]
        self.customers: dict[str, CustomerRead] = {}
        self.orders: dict[str, OrderSummaryRead] = {}
        self.order_items: dict[str, list] = {}

    def list_products(self, search: str | None = None):
        if not search:
            return self.products
        needle = search.lower()
        return [product for product in self.products if needle in product.name.lower()]

    def list_customers(self):
        return list(self.customers.values())

    def list_orders(self, customer_id: UUID | None = None):
        result = []
        for order in self.orders.values():
            if customer_id and order.customer_id != customer_id:
                continue
            result.append(self.get_order(order.id))
        return result

    def upsert_customer(self, name: str, email: str, phone: str | None):
        customer = self.customers.get(email)
        if customer is None:
            customer = CustomerRead(
                id=uuid4(),
                name=name,
                email=email,
                phone=phone,
                created_at=datetime.now(timezone.utc),
            )
            self.customers[email] = customer
        else:
            customer = customer.model_copy(update={
                "name": name, "phone": phone if phone is not None else customer.phone
            })
            self.customers[email] = customer
        return customer

    def get_products_by_ids(self, product_ids):
        wanted = set(product_ids)
        return [product for product in self.products if product.id in wanted]

    def create_order(self, payload: OrderCreate):
        products_by_id = {product.id: product for product in self.get_products_by_ids(
            [item.product_id for item in payload.items]
        )}
        if any(item.product_id not in products_by_id for item in payload.items):
            raise ProductNotFound()
        customer = self.upsert_customer(
            payload.customer_name, payload.customer_email, payload.customer_phone
        )
        total_amount = sum(
            item.quantity * products_by_id[item.product_id].price for item in payload.items
        )
        order = OrderSummaryRead(
            id=uuid4(),
            customer_id=customer.id,
            total_amount=total_amount,
            status="Pending",
            created_at=datetime.now(timezone.utc),
        )
        self.orders[str(order.id)] = order
        created = []
        for item in payload.items:
            created.append(
                {
                    "id": uuid4(),
                    "order_id": order.id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "price": products_by_id[item.product_id].price,
                }
            )
        self.order_items[str(order.id)] = created
        return self.get_order(order.id)

    def get_order(self, order_id: UUID):
        order = self.orders[str(order_id)]
        customer = next(customer for customer in self.customers.values()
                        if customer.id == order.customer_id)
        return OrderRead(
            **order.model_dump(),
            customer=customer,
            items=[
                item
                for item in self.order_items.get(str(order_id), [])
            ],
        )

    def update_order_status(self, order_id: UUID, status: str):
        if str(order_id) not in self.orders:
            raise OrderNotFound()
        order = self.orders[str(order_id)].model_copy(update={"status": status})
        self.orders[str(order_id)] = order
        return self.get_order(order_id)


def build_client(settings: Settings | None = None):
    app = create_app(settings)
    fake_service = OrderService(FakeRepository())
    app.dependency_overrides[get_order_service] = lambda: fake_service
    return TestClient(app), fake_service


def test_get_products_filters_by_search():
    client, _ = build_client()

    response = client.get("/api/products", params={"search": "laptop"})

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Laptop"


def test_create_order_auto_creates_customer():
    client, service = build_client()
    payload = {
        "customer_name": "Ada Lovelace",
        "customer_email": "ada@example.com",
        "customer_phone": "+1-555-1000",
        "items": [
            {"product_id": "11111111-1111-1111-1111-111111111111", "quantity": 2},
            {"product_id": "22222222-2222-2222-2222-222222222222", "quantity": 1},
        ],
    }

    response = client.post("/api/orders", json=payload)

    assert response.status_code == 201
    assert response.json()["total_amount"] == 2425.0
    assert "ada@example.com" in service._repository.customers
    assert len(response.json()["items"]) == 2


def test_update_order_status():
    client, _ = build_client()
    created = client.post(
        "/api/orders",
        json={
            "customer_name": "Grace Hopper",
            "customer_email": "grace@example.com",
            "customer_phone": "+1-555-2000",
            "items": [{"product_id": "11111111-1111-1111-1111-111111111111", "quantity": 1}],
        },
    ).json()

    response = client.patch(f"/api/orders/{created['id']}/status", json={"status": "Completed"})

    assert response.status_code == 200
    assert response.json()["status"] == "Completed"


def order_payload(name="Ada", email="ada@example.com", phone=None):
    return {
        "customer_name": name,
        "customer_email": email,
        "customer_phone": phone,
        "items": [{"product_id": "11111111-1111-1111-1111-111111111111", "quantity": 2}],
    }


def test_products_unfiltered_and_empty_search():
    client, _ = build_client()
    assert len(client.get("/api/products").json()) == 2
    assert len(client.get("/api/products", params={"search": ""}).json()) == 2


def test_customers_orders_and_customer_filter():
    client, _ = build_client()
    assert client.get("/api/customers").json() == []
    assert client.get("/api/orders").json() == []
    ada = client.post("/api/orders", json=order_payload()).json()
    grace = client.post(
        "/api/orders", json=order_payload("Grace", "grace@example.com")
    ).json()
    customers = client.get("/api/customers")
    assert customers.status_code == 200
    assert {c["email"] for c in customers.json()} == {
        "ada@example.com", "grace@example.com",
    }
    assert len(client.get("/api/orders").json()) == 2
    ada_orders = client.get("/api/orders", params={"customer_id": ada["customer_id"]})
    assert ada_orders.status_code == 200
    assert [order["id"] for order in ada_orders.json()] == [ada["id"]]
    assert ada_orders.json()[0]["customer"]["email"] == "ada@example.com"
    assert client.get(
        "/api/orders", params={"customer_id": str(uuid4())}
    ).json() == []
    assert grace["customer_id"] != ada["customer_id"]


def test_checkout_reuses_customer_and_preserves_phone_when_omitted():
    client, _ = build_client()
    first = client.post(
        "/api/orders", json=order_payload(phone="+1-555-0101")
    ).json()
    second = client.post(
        "/api/orders", json=order_payload("Ada Updated")
    ).json()
    assert second["customer_id"] == first["customer_id"]
    assert second["id"] != first["id"]
    assert second["customer"]["name"] == "Ada Updated"
    assert second["customer"]["phone"] == "+1-555-0101"
    assert len(client.get("/api/customers").json()) == 1


@pytest.mark.parametrize("change", [
    {"customer_name": " \t "},
    {"customer_email": "not-email"},
    {"items": []},
    {"items": [{"product_id": "not-a-uuid", "quantity": 1}]},
    {"items": [{"product_id": "11111111-1111-1111-1111-111111111111", "quantity": 0}]},
    {"items": [{"product_id": "11111111-1111-1111-1111-111111111111", "quantity": True}]},
    {"items": [{"product_id": "11111111-1111-1111-1111-111111111111", "quantity": 1.0}]},
    {"items": [{"product_id": "11111111-1111-1111-1111-111111111111", "quantity": 2147483648}]},
    {"items": [
        {"product_id": "11111111-1111-1111-1111-111111111111", "quantity": 1},
        {"product_id": "11111111-1111-1111-1111-111111111111", "quantity": 2},
    ]},
    {"total_amount": 0},
])
def test_bad_checkout_does_not_create_records(change):
    client, _ = build_client()
    assert client.post("/api/orders", json={**order_payload(), **change}).status_code == 422
    assert client.get("/api/orders").json() == []
    assert client.get("/api/customers").json() == []


def test_missing_product_is_404_without_customer_creation():
    client, _ = build_client()
    payload = order_payload()
    payload["items"][0]["product_id"] = str(uuid4())
    response = client.post("/api/orders", json=payload)
    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found"}
    assert client.get("/api/customers").json() == []


def test_status_errors_and_invalid_customer_filter():
    client, _ = build_client()
    assert client.patch(
        f"/api/orders/{uuid4()}/status", json={"status": "Completed"}
    ).status_code == 404
    assert client.patch(
        f"/api/orders/{uuid4()}/status", json={"status": "Shipped"}
    ).status_code == 422
    assert client.patch(
        "/api/orders/not-uuid/status", json={"status": "Completed"}
    ).status_code == 422
    assert client.get("/api/orders?customer_id=not-uuid").status_code == 422


def test_openapi_contract_for_shop_endpoints():
    client, _ = build_client()
    schema = client.get("/openapi.json").json()
    assert schema["openapi"] == "3.0.3"
    assert schema["info"]["title"] == "Mini E-Commerce Store API"
    paths = schema["paths"]
    for path, method, summary, code, description in [
        ("/api/products", "get", "Get all products", "200", "List of products"),
        ("/api/customers", "get", "Get all customers (Business side)", "200",
         "List of customers"),
        ("/api/orders", "get", "Get orders", "200", "List of orders"),
        ("/api/orders", "post", "Create a new order", "201", "Order created"),
        ("/api/orders/{id}/status", "patch", "Update order status", "200",
         "Status updated"),
    ]:
        operation = paths[path][method]
        assert operation["summary"] == summary
        assert operation["responses"][code]["description"] == description
    assert paths["/api/orders/{id}/status"]["patch"]["parameters"][0]["name"] == "id"
    assert paths["/api/orders"]["get"]["parameters"][0]["schema"]["format"] == "uuid"
    assert paths["/api/products"]["get"]["parameters"][0]["name"] == "search"


def test_order_email_is_sent_before_checkout_response_and_only_after_success(monkeypatch):
    calls = []
    def send_now(order, **kwargs):
        calls.append((order, kwargs))
        assert str(order.id) in service._repository.orders

    monkeypatch.setattr("app.factory.send_order_confirmation", send_now)
    client, service = build_client(Settings(
        gmail_address="orders@gmail.com",
        gmail_app_password="test-app-password",
    ))
    created = client.post("/api/orders", json=order_payload())
    assert created.status_code == 201
    assert len(calls) == 1
    assert str(calls[0][0].id) == created.json()["id"]
    assert calls[0][1] == {
        "gmail_address": "orders@gmail.com", "app_password": "test-app-password"
    }

    invalid = client.post("/api/orders", json={**order_payload(), "items": []})
    missing = order_payload()
    missing["items"][0]["product_id"] = str(uuid4())
    unknown = client.post("/api/orders", json=missing)
    assert invalid.status_code == 422
    assert unknown.status_code == 404
    assert len(calls) == 1


def test_order_email_is_disabled_without_provider_configuration(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.factory.send_order_confirmation",
        lambda order, **kwargs: calls.append(order),
    )
    client, _ = build_client(Settings())
    assert client.post("/api/orders", json=order_payload()).status_code == 201
    assert calls == []


def test_provider_failure_does_not_make_saved_order_look_failed(monkeypatch, caplog):
    def fail_send(*args, **kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"private provider error")

    monkeypatch.setattr("app.email.smtplib.SMTP", fail_send)
    client, _ = build_client(Settings(
        gmail_address="orders@gmail.com",
        gmail_app_password="test-app-password",
    ))
    response = client.post("/api/orders", json=order_payload())
    assert response.status_code == 201
    assert len(client.get("/api/orders").json()) == 1
    assert "Confirmation email delivery failed" in caplog.text
    assert "private provider error" not in caplog.text
