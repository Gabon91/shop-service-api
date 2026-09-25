from threading import Lock
from typing import Annotated

import httpx
from fastapi import Depends, Request
from supabase import ClientOptions, create_client
from supabase._sync.client import SupabaseException

from app.config import Settings
from app.errors import ConfigurationError
from app.repositories import ShopRepository, SupabaseShopRepository
from app.services import OrderService


class RepositoryProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = Lock()
        self._repository: ShopRepository | None = None
        self._http: httpx.Client | None = None

    def get(self) -> ShopRepository:
        with self._lock:
            if self._repository is None:
                self._settings.validate_database()
                transport = httpx.Client(timeout=15.0)
                try:
                    client = create_client(
                        self._settings.supabase_url,
                        self._settings.supabase_key,
                        options=ClientOptions(
                            httpx_client=transport,
                            auto_refresh_token=False,
                            persist_session=False,
                        ),
                    )
                    # Initialize once under the lock; requests use independent builders.
                    client.postgrest
                except (SupabaseException, httpx.InvalidURL, ValueError):
                    transport.close()
                    raise ConfigurationError("Invalid Supabase client configuration") from None
                self._http = transport
                self._repository = SupabaseShopRepository(client)
            return self._repository

    def close(self) -> None:
        with self._lock:
            if self._http is not None:
                self._http.close()
                self._http = None
            self._repository = None


def get_repository(request: Request) -> ShopRepository:
    provider: RepositoryProvider = request.app.state.repository_provider
    return provider.get()


def get_order_service(
    repository: Annotated[ShopRepository, Depends(get_repository)],
) -> OrderService:
    return OrderService(repository)
