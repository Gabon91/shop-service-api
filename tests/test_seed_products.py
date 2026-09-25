from uuid import UUID

from scripts.seed_products import demo_products


def test_seed_catalog_is_repeatable_and_safe_for_reruns():
    products = demo_products()
    assert products == demo_products()
    assert len(products) == 24
    assert len({product["id"] for product in products}) == 24
    assert len({product["name"] for product in products}) == 24
    assert all(UUID(product["id"]).version == 5 for product in products)
    assert all(product["price"] > 0 and product["stock"] >= 0 for product in products)
    assert all(product["image_url"] is None for product in products)
