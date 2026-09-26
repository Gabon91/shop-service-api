"""Send a local test message to the authorized Gmail account, without creating an order."""

from datetime import datetime, timezone
from uuid import uuid4

from app.config import Settings
from app.email import send_order_confirmation
from app.models import CustomerRead, OrderRead


def main() -> None:
    settings = Settings.from_env()
    settings.validate_order_email()
    if not settings.gmail_address:
        raise SystemExit("Configure Gmail OAuth in local .env before running this check.")
    customer = CustomerRead(
        id=uuid4(), name="Local email test", email=settings.gmail_address,
        created_at=datetime.now(timezone.utc),
    )
    message = OrderRead(
        id=uuid4(), customer_id=customer.id, total_amount=0.0,
        status="Pending", created_at=datetime.now(timezone.utc),
        customer=customer, items=[],
    )
    if not send_order_confirmation(
        message, gmail_address=settings.gmail_address,
        client_id=settings.google_client_id, client_secret=settings.google_client_secret,
        refresh_token=settings.google_refresh_token,
    ):
        raise SystemExit("Gmail API test send failed; check the safe status in the application log.")
    print("Gmail API accepted the local test message. Check the account inbox and Sent folder.")


if __name__ == "__main__":
    main()
