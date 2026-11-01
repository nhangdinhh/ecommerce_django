from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.shortcuts import reverse
from django_countries.fields import CountryField
from decimal import Decimal

# Create your models here.
CATEGORY_CHOICES = (
    ('SB', 'Shirts And Blouses'),
    ('TS', 'T-Shirts'),
    ('SK', 'Skirts'),
    ('HS', 'Hoodies&Sweatshirts')
)

LABEL_CHOICES = (
    ('S', 'sale'),
    ('N', 'new'),
    ('P', 'promotion')
)

ORDER_STATUS_CHOICES = (
    ('pending', 'Order placed'),
    ('confirmed', 'Confirmed'),
    ('packed', 'Packed'),
    ('shipped', 'Shipped'),
    ('delivery_failed', 'Delivery failed'),
    ('returning', 'Returning to shop'),
    ('returned', 'Returned to shop'),
    ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'),
    ('refund_requested', 'Refund requested'),
    ('refunded', 'Refunded'),
)

PAYMENT_METHOD_CHOICES = (
    ('cod', 'Cash on delivery'),
    ('card', 'Card'),
)

PAYMENT_STATUS_CHOICES = (
    ('pending', 'Pending collection'),
    ('paid', 'Paid'),
    ('refunded', 'Refunded'),
    ('cancelled', 'Cancelled'),
)

ADDRESS_CHOICES = (
    ('B', 'Billing'),
    ('S', 'Shipping'),
)


class Slide(models.Model):
    caption1 = models.CharField(max_length=100)
    caption2 = models.CharField(max_length=100)
    link = models.CharField(max_length=100)
    image = models.ImageField(help_text="Size: 1920x570")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return "{} - {}".format(self.caption1, self.caption2)

class Category(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField()
    description = models.TextField()
    image = models.ImageField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("core:category", kwargs={
            'slug': self.slug
        })


class Item(models.Model):
    title = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    label = models.CharField(choices=LABEL_CHOICES, max_length=1)
    slug = models.SlugField(unique=True)
    stock_no = models.CharField(max_length=10)
    stock_quantity = models.PositiveIntegerField(default=10)
    reorder_level = models.PositiveIntegerField(default=5, help_text='Warn staff when total available stock reaches this level.')
    description_short = models.CharField(max_length=50)
    description_long = models.TextField()
    image = models.ImageField()
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=('is_active', 'category'))]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("core:product", kwargs={
            'slug': self.slug
        })

    def get_add_to_cart_url(self):
        return reverse("core:add-to-cart", kwargs={
            'slug': self.slug
        })

    def get_remove_from_cart_url(self):
        return reverse("core:remove-from-cart", kwargs={
            'slug': self.slug
        })

    @property
    def available_stock(self):
        prefetched = getattr(self, '_prefetched_objects_cache', {}).get('variants')
        if prefetched is not None:
            active_variants = [variant for variant in prefetched if variant.is_active]
            if active_variants:
                return sum(variant.stock_quantity for variant in active_variants)
            return self.stock_quantity
        else:
            variants = self.variants.filter(is_active=True)
            if variants.exists():
                return variants.aggregate(total=Sum('stock_quantity'))['total'] or 0
        return self.stock_quantity


class PriceHistory(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='price_history')
    old_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    new_price = models.DecimalField(max_digits=12, decimal_places=2)
    old_discount_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    new_discount_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ('-changed_at', '-pk')
        indexes = [models.Index(fields=('item', 'changed_at'))]

    def __str__(self):
        return f'{self.item.title}: {self.old_price or "New"} → {self.new_price}'


class ItemVariant(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='variants')
    size = models.CharField(max_length=30)
    color = models.CharField(max_length=40)
    sku = models.CharField(max_length=40, unique=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('item__title', 'size', 'color')
        constraints = [
            models.UniqueConstraint(fields=('item', 'size', 'color'), name='core_unique_item_size_color'),
        ]
        indexes = [models.Index(fields=('item', 'is_active'))]

    def __str__(self):
        return f'{self.item.title} · {self.size} · {self.color}'


class ItemImage(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/gallery/')
    alt_text = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('sort_order', 'pk')

    def __str__(self):
        return self.alt_text or f'{self.item.title} photo'


class OrderItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE)
    ordered = models.BooleanField(default=False)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    variant = models.ForeignKey('ItemVariant', on_delete=models.SET_NULL, blank=True, null=True, related_name='order_lines')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return f"{self.quantity} of {self.item.title}"

    def get_total_item_price(self):
        unit_price = self.unit_price if self.unit_price is not None else self.item.price
        return self.quantity * unit_price

    def get_total_discount_item_price(self):
        unit_price = self.unit_price if self.unit_price is not None else (self.item.discount_price or self.item.price)
        return self.quantity * unit_price

    def get_amount_saved(self):
        return (self.get_total_item_price() - self.get_total_discount_item_price()).quantize(Decimal('0.01'))

    def get_final_price(self):
        if self.unit_price is not None:
            return (self.quantity * self.unit_price).quantize(Decimal('0.01'))
        if self.item.discount_price:
            return self.get_total_discount_item_price().quantize(Decimal('0.01'))
        return self.get_total_item_price().quantize(Decimal('0.01'))


class Order(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE)
    ref_code = models.CharField(max_length=20)
    items = models.ManyToManyField(OrderItem)
    start_date = models.DateTimeField(auto_now_add=True)
    ordered_date = models.DateTimeField()
    ordered = models.BooleanField(default=False)
    status = models.CharField(max_length=24, choices=ORDER_STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=12, choices=PAYMENT_METHOD_CHOICES, default='cod')
    payment_status = models.CharField(max_length=12, choices=PAYMENT_STATUS_CHOICES, default='pending')
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    shipping_fee_confirmed = models.BooleanField(default=False)
    shipping_fee_accepted = models.BooleanField(default=False)
    shipping_carrier = models.CharField(max_length=80, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    shipped_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    stock_deducted = models.BooleanField(default=False)
    shipping_address = models.ForeignKey(
        'BillingAddress', related_name='shipping_address', on_delete=models.SET_NULL, blank=True, null=True)
    billing_address = models.ForeignKey(
        'BillingAddress', related_name='billing_address', on_delete=models.SET_NULL, blank=True, null=True)
    payment = models.ForeignKey(
        'Payment', on_delete=models.SET_NULL, blank=True, null=True)
    coupon = models.ForeignKey(
        'Coupon', on_delete=models.SET_NULL, blank=True, null=True)
    being_delivered = models.BooleanField(default=False)
    received = models.BooleanField(default=False)
    refund_requested = models.BooleanField(default=False)
    refund_granted = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=('user', 'ordered_date')),
            models.Index(fields=('status', 'ordered_date')),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=('ref_code',),
                condition=~models.Q(ref_code=''),
                name='core_unique_nonempty_order_ref',
            ),
            models.UniqueConstraint(
                fields=('user',),
                condition=models.Q(ordered=False),
                name='core_one_open_cart_per_user',
            ),
        ]

    '''
    1. Item added to cart
    2. Adding a BillingAddress
    (Failed Checkout)
    3. Payment
    4. Being delivered
    5. Received
    6. Refunds
    '''

    def __str__(self):
        return self.user.username

    def get_items_subtotal(self):
        total = Decimal('0.00')
        for order_item in self.items.all():
            total += order_item.get_final_price()
        return total.quantize(Decimal('0.01'))

    def get_total(self):
        total = self.get_items_subtotal()
        if self.coupon:
            total -= self.coupon.amount
        total = max(Decimal('0.00'), total) + self.shipping_fee
        return total.quantize(Decimal('0.01'))


# models.py

from django.conf import settings
from django.db import models

class BillingAddress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    recipient_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=15, blank=True)
    street_address = models.CharField(max_length=100)
    default = models.BooleanField(default=False)

    def __str__(self):
        return self.recipient_name or self.user.username

    class Meta:
        verbose_name_plural = 'BillingAddresses'


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=24, choices=ORDER_STATUS_CHOICES)
    note = models.CharField(max_length=255, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at', 'id')
        verbose_name_plural = 'Order status history'
        indexes = [models.Index(fields=('order', 'created_at'))]

    def __str__(self):
        return f"{self.order.ref_code}: {self.get_status_display()}"



class Payment(models.Model):
    stripe_charge_id = models.CharField(max_length=50, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.SET_NULL, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=12, choices=PAYMENT_METHOD_CHOICES, default='card')
    status = models.CharField(max_length=12, choices=PAYMENT_STATUS_CHOICES, default='paid')
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.get_method_display()} · {self.amount:.2f}'


class Coupon(models.Model):
    code = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    minimum_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    max_uses = models.PositiveIntegerField(blank=True, null=True)
    use_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.code


class StockMovement(models.Model):
    REASON_CHOICES = (
        ('order', 'Reserved for order'),
        ('cancellation', 'Released after cancellation'),
        ('adjustment', 'Manual stock adjustment'),
        ('purchase', 'Received from supplier'),
        ('refund_return', 'Returned after refund'),
        ('delivery_return', 'Returned after failed delivery'),
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='stock_movements')
    variant = models.ForeignKey(ItemVariant, on_delete=models.PROTECT, blank=True, null=True, related_name='stock_movements')
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, blank=True, null=True, related_name='stock_movements')
    quantity_change = models.IntegerField(help_text='Negative when stock is reserved; positive when it is returned.')
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-id')
        indexes = [models.Index(fields=('item', 'created_at'))]

    def __str__(self):
        return f'{self.item.title}: {self.quantity_change:+d}'


class Refund(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    reason = models.TextField()
    accepted = models.BooleanField(default=False)
    email = models.EmailField()
    items_received = models.BooleanField(default=False, help_text='Confirm the returned parcel has physically arrived at the shop.')
    restocked = models.BooleanField(default=False)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='processed_refunds')
    processed_at = models.DateTimeField(blank=True, null=True)
    rejected = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True)
    refund_method = models.CharField(max_length=20, blank=True, choices=(('cash', 'Cash'), ('bank_transfer', 'Bank transfer')))
    refund_reference = models.CharField(max_length=100, blank=True)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    refunded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='completed_refunds')
    refunded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('order',), name='core_one_refund_per_order'),
        ]

    def __str__(self):
        return f"{self.pk}"

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def __str__(self):
        return self.user.username

class Wishlist(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    items = models.ManyToManyField(Item, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Wishlist"

class Review(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    comment = models.TextField()
    photo = models.ImageField(upload_to='reviews/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def verified_purchase(self):
        return Order.objects.filter(
            user=self.user,
            ordered=True,
            status__in=('delivered', 'refund_requested', 'refunded'),
            items__item=self.item,
        ).exists()

    def __str__(self):
        return f"{self.user.username} - {self.item.title} - {self.rating} Stars"


class Supplier(models.Model):
    name = models.CharField(max_length=150, unique=True)
    contact_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class StockReceipt(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='receipts')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='receipts')
    variant = models.ForeignKey(ItemVariant, on_delete=models.PROTECT, blank=True, null=True, related_name='receipts')
    reference = models.CharField(max_length=80, blank=True, db_index=True)
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    received_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ('-received_at', '-pk')

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.quantity < 1:
            raise ValidationError({'quantity': 'Enter a quantity greater than zero.'})
        if self.variant_id and self.item_id and self.variant.item_id != self.item_id:
            raise ValidationError({'variant': 'The selected SKU does not belong to this product.'})
        if self.unit_cost < 0:
            raise ValidationError({'unit_cost': 'Unit cost cannot be negative.'})

    @property
    def total_cost(self):
        return (self.unit_cost * self.quantity).quantize(Decimal('0.01'))

    def __str__(self):
        sku = f' · {self.variant.sku}' if self.variant_id else ''
        return f'{self.reference or "Receipt"} · {self.item.title}{sku} · +{self.quantity}'

