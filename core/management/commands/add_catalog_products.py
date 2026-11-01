from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from core.models import Category, Item


PRODUCTS = (
    {
        'title': 'Metro Everyday Backpack', 'category': 'bags', 'image': 'kfashion/bag_korean_backpack_1.jpg',
        'price': '68.00', 'stock_no': 'NS-BG-008', 'stock_quantity': 12,
        'description_short': 'A practical bag for everyday plans.',
        'description_long': 'A clean, easy-to-style backpack for commuting, errands, and weekend plans. Its understated shape pairs naturally with everyday outfits.',
    },
    {
        'title': 'Lightweight City Backpack', 'category': 'bags', 'image': 'kfashion/bag_korean_backpack_2.jpg',
        'price': '54.50', 'stock_no': 'NS-BG-009', 'stock_quantity': 10,
        'description_short': 'A light carry-all with a relaxed look.',
        'description_long': 'A relaxed everyday backpack with a simple silhouette and room for the essentials. Made for an easy transition from weekday errands to short trips.',
    },
    {
        'title': 'Midnight Statement Dress', 'category': 'dresses', 'image': 'kfashion/dress_korean_black.jpg',
        'price': '62.00', 'stock_no': 'NS-DR-008', 'stock_quantity': 10,
        'description_short': 'An elegant black dress for evenings out.',
        'description_long': 'A polished black dress with a graceful, occasion-ready silhouette. Style it with understated accessories for dinners, celebrations, and evening events.',
    },
    {
        'title': 'Soft-Neutral Knit Dress', 'category': 'dresses', 'image': 'kfashion/dress_korean_ivory.jpg',
        'price': '57.00', 'stock_no': 'NS-DR-009', 'stock_quantity': 10,
        'description_short': 'A soft neutral look for easy dressing.',
        'description_long': 'A softly tailored neutral dress designed for simple, versatile styling. Wear it on its own or layer it with your favourite everyday pieces.',
    },
    {
        'title': 'Everyday Jogger Trousers', 'category': 'pants', 'image': 'kfashion/pants_korean_jogger.jpg',
        'price': '42.00', 'stock_no': 'NS-PT-008', 'stock_quantity': 14,
        'description_short': 'Comfortable trousers with a sporty feel.',
        'description_long': 'Relaxed jogger-style trousers for casual days and travel. Their streamlined shape makes them easy to pair with tees, shirts, and sneakers.',
    },
    {
        'title': 'Essential Straight-Leg Denim', 'category': 'pants', 'image': 'kfashion/pants_korean_denim.jpg',
        'price': '49.00', 'stock_no': 'NS-PT-009', 'stock_quantity': 12,
        'description_short': 'A versatile denim shape for every day.',
        'description_long': 'A classic straight-leg denim look that works across seasons. Pair it with a crisp shirt or a simple tee for an effortless everyday outfit.',
    },
    {
        'title': 'Classic Crew-Neck Tee', 'category': 'shirts', 'image': 'kfashion/shirt_korean_tee.jpg',
        'price': '24.00', 'stock_no': 'NS-SH-008', 'stock_quantity': 18,
        'description_short': 'A simple tee for everyday layering.',
        'description_long': 'A straightforward crew-neck tee with an easy, versatile look. Wear it on its own or layer it under shirts and light jackets.',
    },
    {
        'title': 'Relaxed Rugby Polo', 'category': 'shirts', 'image': 'kfashion/shirt_korean_polo.jpg',
        'price': '38.00', 'stock_no': 'NS-SH-009', 'stock_quantity': 12,
        'description_short': 'A casual polo with a sporty finish.',
        'description_long': 'A relaxed polo-inspired top that brings a sporty note to casual outfits. It pairs easily with denim, trousers, or simple skirts.',
    },
    {
        'title': 'Everyday White Button-Up', 'category': 'shirts', 'image': 'kfashion/shirt_korean_buttonup.jpg',
        'price': '45.00', 'stock_no': 'NS-SH-010', 'stock_quantity': 10,
        'description_short': 'A crisp shirt for work or the weekend.',
        'description_long': 'A clean white button-up with a versatile, easy-to-layer look. Style it tucked into trousers, worn open over a tee, or with denim.',
    },
    {
        'title': 'Retro Court Sneakers', 'category': 'shoes', 'image': 'kfashion/shoes_korean_court.jpg',
        'price': '59.00', 'stock_no': 'NS-SC-008', 'stock_quantity': 12,
        'description_short': 'A bright retro-inspired sneaker style.',
        'description_long': 'A playful retro sneaker look for relaxed outfits and everyday walks. The bright styling adds a fresh accent to simple wardrobe staples.',
    },
    {
        'title': 'Classic High-Top Sneakers', 'category': 'shoes', 'image': 'kfashion/shoes_korean_hightop.jpg',
        'price': '64.00', 'stock_no': 'NS-SC-009', 'stock_quantity': 12,
        'description_short': 'A timeless high-top for casual wear.',
        'description_long': 'A classic high-top sneaker with an easy-to-style profile. Wear it with denim, relaxed trousers, or weekend essentials.',
    },
    {
        'title': 'Everyday Running Trainers', 'category': 'shoes', 'image': 'kfashion/shoes_korean_running.jpg',
        'price': '72.00', 'stock_no': 'NS-SC-010', 'stock_quantity': 10,
        'description_short': 'A sporty trainer for active days.',
        'description_long': 'A sporty running-inspired shoe for active days and casual outfits. Its streamlined look works well with athleisure and everyday basics.',
    },
    {
        'title': 'Everyday Leather Loafers', 'category': 'shoes', 'image': 'kfashion/shoes_korean_loafers.jpg',
        'price': '58.00', 'stock_no': 'NS-SC-011', 'stock_quantity': 8,
        'description_short': 'An understated shoe for polished looks.',
        'description_long': 'A refined, understated shoe style for outfits that need a more polished finish. Pair it with tailored pieces or a simple dress.',
    },
    {
        'title': 'Minimal Leather-Strap Watch', 'category': 'watches', 'image': 'kfashion/watch_korean_leather_strap.jpg',
        'price': '89.00', 'stock_no': 'NS-WT-008', 'stock_quantity': 9,
        'description_short': 'A clean watch with a warm accent.',
        'description_long': 'A minimal watch style with a warm metallic accent. Its clean face and polished look make it an easy choice for daily wear or gifting.',
    },
    {
        'title': 'Classic Steel Bracelet Watch', 'category': 'watches', 'image': 'kfashion/watch_korean_chronograph.jpg',
        'price': '95.00', 'stock_no': 'NS-WT-009', 'stock_quantity': 8,
        'description_short': 'A versatile watch with a steel finish.',
        'description_long': 'A versatile watch with a classic steel-bracelet look. Wear it with everyday outfits or use it to finish a more tailored ensemble.',
    },
)


class Command(BaseCommand):
    help = 'Add or synchronize sample catalog products with Korean celebrity campaign photos stored locally.'

    @transaction.atomic
    def handle(self, *args, **options):
        categories = {category.slug.casefold(): category for category in Category.objects.filter(is_active=True)}
        created = 0
        updated = 0
        skipped = 0

        for data in PRODUCTS:
            image_path = Path(settings.MEDIA_ROOT) / data['image']
            if not image_path.is_file():
                raise CommandError(f'Missing product image: {image_path}')

            category = categories.get(data['category'])
            if category is None:
                raise CommandError(f'Missing active category: {data["category"]}')

            slug = slugify(data['title'])
            existing = Item.objects.filter(stock_no=data['stock_no']).first()
            if existing is None:
                existing = Item.objects.filter(slug=slug).first()
            if existing:
                changed_fields = []
                if existing.title != data['title']:
                    existing.title = data['title']
                    changed_fields.append('title')
                if existing.slug != slug:
                    existing.slug = slug
                    changed_fields.append('slug')
                if existing.image.name != data['image']:
                    existing.image = data['image']
                    changed_fields.append('image')
                if changed_fields:
                    existing.save(update_fields=changed_fields)
                    updated += 1
                    self.stdout.write(f'Updated product: {existing.title}')
                else:
                    skipped += 1
                continue

            Item.objects.create(
                title=data['title'],
                price=Decimal(data['price']),
                category=category,
                label='N',
                slug=slug,
                stock_no=data['stock_no'],
                stock_quantity=data['stock_quantity'],
                reorder_level=3,
                description_short=data['description_short'],
                description_long=data['description_long'],
                image=data['image'],
                is_active=True,
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Added {created} products; updated {updated} existing products; left {skipped} unchanged.'
        ))
        for category in Category.objects.filter(is_active=True).order_by('title'):
            count = Item.objects.filter(category=category, is_active=True).count()
            self.stdout.write(f'{category.title}: {count} active products')
