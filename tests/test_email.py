import base64
from email import message_from_bytes
import json
import logging

import httpx
import pytest

from app.config import Settings
from app.email import SEND_URL, TOKEN_URL, send_order_confirmation
from app.errors import ConfigurationError
from app.factory import create_app
from app.models import OrderRead


ORIGINAL_HTTPX_CLIENT = httpx.Client


def sample_order() -> OrderRead:
    return OrderRead.model_validate({
        "id": "33333333-3333-3333-3333-333333333333",
        "customer_id": "22222222-2222-2222-2222-222222222222",
        "total_amount": 25.0,
        "status": "Pending",
        "created_at": "2026-01-01T00:00:00+00:00",
        "customer": {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Ada Demo",
            "email": "ada@example.com",
            "phone": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        "items": [{
            "id": "44444444-4444-4444-4444-444444444444",
            "order_id": "33333333-3333-3333-3333-333333333333",
            "product_id": "11111111-1111-1111-1111-111111111111",
            "quantity": 2,
            "price": 12.5,
        }],
    })


def send_with_transport(monkeypatch, handler):
    monkeypatch.setattr(
        "app.email.httpx.Client",
        lambda **kwargs: ORIGINAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )
    return send_order_confirmation(
        sample_order(), gmail_address="orders@gmail.com", client_id="test-client",
        client_secret="private-client-secret", refresh_token="private-refresh-token",
    )


def test_order_email_refreshes_oauth_then_sends_mime_over_https(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        if str(request.url) == TOKEN_URL:
            assert request.content.decode() == (
                "client_id=test-client&client_secret=private-client-secret&"
                "refresh_token=private-refresh-token&grant_type=refresh_token"
            )
            return httpx.Response(200, json={"access_token": "test-access-token"})
        assert str(request.url) == SEND_URL
        assert request.headers["Authorization"] == "Bearer test-access-token"
        mime = message_from_bytes(base64.urlsafe_b64decode(json.loads(request.content)["raw"]))
        assert mime["From"] == "orders@gmail.com"
        assert mime["To"] == "ada@example.com"
        assert "25.00" in mime.get_payload(decode=True).decode()
        return httpx.Response(200, json={"id": "sent-message"})

    assert send_with_transport(monkeypatch, handler)
    assert len(seen) == 2


@pytest.mark.parametrize(("failed_url", "status"), [
    (TOKEN_URL, 400),
    (SEND_URL, 403),
])
def test_http_failure_logs_only_stage_and_status(monkeypatch, caplog, failed_url, status):
    def handler(request):
        if str(request.url) == failed_url:
            return httpx.Response(status, json={"error": "private provider error"})
        return httpx.Response(200, json={"access_token": "private-access-token"})

    with caplog.at_level(logging.ERROR):
        assert not send_with_transport(monkeypatch, handler)
    assert str(status) in caplog.text
    for secret in (
        "private-client-secret", "private-refresh-token",
        "private-access-token", "private provider error", "ada@example.com",
    ):
        assert secret not in caplog.text


def test_missing_access_token_and_network_error_are_safe(monkeypatch, caplog):
    with caplog.at_level(logging.ERROR):
        assert not send_with_transport(
            monkeypatch, lambda request: httpx.Response(200, json={})
        )
    assert "missing access token" in caplog.text
    with caplog.at_level(logging.ERROR):
        assert not send_with_transport(
            monkeypatch, lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("private timeout"))
        )
    assert "network" in caplog.text
    assert "private timeout" not in caplog.text


def test_email_settings_require_complete_valid_configuration():
    for settings in (
        Settings(gmail_address="orders@gmail.com"),
        Settings(google_refresh_token="only-token"),
        Settings(
            gmail_address="bad-address", google_client_id="id",
            google_client_secret="secret", google_refresh_token="token",
        ),
    ):
        with pytest.raises(ConfigurationError):
            create_app(settings)
