from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models import CustomerRead, OrderItemRead, OrderRead, ProductRead
from scripts.seed_orders import CUSTOMERS, seed_demo_orders
from scripts.seed_products import demo_products


class DemoRepository:
    def __init__(self):
        self.products = [ProductRead.model_validate(product) for product in demo_products()]
        self.customers = {}
        self.orders = []

    def list_products(self, search=None):
        return self.products

    def list_customers(self):
        return list(self.customers.values())

    def list_orders(self, customer_id=None):
        return [order for order in self.orders if order.customer_id == customer_id]

    def create_order(self, payload):
        email = str(payload.customer_email)
        customer = self.customers.get(email)
        if customer is None:
            customer = CustomerRead(
                id=uuid4(), name=payload.customer_name, email=email,
                phone=payload.customer_phone, created_at=datetime.now(timezone.utc),
            )
            self.customers[email] = customer
        order_id = uuid4()
        prices = {product.id: product.price for product in self.products}
        items = [
            OrderItemRead(
                id=uuid4(), order_id=order_id, product_id=item.product_id,
                quantity=item.quantity, price=prices[item.product_id],
            )
            for item in payload.items
        ]
        order = OrderRead(
            id=order_id, customer_id=customer.id,
            total_amount=sum(item.quantity * item.price for item in items),
            status="Pending", created_at=datetime.now(timezone.utc),
            customer=customer, items=items,
        )
        self.orders.append(order)
        return order

    def update_order_status(self, order_id, status):
        index = next(i for i, order in enumerate(self.orders) if order.id == order_id)
        self.orders[index] = self.orders[index].model_copy(update={"status": status})
        return self.orders[index]


def test_seed_orders_creates_fictional_customers_and_is_repeatable():
    repo = DemoRepository()
    assert seed_demo_orders(repo) == (4, 8, 0)
    assert len(repo.customers) == len(CUSTOMERS)
    assert {order.status for order in repo.orders} == {"Pending", "Completed", "Cancelled"}
    assert all(customer.email.endswith("@example.com") for customer in repo.customers.values())
    assert all(order.total_amount > 0 for order in repo.orders)
    original_ids = {order.id for order in repo.orders}
    repo.orders[0] = repo.orders[0].model_copy(update={"status": "Completed"})

    assert seed_demo_orders(repo) == (0, 0, 8)
    assert {order.id for order in repo.orders} == original_ids
    assert repo.orders[0].status == "Completed"


def test_seed_orders_resumes_when_one_order_already_exists():
    repo = DemoRepository()
    seed_demo_orders(repo)
    removed = repo.orders.pop()
    assert seed_demo_orders(repo) == (0, 1, 7)
    assert len(repo.orders) == 8
    assert all(order.id != removed.id for order in repo.orders)


def test_seed_orders_requires_catalog_before_writing():
    repo = DemoRepository()
    repo.products.clear()
    with pytest.raises(ValueError, match="Seed the demo products"):
        seed_demo_orders(repo)
    assert repo.customers == {}
    assert repo.orders == []
