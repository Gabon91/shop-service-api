class ShopError(Exception):
    status_code = 503
    detail = "Database service unavailable"


class ConfigurationError(ShopError):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class InvalidCheckout(ShopError):
    status_code = 400
    detail = "Invalid checkout input or order total exceeds storage limits"


class ProductNotFound(ShopError):
    status_code = 404
    detail = "Product not found"


class DuplicateProduct(ShopError):
    status_code = 409
    detail = "Duplicate product in items"


class OrderNotFound(ShopError):
    status_code = 404
    detail = "Order not found"
