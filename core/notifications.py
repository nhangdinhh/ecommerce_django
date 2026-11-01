import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Order


logger = logging.getLogger(__name__)


def send_order_status_email(order_id, status, note=''):
    order = Order.objects.select_related('user').filter(pk=order_id).first()
    if not order or not order.user.email:
        return
    subject = f'Nhang Shop order {order.ref_code}: {order.get_status_display()}'
    detail_url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}/orders/{order.ref_code}/"
    amount_label = 'Amount due on delivery' if order.shipping_fee_confirmed else 'Items total before delivery fee'
    delivery_fee = (
        f"Delivery fee: ${order.shipping_fee:.2f}"
        if order.shipping_fee_confirmed
        else 'Delivery fee: to be confirmed by the shop before dispatch.'
    )
    tracking = ''
    if order.status == 'shipped':
        tracking = (
            f"Carrier: {order.shipping_carrier or 'To be confirmed'}\n"
            f"Tracking number: {order.tracking_number or 'To be confirmed'}\n"
        )
    body = (
        f"Hello {order.user.get_short_name() or order.user.username},\n\n"
        f"Your order #{order.ref_code} is now: {order.get_status_display()}.\n"
        f"{note}\n\n"
        f"{tracking}"
        f"{delivery_fee}\n"
        f"{amount_label}: ${order.get_total():.2f}\n"
        f"Track your order: {detail_url}\n\n"
        "Nhang Shop"
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [order.user.email], fail_silently=False)
    except Exception:
        logger.exception('Could not send order update email for order %s', order.ref_code)


def send_shipping_quote_email(order_id):
    order = Order.objects.select_related('user').filter(pk=order_id).first()
    if not order or not order.user.email or not order.shipping_fee_confirmed:
        return
    detail_url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}/orders/{order.ref_code}/"
    subject = f'Nhang Shop order {order.ref_code}: delivery total to confirm'
    body = (
        f"Hello {order.user.get_short_name() or order.user.username},\n\n"
        f"The shop has confirmed a delivery fee of ${order.shipping_fee:.2f}.\n"
        f"Your total amount due on delivery is ${order.get_total():.2f}.\n\n"
        "Please review and accept this amount on your order page before the shop dispatches it.\n"
        f"Review your order: {detail_url}\n\n"
        "Nhang Shop"
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [order.user.email], fail_silently=False)
    except Exception:
        logger.exception('Could not send delivery quote for order %s', order.ref_code)
