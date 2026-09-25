from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


OrderStatus = Literal["Pending", "Completed", "Cancelled"]


def _validate_email(value: str) -> str:
    try:
        validate_email(value, check_deliverability=False)
    except EmailNotValidError:
        raise ValueError("Invalid email address") from None
    # The deployed unique key and RPC use case-sensitive, verbatim email identity.
    return value


EmailAddress = Annotated[
    str, AfterValidator(_validate_email), Field(json_schema_extra={"format": "email"})
]


class ProductRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    price: float
    stock: int
    image_url: str | None = None


class CustomerRead(BaseModel):
    id: UUID
    name: str
    email: EmailAddress
    phone: str | None = None
    created_at: datetime


class OrderItemRead(BaseModel):
    id: UUID
    order_id: UUID
    product_id: UUID
    quantity: int
    price: float


class OrderSummaryRead(BaseModel):
    id: UUID
    customer_id: UUID
    total_amount: float
    status: OrderStatus
    created_at: datetime


class OrderRead(OrderSummaryRead):
    customer: CustomerRead
    items: list[OrderItemRead]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrderItemCreate(RequestModel):
    product_id: UUID
    quantity: int = Field(strict=True, ge=1, le=2147483647)


class OrderCreate(RequestModel):
    customer_name: str = Field(min_length=1)
    customer_email: EmailAddress
    customer_phone: str | None = None
    items: list[OrderItemCreate] = Field(min_length=1)

    @field_validator("customer_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Customer name must not be blank")
        return value

    @model_validator(mode="after")
    def unique_products(self) -> Self:
        if len({item.product_id for item in self.items}) != len(self.items):
            raise ValueError("Duplicate product in items")
        return self


class OrderStatusUpdate(RequestModel):
    status: OrderStatus


class ErrorResponse(BaseModel):
    detail: str
