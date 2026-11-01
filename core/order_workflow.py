from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Coupon, Item, ItemVariant, Order, OrderStatusHistory, Payment, Refund, StockMovement
from .notifications import send_order_status_email


ALLOWED_TRANSITIONS = {
    'pending': {'confirmed', 'cancelled'},
    'confirmed': {'packed', 'cancelled'},
    'packed': {'shipped', 'cancelled'},
    'shipped': {'delivered', 'delivery_failed'},
    'delivery_failed': {'shipped', 'returning'},
    'returning': {'returned'},
    'returned': set(),
    'delivered': {'refund_requested'},
    'refund_requested': {'delivered', 'refunded'},
    'cancelled': set(),
    'refunded': set(),
}


@transaction.atomic
def transition_order_status(order, new_status, actor=None, note=''):
    order = Order.objects.select_for_update().get(pk=order.pk)
    old_status = order.status
    if new_status == old_status:
        return order
    if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
        raise ValidationError(f"Cannot move an order from {old_status} to {new_status}.")

    if new_status == 'shipped' and (not order.shipping_carrier or not order.tracking_number):
        raise ValidationError('Set the shipping carrier and tracking number before shipping an order.')
    if new_status == 'shipped' and not order.shipping_fee_confirmed:
        raise ValidationError('Confirm the shipping fee before shipping an order.')
    if new_status == 'shipped' and not order.shipping_fee_accepted:
        raise ValidationError('The customer must accept the final delivery fee before the order ships.')

    if new_status == 'refunded':
        refund = Refund.objects.select_for_update().filter(order_id=order.pk).first()
        if not refund or not refund.accepted or not refund.items_received:
            raise ValidationError('Accept the return and confirm the returned parcel arrived before completing a refund.')

    if new_status in {'cancelled', 'returned'}:
        if order.stock_deducted:
            for line in order.items.select_related('item', 'variant').all():
                if line.variant_id:
                    ItemVariant.objects.filter(pk=line.variant_id).update(
                        stock_quantity=F('stock_quantity') + line.quantity
                    )
                else:
                    Item.objects.filter(pk=line.item_id).update(
                        stock_quantity=F('stock_quantity') + line.quantity
                    )
                StockMovement.objects.create(
                    item_id=line.item_id,
                    variant=line.variant,
                    order=order,
                    quantity_change=line.quantity,
                    reason='delivery_return' if new_status == 'returned' else 'cancellation',
                    note=(
                        'Stock restored after the failed-delivery parcel returned to the shop.'
                        if new_status == 'returned'
                        else 'Stock released after order cancellation.'
                    ),
                    created_by=actor,
                )
            order.stock_deducted = False
        if order.coupon_id and order.ordered:
            Coupon.objects.filter(pk=order.coupon_id, use_count__gt=0).update(use_count=F('use_count') - 1)
        order.payment_status = 'cancelled'
        if order.payment_id:
            Payment.objects.filter(pk=order.payment_id).update(status='cancelled')

    order.status = new_status
    order.being_delivered = new_status in {'shipped', 'delivery_failed', 'returning'}
    order.received = new_status == 'delivered'
    order.refund_requested = new_status == 'refund_requested'
    order.refund_granted = new_status == 'refunded'

    if new_status == 'shipped' and not order.shipped_at:
        order.shipped_at = timezone.now()
    if new_status == 'delivered':
        if not order.delivered_at:
            order.delivered_at = timezone.now()
        if order.payment_method == 'cod':
            order.payment_status = 'paid'
            if order.payment_id:
                payment = order.payment
                payment.method = 'cod'
                payment.status = 'paid'
                payment.amount = order.get_total()
                payment.save(update_fields=('method', 'status', 'amount'))
            else:
                order.payment = Payment.objects.create(
                    user=order.user,
                    amount=order.get_total(),
                    method='cod',
                    status='paid',
                )
    elif new_status == 'refunded':
        order.payment_status = 'refunded'
        if order.payment_id:
            Payment.objects.filter(pk=order.payment_id).update(status='refunded')
        if order.coupon_id and order.ordered:
            Coupon.objects.filter(pk=order.coupon_id, use_count__gt=0).update(use_count=F('use_count') - 1)

    order.save()
    OrderStatusHistory.objects.create(
        order=order,
        status=new_status,
        note=note,
        updated_by=actor,
    )
    transaction.on_commit(lambda: send_order_status_email(order.pk, new_status, note))
    return order
