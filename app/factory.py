from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.config import Settings
from app.dependencies import RepositoryProvider, get_order_service, get_repository
from app.email import send_order_confirmation
from app.errors import ShopError
from app.models import (
    CustomerRead,
    ErrorResponse,
    OrderCreate,
    OrderRead,
    OrderStatusUpdate,
    ProductRead,
)
from app.openapi import install_openapi
from app.repositories import ShopRepository
from app.services import OrderService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()
    settings.validate_order_email()
    provider = RepositoryProvider(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await run_in_threadpool(provider.close)

    app = FastAPI(
        title="Mini E-Commerce Store API",
        version=__version__,
        description="FastAPI backend for products, customers, and orders on Supabase.",
        lifespan=lifespan,
        responses={503: {"model": ErrorResponse, "description": "Database service unavailable"}},
    )
    app.state.repository_provider = provider
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(ShopError)
    async def shop_error_handler(request: Request, exc: ShopError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/health", summary="Process liveness", responses={200: {"description": "Process is running"}})
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/whoami", summary="Service identity")
    def whoami() -> dict[str, str]:
        return {"service": "shop-service-api", "version": app.version}

    @app.get(
        "/livenss", summary="Database connectivity",
        response_description="Supabase database is reachable",
    )
    def livenss(repository: ShopRepository = Depends(get_repository)) -> dict[str, str]:
        repository.check_connection()
        return {"status": "ok", "database": "connected"}

    @app.get(
        "/api/products", response_model=list[ProductRead], summary="Get all products",
        response_description="List of products",
    )
    def get_products(
        search: str | None = Query(default=None),
        service: OrderService = Depends(get_order_service),
    ) -> list[ProductRead]:
        return service.list_products(search=search)

    @app.get(
        "/api/customers",
        response_model=list[CustomerRead],
        summary="Get all customers (Business side)",
        response_description="List of customers",
    )
    def get_customers(service: OrderService = Depends(get_order_service)) -> list[CustomerRead]:
        return service.list_customers()

    @app.get(
        "/api/orders", response_model=list[OrderRead], summary="Get orders",
        response_description="List of orders",
    )
    def get_orders(
        customer_id: UUID | None = Query(default=None),
        service: OrderService = Depends(get_order_service),
    ) -> list[OrderRead]:
        return service.list_orders(customer_id=customer_id)

    @app.post(
        "/api/orders",
        response_model=OrderRead,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new order",
        response_description="Order created",
        responses={
            400: {"model": ErrorResponse, "description": "Invalid checkout input or total overflow"},
            404: {"model": ErrorResponse, "description": "Product not found"},
            409: {"model": ErrorResponse, "description": "Duplicate products rejected by database"},
            422: {"description": "Invalid request, including duplicate product IDs"},
        },
    )
    def create_order(
        payload: OrderCreate,
        service: OrderService = Depends(get_order_service),
    ) -> OrderRead:
        order = service.create_order(payload)
        if settings.gmail_address:
            send_order_confirmation(
                order,
                gmail_address=settings.gmail_address,
                app_password=settings.gmail_app_password,
            )
        return order

    @app.patch(
        "/api/orders/{id}/status", response_model=OrderRead, summary="Update order status",
        response_description="Status updated",
        responses={404: {"model": ErrorResponse, "description": "Order not found"}},
    )
    def update_order_status(
        id: UUID,
        payload: OrderStatusUpdate,
        service: OrderService = Depends(get_order_service),
    ) -> OrderRead:
        return service.update_order_status(id, payload.status)

    install_openapi(app)
    return app
