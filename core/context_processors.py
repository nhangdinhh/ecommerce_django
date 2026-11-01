from .models import Order


def shopping_cart(request):
    """Expose the signed-in customer's real open cart to the shared header."""
    order = None
    items = []
    if request.user.is_authenticated:
        order = (
            Order.objects.filter(user=request.user, ordered=False)
            .prefetch_related('items__item', 'items__item__category')
            .first()
        )
        if order:
            items = list(order.items.all())

    return {
        'shopping_cart': order,
        'shopping_cart_items': items,
        'shopping_cart_count': sum(line.quantity for line in items),
    }
