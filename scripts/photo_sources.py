"""Reusable Commons photographs and attribution for unofficial demo products."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Photo:
    url: str
    source: str
    author: str
    license_name: str
    license_url: str

    def credit(self) -> str:
        return (
            f"Illustrative photo (part or color may differ): {self.author}, "
            f"{self.license_name}. Source: {self.source} License: {self.license_url}"
        )


PHOTOS = {
    "green_brick": Photo(
        "https://upload.wikimedia.org/wikipedia/commons/f/fd/Light_Green_Lego_Brick.jpg",
        "https://commons.wikimedia.org/wiki/File:Light_Green_Lego_Brick.jpg",
        "Stilfehler", "CC BY-SA 3.0",
        "https://creativecommons.org/licenses/by-sa/3.0/",
    ),
    "blue_round_brick": Photo(
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a2/Lego_Round_Brick_Blue.jpg/500px-Lego_Round_Brick_Blue.jpg",
        "https://commons.wikimedia.org/wiki/File:Lego_Round_Brick_Blue.jpg",
        "Stilfehler", "CC BY-SA 3.0",
        "https://creativecommons.org/licenses/by-sa/3.0/",
    ),
    "assorted_color_bricks": Photo(
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/3/32/Lego_Color_Bricks.jpg/500px-Lego_Color_Bricks.jpg",
        "https://commons.wikimedia.org/wiki/File:Lego_Color_Bricks.jpg",
        "Alan Chia", "CC BY-SA 2.0",
        "https://creativecommons.org/licenses/by-sa/2.0/",
    ),
    "loose_blocks": Photo(
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/8/8b/Pile_of_lego_blocks.jpg/500px-Pile_of_lego_blocks.jpg",
        "https://commons.wikimedia.org/wiki/File:Pile_of_lego_blocks.jpg",
        "GTurnbull925", "CC BY-SA 4.0",
        "https://creativecommons.org/licenses/by-sa/4.0/",
    ),
    "assorted_store_bricks": Photo(
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/1/19/Lego_bricks.jpg/500px-Lego_bricks.jpg",
        "https://commons.wikimedia.org/wiki/File:Lego_bricks.jpg",
        "Benjamin D. Esham", "CC BY-SA 4.0",
        "https://creativecommons.org/licenses/by-sa/4.0/",
    ),
    "bricks_250_365": Photo(
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/21/250_365_-_Bricks_%284247555680%29.jpg/500px-250_365_-_Bricks_%284247555680%29.jpg",
        "https://commons.wikimedia.org/wiki/File:250_365_-_Bricks_(4247555680).jpg",
        "Kenny Louie", "CC BY 2.0",
        "https://creativecommons.org/licenses/by/2.0/",
    ),
    "technic_gears": Photo(
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/69/Lego_Technic_gears_red%2Cblue%2Cyellow_%2842457828342%29.jpg/500px-Lego_Technic_gears_red%2Cblue%2Cyellow_%2842457828342%29.jpg",
        "https://commons.wikimedia.org/wiki/File:Lego_Technic_gears_red,blue,yellow_(42457828342).jpg",
        "Brickset", "CC BY 2.0",
        "https://creativecommons.org/licenses/by/2.0/",
    ),
    "wedo_bricks": Photo(
        "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/7a/Lego_WeDo_2.0_Bricks.jpg/500px-Lego_WeDo_2.0_Bricks.jpg",
        "https://commons.wikimedia.org/wiki/File:Lego_WeDo_2.0_Bricks.jpg",
        "Klaus-Dieter Keller", "CC0 1.0",
        "https://creativecommons.org/publicdomain/zero/1.0/",
    ),
}


# Images are illustrative, not photographs of the exact variant being sold.
PHOTO_KEYS = {
    "2x4 Brick Pack": (
        "assorted_color_bricks", "blue_round_brick",
        "loose_blocks", "green_brick",
    ),
    "2x2 Brick Pack": (
        "assorted_store_bricks", "blue_round_brick",
        "bricks_250_365", "green_brick",
    ),
    "Flat Tile Pack": (
        "loose_blocks", "assorted_store_bricks",
        "wedo_bricks", "green_brick",
    ),
    "Window Frame Pack": (
        "assorted_store_bricks", "wedo_bricks",
        "loose_blocks", "green_brick",
    ),
    "Roof Slope Pack": (
        "bricks_250_365", "blue_round_brick",
        "assorted_color_bricks", "green_brick",
    ),
    "Wheel and Axle Kit": (
        "technic_gears", "technic_gears",
        "technic_gears", "technic_gears",
    ),
}
