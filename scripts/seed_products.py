"""Populate the catalog with repeatable, unofficial building-brick demo products."""

import argparse
import random
from urllib.parse import quote_plus
from uuid import NAMESPACE_URL, uuid5

import httpx
from postgrest import APIError
from supabase import ClientOptions, create_client
from supabase._sync.client import SupabaseException

from app.config import Settings
from app.errors import ConfigurationError


PRODUCT_TYPES = (
    ("2x4 Brick Pack", "A pack of classic 2x4 building bricks."),
    ("2x2 Brick Pack", "A pack of compact 2x2 building bricks."),
    ("Flat Tile Pack", "Smooth tiles for finishing a model."),
    ("Window Frame Pack", "Frames for building houses and towers."),
    ("Roof Slope Pack", "Sloped bricks for creative rooftops."),
    ("Wheel and Axle Kit", "Parts for building rolling models."),
)
COLORS = ("Red", "Blue", "Yellow", "Green")
IMAGE_COLORS = {
    "Red": ("c83838", "ffffff"),
    "Blue": ("2860ae", "ffffff"),
    "Yellow": ("f4cc36", "222222"),
    "Green": ("26834f", "ffffff"),
}


def demo_products() -> list[dict[str, object]]:
    rng = random.Random(20260925)
    products: list[dict[str, object]] = []
    for product_type, description in PRODUCT_TYPES:
        for color in COLORS:
            name = f"{color} {product_type}"
            background, foreground = IMAGE_COLORS[color]
            products.append({
                "id": str(uuid5(NAMESPACE_URL, f"shop-service-api/demo-bricks/v1/{name}")),
                "name": name,
                "description": f"Unofficial demo product. {description}",
                "price": rng.randint(399, 2999) / 100,
                "stock": rng.randint(5, 40),
                "image_url": (
                    f"https://placehold.co/600x400/{background}/{foreground}.png"
                    f"?text={quote_plus(name)}"
                ),
            })
    return products


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed unofficial building-brick demo products")
    parser.add_argument("--dry-run", action="store_true", help="Preview without connecting to Supabase")
    args = parser.parse_args()
    products = demo_products()
    if args.dry_run:
        print(f"Would seed {len(products)} demo products (for example, {products[0]['name']}).")
        return

    settings = Settings.from_env()
    try:
        settings.validate_database()
        with httpx.Client(timeout=15.0) as transport:
            client = create_client(
                settings.supabase_url,
                settings.supabase_key,
                options=ClientOptions(
                    httpx_client=transport,
                    auto_refresh_token=False,
                    persist_session=False,
                ),
            )
            result = client.table("products").upsert(
                products, on_conflict="id", ignore_duplicates=True
            ).execute()
            updated = 0
            for product in products:
                changed = (
                    client.table("products")
                    .update({"image_url": product["image_url"]})
                    .eq("id", product["id"])
                    .is_("image_url", "null")
                    .execute()
                )
                updated += len(changed.data)
            print(
                f"Added {len(result.data)} demo products and filled {updated} blank image URLs; "
                "existing catalog edits were preserved."
            )
    except (ConfigurationError, SupabaseException, APIError, httpx.RequestError) as exc:
        raise SystemExit(f"Seeding failed ({type(exc).__name__}); no credentials printed.") from None


if __name__ == "__main__":
    main()
