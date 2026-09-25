from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.dependencies import get_order_service
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
            customer = customer.model_copy(update={"name": name, "phone": phone})
            self.customers[email] = customer
        return customer

    def get_products_by_ids(self, product_ids):
        wanted = set(product_ids)
        return [product for product in self.products if product.id in wanted]

    def create_order(self, payload: OrderCreate):
        customer = self.upsert_customer(
            payload.customer_name, payload.customer_email, payload.customer_phone
        )
        products_by_id = {product.id: product for product in self.get_products_by_ids(
            [item.product_id for item in payload.items]
        )}
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
        order = self.orders[str(order_id)].model_copy(update={"status": status})
        self.orders[str(order_id)] = order
        return self.get_order(order_id)


def build_client():
    app = create_app()
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
