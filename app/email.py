import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.models import OrderRead


logger = logging.getLogger(__name__)


def send_order_confirmation(
    order: OrderRead, *, gmail_address: str, app_password: str
) -> None:
    message = EmailMessage()
    message["From"] = gmail_address
    message["To"] = str(order.customer.email)
    message["Subject"] = "Your order is confirmed"
    message.set_content(f"Order {order.id} was placed. Total: {order.total_amount:.2f}")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(gmail_address, app_password)
            refused = smtp.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
    except (smtplib.SMTPException, OSError) as exc:
        logger.error(
            "Confirmation email delivery failed for order %s (%s)",
            order.id,
            type(exc).__name__,
        )
