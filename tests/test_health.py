from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from postgrest import APIError

from app.config import Settings
from app.dependencies import get_repository
from app.factory import create_app
from app.repositories import SupabaseShopRepository


def test_whoami_and_process_health_need_no_database():
    app = create_app(Settings())
    with TestClient(app) as client:
        assert client.get("/whoami").json() == {
            "service": "shop-service-api", "version": "1.0.0",
        }
        assert client.get("/health").json() == {"status": "ok"}


def test_livenss_queries_database_even_when_products_empty():
    database = Mock()
    query = database.table.return_value.select.return_value.limit.return_value
    query.execute.return_value.data = []
    app = create_app(Settings())
    app.dependency_overrides[get_repository] = lambda: SupabaseShopRepository(database)
    with TestClient(app) as client:
        response = client.get("/livenss")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
    database.table.assert_called_once_with("products")
    database.table.return_value.select.assert_called_once_with("id")
    database.table.return_value.select.return_value.limit.assert_called_once_with(1)
    query.execute.assert_called_once_with()


@pytest.mark.parametrize("error", [
    httpx.ConnectError("private connection details"),
    httpx.ReadTimeout("private connection details"),
    APIError({"code": "42501", "message": "private database details",
              "details": None, "hint": None}),
])
def test_livenss_returns_safe_503_on_database_failure(error):
    database = Mock()
    database.table.return_value.select.return_value.limit.return_value.execute.side_effect = error
    app = create_app(Settings())
    app.dependency_overrides[get_repository] = lambda: SupabaseShopRepository(database)
    with TestClient(app) as client:
        response = client.get("/livenss")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database service unavailable"}


def test_livenss_missing_configuration_is_not_healthy():
    with TestClient(create_app(Settings())) as client:
        response = client.get("/livenss")
    assert response.status_code == 503
    assert response.json() == {"detail": "SUPABASE_URL and SUPABASE_KEY must be configured"}


def test_health_routes_appear_in_openapi():
    with TestClient(create_app(Settings())) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert "/whoami" in paths
    assert "503" in paths["/livenss"]["get"]["responses"]


def test_deployed_frontend_is_allowed_for_json_order_preflight_and_get():
    origin = "https://shop-ui-react.vercel.app"
    with TestClient(create_app(Settings())) as client:
        preflight = client.options("/api/orders", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        actual = client.get("/whoami", headers={"Origin": origin})

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "POST" in preflight.headers["access-control-allow-methods"]
    assert actual.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in actual.headers


def test_unknown_origin_is_not_allowed():
    with TestClient(create_app(Settings())) as client:
        response = client.options("/api/orders", headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
