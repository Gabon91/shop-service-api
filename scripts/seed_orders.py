"""Seed fictional customers and checkout orders for dashboard demos."""

import argparse
from dataclasses import dataclass
from uuid import UUID

from app.config import Settings
from app.dependencies import RepositoryProvider
from app.errors import ShopError
from app.models import OrderCreate, OrderItemCreate, OrderItemRead, OrderStatus
from app.repositories import ShopRepository
from scripts.seed_products import demo_products


@dataclass(frozen=True)
class DemoOrder:
    status: OrderStatus
    lines: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class DemoCustomer:
    name: str
    email: str
    phone: str
    orders: tuple[DemoOrder, ...]


CUSTOMERS = (
    DemoCustomer(
        "Alex Demo", "shop-demo-alex@example.com", "+1-202-555-0101",
        (DemoOrder("Pending", ((0, 2), (4, 1))),
         DemoOrder("Completed", ((2, 1), (6, 2)))),
    ),
    DemoCustomer(
        "Sam Demo", "shop-demo-sam@example.com", "+1-202-555-0102",
        (DemoOrder("Completed", ((5, 1), (8, 2))),
         DemoOrder("Cancelled", ((10, 1),))),
    ),
    DemoCustomer(
        "Jordan Demo", "shop-demo-jordan@example.com", "+1-202-555-0103",
        (DemoOrder("Pending", ((12, 3),)),
         DemoOrder("Completed", ((14, 1), (16, 2)))),
    ),
    DemoCustomer(
        "Casey Demo", "shop-demo-casey@example.com", "+1-202-555-0104",
        (DemoOrder("Cancelled", ((17, 1),)),
         DemoOrder("Pending", ((20, 2),))),
    ),
)


def signature(items: list[OrderItemCreate] | list[OrderItemRead]) -> frozenset[tuple[UUID, int]]:
    return frozenset((item.product_id, item.quantity) for item in items)


def seed_demo_orders(repository: ShopRepository) -> tuple[int, int, int]:
    products = demo_products()
    available = {product.id for product in repository.list_products()}
    if not {UUID(str(product["id"])) for product in products}.issubset(available):
        raise ValueError("Seed the demo products before creating demo orders")

    existing_customers = {str(customer.email): customer for customer in repository.list_customers()}
    new_customers = new_orders = skipped_orders = 0
    for demo_customer in CUSTOMERS:
        customer = existing_customers.get(demo_customer.email)
        previous = repository.list_orders(customer.id) if customer is not None else []
        existing_signatures = {signature(order.items) for order in previous}
        for demo_order in demo_customer.orders:
            items = [
                OrderItemCreate(product_id=UUID(str(products[index]["id"])), quantity=quantity)
                for index, quantity in demo_order.lines
            ]
            item_signature = signature(items)
            if item_signature in existing_signatures:
                skipped_orders += 1
                continue

            payload = OrderCreate(
                customer_name=demo_customer.name,
                customer_email=demo_customer.email,
                customer_phone=demo_customer.phone,
                items=items,
            )
            created = repository.create_order(payload)
            if customer is None:
                new_customers += 1
                customer = created.customer
                existing_customers[demo_customer.email] = customer
            existing_signatures.add(item_signature)
            new_orders += 1
            if demo_order.status != "Pending":
                repository.update_order_status(created.id, demo_order.status)
    return new_customers, new_orders, skipped_orders


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed fictional customers and demo orders")
    parser.add_argument("--dry-run", action="store_true", help="Preview without connecting to Supabase")
    args = parser.parse_args()
    if args.dry_run:
        print(f"Would seed {len(CUSTOMERS)} demo customers and "
              f"{sum(len(customer.orders) for customer in CUSTOMERS)} orders.")
        return

    provider = RepositoryProvider(Settings.from_env())
    try:
        customers, orders, skipped = seed_demo_orders(provider.get())
        print(f"Added {customers} demo customers and {orders} orders; skipped {skipped} existing orders.")
    except ShopError as exc:
        raise SystemExit(f"Demo order seeding failed: {exc.detail}") from None
    except ValueError as exc:
        raise SystemExit(f"Demo order seeding failed: {exc}") from None
    finally:
        provider.close()


if __name__ == "__main__":
    main()
