import base64
from email.message import EmailMessage
import logging

import httpx

from app.models import OrderRead


logger = logging.getLogger(__name__)
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def send_order_confirmation(
    order: OrderRead, *, gmail_address: str, client_id: str,
    client_secret: str, refresh_token: str,
) -> bool:
    message = EmailMessage()
    message["From"] = gmail_address
    message["To"] = str(order.customer.email)
    message["Subject"] = "Your order is confirmed"
    message.set_content(f"Order {order.id} was placed. Total: {order.total_amount:.2f}")

    stage = "token"
    try:
        with httpx.Client(timeout=10.0) as client:
            token_response = client.post(TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not isinstance(access_token, str) or not access_token:
                logger.error("Confirmation email token response missing access token for order %s", order.id)
                return False

            stage = "send"
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
            sent = client.post(
                SEND_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
            )
            sent.raise_for_status()
            return True
    except httpx.HTTPError as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else "network"
        logger.error("Confirmation email failed for order %s (%s: %s)", order.id, stage, status)
        return False
