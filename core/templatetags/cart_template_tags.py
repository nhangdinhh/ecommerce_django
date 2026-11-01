from django import template
from core.models import Order

register = template.Library()


@register.filter
def cart_item_count(user):
    if user.is_authenticated:
        order = Order.objects.filter(user=user, ordered=False).prefetch_related('items').first()
        if order:
            return sum(line.quantity for line in order.items.all())
    return 0
