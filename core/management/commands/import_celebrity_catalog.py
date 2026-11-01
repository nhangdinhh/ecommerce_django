import csv
from collections import defaultdict, deque
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from core.models import (
    Category,
    Item,
    ItemVariant,
    PriceHistory,
    StockMovement,
    StockReceipt,
    Supplier,
)


CATEGORY_COPY = {
    'bags': ('A Seoul-inspired bag for everyday plans.', 'A polished Korean fashion campaign look, selected for everyday styling and versatile wear.'),
    'dresses': ('A refined dress with an easy, polished shape.', 'A Korean fashion campaign look with an elegant silhouette for everyday plans and special occasions.'),
    'pants': ('An easy trouser shape for versatile styling.', 'A Korean fashion campaign look with a versatile fit for relaxed and polished outfits.'),
    'shirts': ('A versatile top for simple everyday outfits.', 'A Korean fashion campaign look that layers easily and pairs with everyday wardrobe pieces.'),
    'shoes': ('A considered shoe style for everyday wear.', 'A Korean fashion campaign look selected for comfortable, versatile styling across the week.'),
    'watches': ('A polished accessory for everyday wear.', 'A Korean fashion campaign look with a refined accessory chosen to complement everyday outfits.'),
}

SIZES = {
    'dresses': ('XS', 'S', 'M', 'L', 'XL'),
    'pants': ('XS', 'S', 'M', 'L', 'XL'),
    'shirts': ('XS', 'S', 'M', 'L', 'XL'),
    'shoes': ('36', '37', '38', '39', '40', '41'),
    'bags': ('One Size',),
    'watches': ('One Size',),
}
COLORS = ('Black', 'Ivory', 'Navy')
BASE_PRICES = {
    'bags': Decimal('58.00'),
    'dresses': Decimal('68.00'),
    'pants': Decimal('52.00'),
    'shirts': Decimal('34.00'),
    'shoes': Decimal('61.00'),
    'watches': Decimal('88.00'),
}


class Command(BaseCommand):
    help = 'Import a balanced catalog with distinct Korean fashion campaign images.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100, help='Target total imported catalog products (default: 100).')

    @transaction.atomic
    def handle(self, *args, **options):
        target_count = options['count']
        if target_count < 1:
            raise CommandError('--count must be greater than zero.')

        csv_path = Path(settings.MEDIA_ROOT) / 'KOREAN_CELEBRITY_CATALOG_SOURCES.csv'
        if not csv_path.is_file():
            raise CommandError(f'Catalog source file is missing: {csv_path}')

        categories = {
            category.slug.casefold(): category
            for category in Category.objects.filter(is_active=True)
        }
        missing_categories = sorted(set(CATEGORY_COPY) - set(categories))
        if missing_categories:
            raise CommandError(f'Missing active categories: {", ".join(missing_categories)}')

        existing_import_count = Item.objects.filter(stock_no__startswith='KCAT').count()
        additional_count = max(0, target_count - existing_import_count)
        if additional_count == 0:
            self.stdout.write(self.style.SUCCESS(
                f'Imported catalog already has {existing_import_count} products; nothing to add.'
            ))
            return

        used_images = set(Item.objects.exclude(image='').values_list('image', flat=True))
        used_slugs = set(Item.objects.values_list('slug', flat=True))
        by_category = defaultdict(list)
        with csv_path.open(encoding='utf-8-sig', newline='') as source_file:
            for row in csv.DictReader(source_file):
                category_key = slugify(row.get('category', '')).casefold()
                image_name = (row.get('local_image') or '').strip().replace('\\', '/')
                title = (row.get('product_title') or '').strip()
                slug = slugify(title)
                image_path = Path(settings.MEDIA_ROOT) / image_name
                if category_key not in CATEGORY_COPY or not title or not image_name:
                    continue
                if not image_path.is_file():
                    raise CommandError(f'Catalog image is missing: {image_path}')
                if image_name in used_images or slug in used_slugs:
                    continue
                by_category[category_key].append({
                    'id': int(row['product_id']),
                    'title': title,
                    'slug': slug,
                    'image': image_name,
                })
                used_images.add(image_name)
                used_slugs.add(slug)

        queues = {key: deque(rows) for key, rows in by_category.items()}
        selected = []
        category_order = tuple(CATEGORY_COPY)
        while len(selected) < additional_count:
            progressed = False
            for key in category_order:
                if queues.get(key):
                    selected.append((key, queues[key].popleft()))
                    progressed = True
                    if len(selected) == additional_count:
                        break
            if not progressed:
                raise CommandError(
                    f'Only {len(selected)} unused catalog images are available; '
                    f'{additional_count} additional products were requested.'
                )

        supplier, _ = Supplier.objects.get_or_create(
            name='Nhang Shop Catalog Opening Stock',
            defaults={
                'contact_name': 'Catalog team',
                'email': 'catalog@example.test',
                'notes': 'Opening stock for the imported coursework catalog.',
                'is_active': False,
            },
        )

        items_added = 0
        variants_to_create = []
        histories = []
        receipts = []
        movements = []
        for category_key, product in selected:
            source_id = product['id']
            price = BASE_PRICES[category_key] + Decimal((source_id * 7) % 31)
            quantity = 24 + ((source_id * 11) % 13)
            short_description, long_description = CATEGORY_COPY[category_key]
            item = Item.objects.create(
                title=product['title'][:100],
                price=price,
                category=categories[category_key],
                label='N',
                slug=product['slug'],
                stock_no=f'KCAT{source_id:06d}',
                stock_quantity=quantity,
                reorder_level=4,
                description_short=short_description[:50],
                description_long=f'{product["title"]}. {long_description}',
                image=product['image'],
                is_active=True,
            )
            items_added += 1
            histories.append(PriceHistory(
                item=item,
                old_price=None,
                new_price=price,
                note='Initial price for imported Korean fashion catalog item.',
            ))

            combinations = [
                (size, color)
                for size in SIZES[category_key]
                for color in COLORS
            ]
            base_stock, remainder = divmod(quantity, len(combinations))
            for index, (size, color) in enumerate(combinations, start=1):
                variant_stock = base_stock + (1 if index <= remainder else 0)
                variant = ItemVariant(
                    item=item,
                    size=size,
                    color=color,
                    sku=f'KCAT{source_id:06d}-{index:02d}',
                    stock_quantity=variant_stock,
                    reorder_level=2,
                )
                variants_to_create.append(variant)
                if variant_stock:
                    reference = f'OPEN-KCAT{source_id:06d}-{index:02d}'
                    unit_cost = (price * Decimal('0.45')).quantize(Decimal('0.01'))
                    receipts.append(StockReceipt(
                        supplier=supplier,
                        item=item,
                        variant=variant,
                        reference=reference,
                        quantity=variant_stock,
                        unit_cost=unit_cost,
                        note='Opening stock for imported catalog item.',
                    ))
                    movements.append(StockMovement(
                        item=item,
                        variant=variant,
                        quantity_change=variant_stock,
                        reason='purchase',
                        note='Opening balance for imported catalog item.',
                    ))

        ItemVariant.objects.bulk_create(variants_to_create, batch_size=1000)
        PriceHistory.objects.bulk_create(histories, batch_size=500)
        StockReceipt.objects.bulk_create(receipts, batch_size=1000)
        StockMovement.objects.bulk_create(movements, batch_size=1000)
        self.stdout.write(self.style.SUCCESS(
            f'Added {items_added} active products with {items_added} distinct catalog images, '
            f'{len(variants_to_create)} variants, and {len(receipts)} opening stock records.'
        ))
        for key in category_order:
            self.stdout.write(f'{categories[key].title}: {Item.objects.filter(category=categories[key], is_active=True).count()} active products')
