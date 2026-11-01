import random
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from core.models import (
    BillingAddress,
    Category,
    Coupon,
    Item,
    ItemVariant,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    PriceHistory,
    Refund,
    Review,
    StockMovement,
    StockReceipt,
    Supplier,
    UserProfile,
)


SIZES = {
    'shoes': ('36', '37', '38', '39', '40', '41'),
    'bags': ('One Size',),
    'watches': ('One Size',),
}
COLORS = ('Oat', 'Stone', 'Black', 'Navy')
FIRST_NAMES = ('An', 'Bình', 'Chi', 'Dũng', 'Hà', 'Linh', 'Minh', 'Ngọc', 'Phúc', 'Quỳnh', 'Thảo', 'Vy')
LAST_NAMES = ('Nguyễn', 'Trần', 'Lê', 'Phạm', 'Hoàng', 'Phan', 'Vũ', 'Đặng')
CITIES = ('Ho Chi Minh City', 'Hanoi', 'Da Nang', 'Can Tho', 'Hai Phong', 'Nha Trang')
REVIEW_TEXTS = (
    'The fit is comfortable and the finish feels thoughtfully made.',
    'Exactly as pictured, and easy to style for everyday wear.',
    'A lovely wardrobe staple. The sizing worked well for me.',
    'Good value and the details are even nicer in person.',
    'Arrived in good condition and has quickly become a favourite.',
    'The color is versatile and the overall look is very polished.',
    'Comfortable from the first wear. I would order this style again.',
    'A simple, well-balanced piece that goes with many outfits.',
)

STATUS_PATHS = {
    'pending': ('pending',),
    'confirmed': ('pending', 'confirmed'),
    'packed': ('pending', 'confirmed', 'packed'),
    'shipped': ('pending', 'confirmed', 'packed', 'shipped'),
    'delivered': ('pending', 'confirmed', 'packed', 'shipped', 'delivered'),
    'cancelled': ('pending', 'confirmed', 'cancelled'),
    'delivery_failed': ('pending', 'confirmed', 'packed', 'shipped', 'delivery_failed'),
    'returning': ('pending', 'confirmed', 'packed', 'shipped', 'delivery_failed', 'returning'),
    'returned': ('pending', 'confirmed', 'packed', 'shipped', 'delivery_failed', 'returning', 'returned'),
    'refund_requested': ('pending', 'confirmed', 'packed', 'shipped', 'delivered', 'refund_requested'),
    'refunded': ('pending', 'confirmed', 'packed', 'shipped', 'delivered', 'refund_requested', 'refunded'),
}


def database_size_bytes():
    if connection.vendor == 'sqlite':
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA wal_checkpoint(FULL)')
            cursor.execute('PRAGMA page_count')
            pages = cursor.fetchone()[0]
            cursor.execute('PRAGMA page_size')
            page_size = cursor.fetchone()[0]
        return pages * page_size
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_database_size(current_database())')
            return cursor.fetchone()[0]
    raise CommandError('This command supports SQLite and PostgreSQL databases.')


def make_user(username, index):
    User = get_user_model()
    first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
    last_name = LAST_NAMES[(index // len(FIRST_NAMES)) % len(LAST_NAMES)]
    user = User(
        username=username,
        email=f'{username}@example.test',
        first_name=first_name,
        last_name=last_name,
        is_active=True,
    )
    user.set_unusable_password()
    return user


class Command(BaseCommand):
    help = 'Create clearly marked, repeatable ecommerce demo records until the database reaches a target size.'

    def add_arguments(self, parser):
        parser.add_argument('--target-mb', type=float, default=100, help='Target total database size in decimal MB (default: 100).')
        parser.add_argument('--batch-size', type=int, default=1000, help='Orders added per transaction (default: 1000).')
        parser.add_argument('--max-orders', type=int, default=200000, help='Safety limit for new orders in this run.')

    def handle(self, *args, **options):
        if connection.vendor not in {'sqlite', 'postgresql'}:
            raise CommandError('Use SQLite locally or PostgreSQL on the server.')
        target_bytes = int(options['target_mb'] * 1_000_000)
        batch_size = options['batch_size']
        max_orders = options['max_orders']
        if target_bytes <= 0 or batch_size <= 0 or max_orders <= 0:
            raise CommandError('Target size, batch size, and order limit must all be positive.')

        rng = random.Random(20261027)
        User = get_user_model()
        users = self._ensure_customers(User)
        variants, products = self._ensure_demo_catalog()
        if not users or not variants:
            raise CommandError('Could not prepare demo customers and product variants.')
        self._ensure_demo_inventory_and_prices(variants, products)

        coupon, _ = Coupon.objects.get_or_create(
            code='DEMO-SAVE10',
            defaults={
                'amount': Decimal('10.00'),
                'minimum_order_amount': Decimal('45.00'),
                'is_active': False,
            },
        )
        current_size = database_size_bytes()
        existing_demo_orders = Order.objects.filter(ref_code__startswith='DMD').count()
        self.stdout.write(f'Database: {current_size / 1_000_000:.2f} MB; demo orders already present: {existing_demo_orders}.')
        if current_size >= target_bytes:
            self.stdout.write(self.style.SUCCESS('The database already meets the requested size; no orders were added.'))
            return

        added = 0
        while current_size < target_bytes and added < max_orders:
            count = min(batch_size, max_orders - added)
            first_sequence = existing_demo_orders + added + 1
            batch_count = self._create_order_batch(
                users=users,
                variants=variants,
                products=products,
                coupon=coupon,
                first_sequence=first_sequence,
                count=count,
                rng=rng,
            )
            added += batch_count
            current_size = database_size_bytes()
            self.stdout.write(f'Added {added:,} orders this run; database is {current_size / 1_000_000:.2f} MB.')

        if current_size < target_bytes:
            self.stdout.write(self.style.WARNING(
                f'Safety limit reached after {added:,} orders; database is {current_size / 1_000_000:.2f} MB, '
                f'below the {options["target_mb"]:.0f} MB target. Re-run the command to continue.'
            ))
            return
        self.stdout.write(self.style.SUCCESS(
            f'Demo data is ready: {current_size / 1_000_000:.2f} MB total, '
            f'{existing_demo_orders + added:,} demo orders, and {len(users):,} demo customers.'
        ))

    def _ensure_customers(self, User):
        existing = list(User.objects.filter(username__startswith='demo_buyer_').order_by('username'))
        target_customers = 2500
        if len(existing) < target_customers:
            new_users = [
                make_user(f'demo_buyer_{number:06d}', number)
                for number in range(len(existing) + 1, target_customers + 1)
            ]
            User.objects.bulk_create(new_users, batch_size=1000)
            existing = list(User.objects.filter(username__startswith='demo_buyer_').order_by('username'))
            UserProfile.objects.bulk_create([
                UserProfile(
                    user=user,
                    phone=f'+849000{index % 100000:05d}',
                    address='Demo address on file',
                )
                for index, user in enumerate(existing, 1)
            ], batch_size=1000, ignore_conflicts=True)
        return existing

    def _ensure_demo_catalog(self):
        categories = list(Category.objects.filter(is_active=True).order_by('pk'))
        if not categories:
            raise CommandError('Add at least one active category before creating demo orders.')
        source_by_category = {}
        for item in Item.objects.filter(category__in=categories).order_by('pk'):
            source_by_category.setdefault(item.category_id, item)
        if not source_by_category:
            raise CommandError('Add at least one product with an image before creating demo orders.')

        products = []
        for index in range(1, 31):
            category = categories[(index - 1) % len(categories)]
            source = source_by_category.get(category.pk) or next(iter(source_by_category.values()))
            item, _ = Item.objects.get_or_create(
                slug=f'demo-catalog-{index:03d}',
                defaults={
                    'title': f'Demo {category.title} Essential {index:02d}',
                    'price': source.price,
                    'discount_price': source.discount_price,
                    'category': category,
                    'label': source.label,
                    'stock_no': f'DM{index:08d}',
                    'stock_quantity': 0,
                    'description_short': 'Inactive sample item for order workflow demos',
                    'description_long': 'Synthetic, inactive sample catalog entry. Used only for clearly identified local order, inventory, payment, delivery, and refund demonstrations.',
                    'image': source.image.name,
                    'is_active': False,
                },
            )
            products.append(item)
            category_key = category.slug.lower()
            sizes = SIZES.get(category_key, ('XS', 'S', 'M', 'L', 'XL'))
            desired = [
                ItemVariant(
                    item=item,
                    size=size,
                    color=color,
                    sku=f'DVAR{index:03d}{size_index:02d}{color_index:02d}',
                    stock_quantity=5_000,
                )
                for size_index, size in enumerate(sizes, 1)
                for color_index, color in enumerate(COLORS, 1)
            ]
            existing_skus = set(ItemVariant.objects.filter(item=item).values_list('sku', flat=True))
            ItemVariant.objects.bulk_create(
                [variant for variant in desired if variant.sku not in existing_skus],
                batch_size=1000,
                ignore_conflicts=True,
            )

        variants = list(ItemVariant.objects.filter(item__slug__startswith='demo-catalog-', is_active=True).select_related('item'))
        products_by_id = {product.pk: product for product in products}
        return variants, products_by_id

    def _ensure_demo_inventory_and_prices(self, variants, products):
        supplier, _ = Supplier.objects.get_or_create(
            name='Demo Order Workflow Supplier',
            defaults={
                'contact_name': 'Sample Supplier',
                'email': 'demo-supplier@example.test',
                'phone': '+84900000001',
                'notes': 'Synthetic supplier record used only for local order workflow demonstrations.',
                'is_active': False,
            },
        )
        price_rows = []
        for product in products.values():
            if not PriceHistory.objects.filter(item=product, note='Demo price history entry; sample only.').exists():
                previous_price = (product.price * Decimal('0.90')).quantize(Decimal('0.01'))
                price_rows.append(PriceHistory(
                    item=product,
                    old_price=previous_price,
                    new_price=product.price,
                    new_discount_price=product.discount_price,
                    note='Demo price history entry; sample only.',
                ))
        PriceHistory.objects.bulk_create(price_rows, batch_size=500)

        receipts = []
        movements = []
        for variant in variants:
            reference = f'DEMO-OPEN-{variant.sku}'
            if StockReceipt.objects.filter(reference=reference).exists():
                continue
            quantity = variant.stock_quantity
            if quantity <= 0:
                continue
            unit_cost = (variant.item.price * Decimal('0.45')).quantize(Decimal('0.01'))
            receipts.append(StockReceipt(
                supplier=supplier,
                item=variant.item,
                variant=variant,
                reference=reference,
                quantity=quantity,
                unit_cost=unit_cost,
                note='Opening sample stock for inactive demo catalog; not a real supplier purchase.',
            ))
            movements.append(StockMovement(
                item=variant.item,
                variant=variant,
                quantity_change=quantity,
                reason='purchase',
                note='Demo opening stock ledger entry matching the sample receipt.',
            ))
        StockReceipt.objects.bulk_create(receipts, batch_size=1000)
        StockMovement.objects.bulk_create(movements, batch_size=1000)

    def _create_order_batch(self, users, variants, products, coupon, first_sequence, count, rng):
        now = timezone.now()
        orders_data = []
        address_records = []
        payment_records = []
        payment_dates = []
        history_records = []
        history_dates = []
        line_records = []
        lines_by_order = []
        refund_records = []
        movement_payloads = []
        stock_delta = defaultdict(int)
        state_counts = Counter()
        coupon_uses = 0
        user_count = len(users)
        colors = ('GHN', 'GHTK', 'J&T Express', 'VNPost')

        for offset in range(count):
            sequence = first_sequence + offset
            user = users[(sequence - 1) % user_count]
            bucket = sequence % 100
            if bucket < 44:
                status = 'delivered'
            elif bucket < 55:
                status = 'shipped'
            elif bucket < 62:
                status = 'packed'
            elif bucket < 68:
                status = 'confirmed'
            elif bucket < 72:
                status = 'pending'
            elif bucket < 81:
                status = 'cancelled'
            elif bucket < 86:
                status = 'delivery_failed'
            elif bucket < 90:
                status = 'returning'
            elif bucket < 94:
                status = 'returned'
            elif bucket < 98:
                status = 'refund_requested'
            else:
                status = 'refunded'
            state_counts[status] += 1
            placed_at = now - timedelta(days=30 + (sequence * 37) % 700)
            path = STATUS_PATHS[status]
            shipped = status in {'shipped', 'delivered', 'delivery_failed', 'returning', 'returned', 'refund_requested', 'refunded'}
            delivered = status in {'delivered', 'refund_requested', 'refunded'}
            shipping_fee = Decimal('0.00') if sequence % 4 == 0 else Decimal('5.95')
            is_coupon_order = sequence % 10 == 0

            selected_variants = rng.sample(variants, k=min(rng.randint(2, 5), len(variants)))
            lines = []
            subtotal = Decimal('0.00')
            for variant in selected_variants:
                product = products[variant.item_id]
                quantity = rng.randint(1, 3)
                unit_price = product.discount_price or product.price
                subtotal += unit_price * quantity
                line = OrderItem(
                    user=user,
                    ordered=True,
                    item=product,
                    variant=variant,
                    quantity=quantity,
                    unit_price=unit_price,
                )
                lines.append((line, variant, product, quantity))
                stock_delta[variant.pk] += quantity if status not in {'cancelled', 'returned', 'refunded'} else 0
            subtotal = subtotal.quantize(Decimal('0.01'))
            discount = coupon.amount if is_coupon_order and subtotal >= coupon.minimum_order_amount else Decimal('0.00')
            coupon_for_order = coupon if discount else None
            if coupon_for_order:
                coupon_uses += 1
            total = max(Decimal('0.00'), subtotal - discount) + shipping_fee
            payment_status = {
                'delivered': 'paid',
                'refund_requested': 'paid',
                'refunded': 'refunded',
                'cancelled': 'cancelled',
                'returned': 'cancelled',
            }.get(status, 'pending')
            address = BillingAddress(
                user=user,
                recipient_name=f'{user.first_name} {user.last_name}',
                phone_number=f'+849000{sequence % 100000:05d}',
                street_address=f'{(sequence % 250) + 1} Demo Street, Ward {(sequence % 12) + 1}, {CITIES[sequence % len(CITIES)]}',
                default=False,
            )
            address_records.append(address)
            payment = Payment(
                user=user,
                amount=total,
                method='cod',
                status=payment_status,
            )
            payment_records.append(payment)
            payment_dates.append(placed_at + timedelta(days=4) if delivered else placed_at)
            tracking = f'DEMO-{sequence:010d}' if shipped else ''
            order = Order(
                user=user,
                ref_code=f'DMD{sequence:010d}',
                ordered_date=placed_at,
                ordered=True,
                status=status,
                payment_method='cod',
                payment_status=payment_status,
                shipping_fee=shipping_fee,
                shipping_fee_confirmed=shipped,
                shipping_carrier=colors[sequence % len(colors)] if shipped else '',
                tracking_number=tracking,
                shipped_at=placed_at + timedelta(days=3) if shipped else None,
                delivered_at=placed_at + timedelta(days=4) if delivered else None,
                stock_deducted=status not in {'cancelled', 'returned'},
                coupon=coupon_for_order,
                being_delivered=status == 'shipped',
                received=status == 'delivered',
                refund_requested=status == 'refund_requested',
                refund_granted=status == 'refunded',
            )
            orders_data.append((order, address, payment, placed_at, path, lines, status, sequence))
            lines_by_order.append(lines)

        with transaction.atomic():
            BillingAddress.objects.bulk_create(address_records, batch_size=1000)
            Payment.objects.bulk_create(payment_records, batch_size=1000)
            for record in address_records + payment_records:
                if record.pk is None:
                    raise CommandError('The selected database did not return ids for bulk-created rows.')
            for payment, timestamp in zip(payment_records, payment_dates):
                payment.timestamp = timestamp
            Payment.objects.bulk_update(payment_records, ('timestamp',), batch_size=1000)

            order_objects = [entry[0] for entry in orders_data]
            Order.objects.bulk_create(order_objects, batch_size=500)
            if any(order.pk is None for order in order_objects):
                raise CommandError('The selected database did not return order ids for bulk-created rows.')

            for order, address, payment, placed_at, path, lines, status, sequence in orders_data:
                order.start_date = placed_at
                order.shipping_address_id = address.pk
                order.billing_address_id = address.pk
                order.payment_id = payment.pk
            Order.objects.bulk_update(order_objects, ('start_date', 'shipping_address', 'billing_address', 'payment'), batch_size=500)

            flat_lines = [line for batch in lines_by_order for line, variant, product, quantity in batch]
            OrderItem.objects.bulk_create(flat_lines, batch_size=1000)
            if any(line.pk is None for line in flat_lines):
                raise CommandError('The selected database did not return ids for order lines.')

            through = Order.items.through
            order_field = Order._meta.get_field('items').m2m_field_name()
            line_field = Order._meta.get_field('items').m2m_reverse_field_name()
            through_rows = []
            for entry, lines in zip(orders_data, lines_by_order):
                order = entry[0]
                for line, variant, product, quantity in lines:
                    through_rows.append(through(**{f'{order_field}_id': order.pk, f'{line_field}_id': line.pk}))
                    movement_payloads.append((order, line, variant, product, quantity, entry[3], entry[6]))
            through.objects.bulk_create(through_rows, batch_size=1000)

            for order, address, payment, placed_at, path, lines, status, sequence in orders_data:
                for step, event_status in enumerate(path):
                    history_records.append(OrderStatusHistory(
                        order=order,
                        status=event_status,
                        note=f'Demo timeline: {dict(Order._meta.get_field("status").choices).get(event_status, event_status)}.',
                    ))
                    history_dates.append(placed_at + timedelta(days=min(step, 5)))
                if status in {'refund_requested', 'refunded'}:
                    refund_records.append(Refund(
                        order=order,
                        reason='Demo return request for order workflow demonstration.',
                        accepted=status == 'refunded',
                        email=order.user.email,
                        items_received=status == 'refunded',
                        restocked=status == 'refunded',
                    ))

            OrderStatusHistory.objects.bulk_create(history_records, batch_size=1000)
            for entry, created_at in zip(history_records, history_dates):
                entry.created_at = created_at
            OrderStatusHistory.objects.bulk_update(history_records, ('created_at',), batch_size=1000)
            Refund.objects.bulk_create(refund_records, batch_size=1000)

            movement_records = []
            movement_dates = []
            for order, line, variant, product, quantity, placed_at, status in movement_payloads:
                movement_records.append(StockMovement(
                    item=product,
                    variant=variant,
                    order=order,
                    quantity_change=-quantity,
                    reason='order',
                    note='Demo order stock reservation.',
                    created_by=None,
                ))
                movement_dates.append(placed_at)
                if status == 'cancelled':
                    movement_records.append(StockMovement(
                        item=product,
                        variant=variant,
                        order=order,
                        quantity_change=quantity,
                        reason='cancellation',
                        note='Demo cancellation released reserved stock.',
                        created_by=None,
                    ))
                    movement_dates.append(placed_at + timedelta(days=1))
                elif status == 'refunded':
                    movement_records.append(StockMovement(
                        item=product,
                        variant=variant,
                        order=order,
                        quantity_change=quantity,
                        reason='refund_return',
                        note='Demo returned units restored to sample inventory.',
                        created_by=None,
                    ))
                    movement_dates.append(placed_at + timedelta(days=6))
                elif status == 'returned':
                    movement_records.append(StockMovement(
                        item=product,
                        variant=variant,
                        order=order,
                        quantity_change=quantity,
                        reason='delivery_return',
                        note='Demo failed-delivery return restored to sample inventory.',
                        created_by=None,
                    ))
                    movement_dates.append(placed_at + timedelta(days=6))
            StockMovement.objects.bulk_create(movement_records, batch_size=1000)
            for movement, created_at in zip(movement_records, movement_dates):
                movement.created_at = created_at
            StockMovement.objects.bulk_update(movement_records, ('created_at',), batch_size=1000)

            variant_by_id = {variant.pk: variant for variant in variants}
            for variant_id, quantity in stock_delta.items():
                variant_by_id[variant_id].stock_quantity -= quantity
            ItemVariant.objects.bulk_update(variants, ('stock_quantity',), batch_size=1000)

            review_records = []
            review_indices = []
            for order, address, payment, placed_at, path, lines, status, sequence in orders_data:
                if status == 'delivered' and sequence % 3 == 0:
                    line, variant, product, quantity = lines[0]
                    review_records.append(Review(
                        user=order.user,
                        item=product,
                        rating=5 if sequence % 4 else 4,
                        comment=REVIEW_TEXTS[sequence % len(REVIEW_TEXTS)],
                    ))
                    review_indices.append(placed_at + timedelta(days=5))
            Review.objects.bulk_create(review_records, batch_size=1000)
            for review, created_at in zip(review_records, review_indices):
                review.created_at = created_at
            Review.objects.bulk_update(review_records, ('created_at',), batch_size=1000)

            if coupon_uses:
                Coupon.objects.filter(pk=coupon.pk).update(use_count=coupon.use_count + coupon_uses)
                coupon.use_count += coupon_uses

        return count
