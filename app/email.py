import logging

import httpx

from app.models import OrderRead


logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"


def send_order_confirmation(order: OrderRead, *, api_key: str, sender: str) -> None:
    try:
        response = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": sender,
                "to": [str(order.customer.email)],
                "subject": "Your order is confirmed",
                "text": f"Order {order.id} was placed. Total: {order.total_amount:.2f}",
            },
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error(
            "Confirmation email delivery failed for order %s (%s)",
            order.id,
            type(exc).__name__,
        )
