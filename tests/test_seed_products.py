from uuid import UUID

from scripts.photo_sources import PHOTOS
from scripts.seed_products import (
    can_replace_seed_image, demo_products, old_placeholder, previous_seed_description,
)


def test_seed_catalog_is_repeatable_and_safe_for_reruns():
    products = demo_products()
    assert products == demo_products()
    assert len(products) == 24
    assert len({product["id"] for product in products}) == 24
    assert len({product["name"] for product in products}) == 24
    assert all(UUID(product["id"]).version == 5 for product in products)
    assert all(product["price"] > 0 and product["stock"] >= 0 for product in products)
    assert len({product["image_url"] for product in products}) >= 8
    assert all(product["image_url"] in {photo.url for photo in PHOTOS.values()}
               for product in products)
    assert all(photo.source in product["description"]
               and photo.license_url in product["description"]
               and photo.author in product["description"]
               for product in products
               for photo in PHOTOS.values() if product["image_url"] == photo.url)


def test_only_seed_owned_placeholders_are_replaced():
    product = demo_products()[0]
    name = product["name"]
    prior = {
        **product,
        "image_url": old_placeholder(name, "Red"),
        "description": previous_seed_description(name),
    }
    assert can_replace_seed_image(prior, product)
    assert can_replace_seed_image({**prior, "image_url": None}, product)
    assert not can_replace_seed_image(product, product)
    assert not can_replace_seed_image({**prior, "image_url": "https://example.com/custom.jpg"}, product)
    assert not can_replace_seed_image({**prior, "description": "Custom description"}, product)
    assert not can_replace_seed_image({**prior, "name": "Custom name"}, product)
