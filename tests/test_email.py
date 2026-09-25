import logging

import httpx
import pytest

from app.config import Settings
from app.email import RESEND_URL, send_order_confirmation
from app.errors import ConfigurationError
from app.factory import create_app
from app.models import OrderRead


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


def test_order_email_uses_resend_with_customer_and_order_summary(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={"id": "email-123"}, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.email.httpx.post", fake_post)
    send_order_confirmation(
        sample_order(), api_key="test-api-key", sender="orders@example.com"
    )

    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == RESEND_URL
    assert kwargs["headers"]["Authorization"] == "Bearer test-api-key"
    assert kwargs["json"]["from"] == "orders@example.com"
    assert kwargs["json"]["to"] == ["ada@example.com"]
    assert "25.00" in kwargs["json"]["text"]
    assert "33333333-3333-3333-3333-333333333333" in kwargs["json"]["text"]
    assert kwargs["timeout"] == 10.0


@pytest.mark.parametrize("error", [
    httpx.Response(403, json={"message": "private provider error"},
                   request=httpx.Request("POST", RESEND_URL)),
    httpx.ReadTimeout("private provider error"),
])
def test_email_failure_is_logged_without_exposing_keys_or_failing_order(
    monkeypatch, caplog, error
):
    def fake_post(url, **kwargs):
        if isinstance(error, Exception):
            raise error
        return error

    monkeypatch.setattr("app.email.httpx.post", fake_post)
    with caplog.at_level(logging.ERROR):
        send_order_confirmation(
            sample_order(), api_key="private-api-key", sender="orders@example.com"
        )
    assert "Confirmation email delivery failed" in caplog.text
    assert "private-api-key" not in caplog.text
    assert "private provider error" not in caplog.text
    assert "ada@example.com" not in caplog.text


def test_email_settings_require_a_complete_valid_configuration():
    for settings in (
        Settings(resend_api_key="only-key"),
        Settings(order_email_from="orders@example.com"),
        Settings(resend_api_key="key", order_email_from="bad-address"),
    ):
        with pytest.raises(ConfigurationError):
            create_app(settings)
