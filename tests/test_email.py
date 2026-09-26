import logging
import smtplib
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.email import send_order_confirmation
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


def test_order_email_uses_gmail_starttls(monkeypatch):
    smtp = MagicMock()
    monkeypatch.setattr("app.email.smtplib.SMTP", smtp)
    session = smtp.return_value.__enter__.return_value
    send_order_confirmation(
        sample_order(), gmail_address="orders@gmail.com", app_password="test-app-password"
    )

    smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
    session.starttls.assert_called_once()
    session.login.assert_called_once_with("orders@gmail.com", "test-app-password")
    message = session.send_message.call_args.args[0]
    assert message["From"] == "orders@gmail.com"
    assert message["To"] == "ada@example.com"
    assert "25.00" in message.get_content()
    assert "33333333-3333-3333-3333-333333333333" in message.get_content()


@pytest.mark.parametrize("error", [
    smtplib.SMTPAuthenticationError(535, b"private auth details"),
    TimeoutError("private connection details"),
])
def test_email_failure_is_logged_without_exposing_secrets(monkeypatch, caplog, error):
    def fail_connect(*args, **kwargs):
        raise error

    monkeypatch.setattr("app.email.smtplib.SMTP", fail_connect)
    with caplog.at_level(logging.ERROR):
        send_order_confirmation(
            sample_order(), gmail_address="orders@gmail.com", app_password="private-password"
        )
    assert "Confirmation email delivery failed" in caplog.text
    assert "private-password" not in caplog.text
    assert "private auth details" not in caplog.text
    assert "private connection details" not in caplog.text
    assert "ada@example.com" not in caplog.text


def test_refused_recipient_is_reported_without_exposing_address(monkeypatch, caplog):
    smtp = MagicMock()
    smtp.return_value.__enter__.return_value.send_message.return_value = {
        "ada@example.com": (550, b"private recipient details"),
    }
    monkeypatch.setattr("app.email.smtplib.SMTP", smtp)
    with caplog.at_level(logging.ERROR):
        send_order_confirmation(
            sample_order(), gmail_address="orders@gmail.com", app_password="private-password"
        )
    assert "Confirmation email delivery failed" in caplog.text
    assert "ada@example.com" not in caplog.text
    assert "private recipient details" not in caplog.text


def test_email_settings_require_complete_valid_configuration():
    for settings in (
        Settings(gmail_app_password="only-password"),
        Settings(gmail_address="orders@gmail.com"),
        Settings(gmail_address="bad-address", gmail_app_password="password"),
        Settings(gmail_address="orders@gmail.com", gmail_app_password="has\twhitespace"),
    ):
        with pytest.raises(ConfigurationError):
            create_app(settings)


def test_grouped_google_app_password_is_normalized_before_login(monkeypatch):
    smtp = MagicMock()
    monkeypatch.setattr("app.email.smtplib.SMTP", smtp)
    settings = Settings(
        gmail_address="orders@gmail.com",
        gmail_app_password="abcd efgh ijkl mnop",
    )
    create_app(settings)
    send_order_confirmation(
        sample_order(),
        gmail_address=settings.gmail_address,
        app_password=settings.gmail_app_password,
    )
    smtp.return_value.__enter__.return_value.login.assert_called_once_with(
        "orders@gmail.com", "abcdefghijklmnop"
    )
