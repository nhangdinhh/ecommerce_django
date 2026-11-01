from collections import defaultdict
from decimal import Decimal

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


# These are additional, clearly generic Nhang Shop catalog entries. Existing
# products are preserved; local category/model photos are reused where needed.
PRODUCTS = {
    'dresses': [
        ('Hana Belted Shirt Dress', '74.00', 'A belted dress for everyday styling.', 'A versatile shirt dress with a clean collar, relaxed sleeves, and a removable belt. Designed for easy weekday styling and simple layering.'),
        ('Seoul Pleated Midi Dress', '82.00', 'A fluid midi with softly defined pleats.', 'A refined midi silhouette with gentle pleating and a comfortable fit through the bodice. Pair it with flats for daytime or a simple heel for evening.'),
        ('Mina Ribbed Knit Dress', '68.00', 'A comfortable knit dress with a clean line.', 'A soft ribbed knit dress with a streamlined shape that works across seasons. Layer with a light jacket or wear on its own.'),
        ('Yuna Wrap-Front Dress', '79.00', 'An easy wrap shape for a polished look.', 'A wrap-front dress with a softly draped waist and a balanced midi length. The versatile shape moves easily from casual plans to dinner.'),
        ('Jisoo Tailored Mini Dress', '72.00', 'A neat tailored mini for day-to-evening wear.', 'A structured mini dress with clean seams and a comfortable lining. Style it with sneakers for daytime or dress shoes for an occasion.'),
        ('Sora Soft-Satin Slip Dress', '86.00', 'A smooth slip dress with a subtle sheen.', 'A softly draped slip dress with adjustable straps and a fluid finish. Wear it alone or layer it over a fitted tee.'),
        ('Nari Cotton Poplin Dress', '65.00', 'A breathable cotton dress for everyday plans.', 'A crisp cotton poplin dress with a relaxed fit and practical pockets. Easy to style with sandals, flats, or a light cardigan.'),
        ('Dami Square-Neck Midi Dress', '78.00', 'A modern neckline with an easy midi shape.', 'A square-neck midi dress with a gently shaped waist and clean, minimal details. Made for repeat wear and simple accessorising.'),
    ],
    'bags': [
        ('Seoul Daily Shoulder Bag', '58.00', 'A compact shoulder bag for daily essentials.', 'A clean-lined shoulder bag with a practical interior and an adjustable strap. Its understated shape pairs easily with work and weekend outfits.'),
        ('Haneul Structured Tote', '84.00', 'A structured tote with room for the day.', 'A roomy tote with a defined silhouette, secure top closure, and interior pocket. Designed to carry everyday essentials without feeling bulky.'),
        ('Mori Mini Crossbody', '49.00', 'A lightweight crossbody for hands-free plans.', 'A compact crossbody bag with an adjustable strap and a simple secure closure. A practical choice for errands, travel, and evenings out.'),
        ('Bora Soft Hobo Bag', '69.00', 'A relaxed hobo shape with a soft finish.', 'A softly structured hobo bag with a comfortable shoulder strap and a useful interior compartment. Easy to carry from morning through evening.'),
        ('Namu Everyday Top-Handle Bag', '76.00', 'A versatile top-handle bag with clean details.', 'A polished top-handle bag with a removable shoulder strap and space for daily essentials. The restrained design works across seasons.'),
        ('Dawn Quilted Shoulder Bag', '73.00', 'A quilted bag with a softly padded feel.', 'A softly padded shoulder bag with a neat profile and a secure fastening. Pair it with simple layers for a subtle texture accent.'),
        ('Itaewon Weekend Carryall', '92.00', 'A roomy carryall for short trips and busy days.', 'A practical carryall with a spacious main compartment and reinforced handles. Made for weekend plans, commuting, and everyday errands.'),
    ],
    'pants': [
        ('Seoul Relaxed Straight Jeans', '59.00', 'Straight-leg denim with an easy everyday fit.', 'A versatile straight-leg jean with a comfortable mid rise and classic five-pocket styling. A reliable base for shirts, knits, and tees.'),
        ('Hana Pleated Wide-Leg Trousers', '68.00', 'A fluid wide leg with a polished front pleat.', 'Tailored wide-leg trousers with a softly structured waistband and front pleats. Wear them with a tucked shirt or a relaxed knit.'),
        ('Mori Cropped Chino Pants', '52.00', 'Cropped chinos with a clean, tapered fit.', 'Cropped chinos with a clean taper and comfortable stretch. Their understated finish works well with trainers, loafers, and simple tops.'),
        ('Bora Everyday Joggers', '46.00', 'Soft joggers for relaxed days and travel.', 'Comfortable joggers with a tidy silhouette, adjustable waist, and practical pockets. Made for casual outfits and long travel days.'),
        ('Nari Tailored Ankle Pants', '64.00', 'An ankle-length trouser with a clean finish.', 'A streamlined ankle trouser with a comfortable waistband and lightly tailored leg. A versatile option for work and smart-casual plans.'),
        ('Dami High-Rise Denim', '61.00', 'High-rise denim with a relaxed straight leg.', 'High-rise jeans with an easy straight leg and classic denim details. Style them with a tucked tee, a crisp shirt, or a soft sweater.'),
        ('Yuna Drawstring Linen Trousers', '57.00', 'Lightweight linen-blend trousers for warm days.', 'Breathable linen-blend trousers with an adjustable drawstring waist and relaxed leg. Designed for comfort without losing a polished look.'),
    ],
    'shirts': [
        ('Seoul Boxy Cotton Tee', '28.00', 'A soft boxy tee with an easy drape.', 'A versatile cotton tee with a relaxed boxy cut and a clean crew neckline. Wear it tucked, loose, or layered under a shirt.'),
        ('Hana Fine-Rib Long-Sleeve Top', '34.00', 'A lightweight rib top for simple layering.', 'A fine-rib long-sleeve top with a comfortable close fit and smooth finish. An easy foundation for layered outfits throughout the year.'),
        ('Mori Relaxed Linen Shirt', '54.00', 'A breathable shirt with a relaxed silhouette.', 'A linen-blend button-up with a soft hand feel and a relaxed shape. Wear it buttoned, open over a tee, or lightly tucked.'),
        ('Bora Striped Cotton Shirt', '48.00', 'A classic stripe with a comfortable fit.', 'A crisp striped shirt with a relaxed fit and button cuffs. Pair it with denim or tailored trousers for an easy everyday outfit.'),
        ('Nari Draped Blouse', '51.00', 'A softly draped blouse with refined details.', 'A fluid blouse with a neat neckline and subtle gathers. Its easy shape works tucked into trousers or worn loose with denim.'),
        ('Dami Everyday Polo Shirt', '39.00', 'A clean polo with a casual, polished feel.', 'A soft polo shirt with a classic collar and comfortable short sleeves. A simple alternative to a tee for everyday outfits.'),
        ('Yuna Oversized Poplin Shirt', '56.00', 'A crisp oversized shirt made for layering.', 'A relaxed poplin shirt with a longer hem and clean button front. Wear it loose, half-tucked, or open as a light layer.'),
    ],
    'shoes': [
        ('Seoul Minimal Court Sneakers', '68.00', 'A low-profile sneaker with a clean shape.', 'Everyday court sneakers with a streamlined profile and cushioned footbed. Designed to pair easily with denim, dresses, and casual tailoring.'),
        ('Hana Retro Running Trainers', '76.00', 'A retro-inspired trainer for everyday movement.', 'A lightweight trainer with a comfortable cushioned sole and a balanced retro profile. Made for daily walks and relaxed outfits.'),
        ('Mori Canvas High-Tops', '61.00', 'A classic canvas high-top for casual wear.', 'Canvas high-tops with a supportive ankle cut and familiar lace-up fastening. A versatile everyday option across seasons.'),
        ('Bora Leather-Look Loafers', '72.00', 'A polished slip-on with a comfortable feel.', 'Easy slip-on loafers with a clean upper and flexible sole. Wear them with tailored trousers, denim, or a simple dress.'),
        ('Nari Everyday Ballet Flats', '57.00', 'A lightweight flat with a neat rounded toe.', 'Simple ballet flats with a soft lining and flexible sole. Their compact shape makes them an easy choice for commuting and everyday plans.'),
        ('Dami Everyday Sandals', '54.00', 'A simple sandal with an adjustable fit.', 'Comfortable everyday sandals with adjustable straps and a supportive footbed. Designed for warm-weather walks and relaxed styling.'),
        ('Yuna Soft-Finish Ankle Boots', '88.00', 'A versatile ankle boot with a clean profile.', 'An easy ankle boot with a comfortable low heel and a softly structured upper. A practical layer for cooler days and transitional seasons.'),
    ],
    'watches': [
        ('Seoul Slim Mesh Watch', '98.00', 'A slim dial and refined mesh bracelet.', 'A minimal analog watch with a slim profile, clear dial, and adjustable mesh bracelet. Designed as a subtle finish for everyday outfits.'),
        ('Hana Petite Round Watch', '92.00', 'A petite dial with a timeless silhouette.', 'A compact round-dial watch with a clean face and comfortable bracelet. Its restrained styling works for daily wear and gifting.'),
        ('Mori Classic Leather Watch', '86.00', 'A clean dial paired with a leather-look strap.', 'A classic analog watch with an easy-to-read dial and adjustable strap. A versatile accessory for workdays and weekends.'),
        ('Bora Two-Tone Everyday Watch', '104.00', 'A two-tone finish for a polished everyday look.', 'A balanced two-tone bracelet watch with a simple dial and secure clasp. Made to complement both casual and tailored looks.'),
        ('Nari Minimal Square Watch', '96.00', 'A modern square dial with understated details.', 'A refined square-dial watch with clear markers and a comfortable adjustable strap. An understated accent for everyday styling.'),
        ('Dami Chronograph-Style Watch', '112.00', 'A detailed dial with a sporty, polished finish.', 'A chronograph-inspired watch with a textured dial and sturdy bracelet. Designed for a confident everyday look.'),
        ('Yuna Everyday Dial Watch', '89.00', 'A versatile watch with a clear, classic face.', 'A simple analog watch with a balanced dial and comfortable strap. Easy to wear daily and simple to pair with other accessories.'),
    ],
}

# A second, distinct batch of 102 catalog products. These are original generic
# store listings (not celebrity endorsements); category-appropriate local model
# photos are reused from the existing media library.
EXTRA_PRODUCTS = {
    'dresses': [
        ('Aria Linen-Blend Wrap Dress', '76.00', 'An easy wrap shape with a neat waist.'),
        ('Sora Pleated Shirt Dress', '81.00', 'A crisp shirt dress with soft pleats.'),
        ('Yuri Soft-Knit Midi Dress', '69.00', 'A comfortable knit with a clean line.'),
        ('Nami Gathered Cotton Dress', '63.00', 'A breathable cotton dress with gentle gathers.'),
        ('Hana Double-Strap Midi Dress', '78.00', 'A simple midi with a refined neckline.'),
        ('Mina Satin Bias-Cut Dress', '88.00', 'A fluid satin finish for evening plans.'),
        ('Seoul Belted Day Dress', '73.00', 'A relaxed day dress with a defined waist.'),
        ('Dawn Square-Neck Dress', '71.00', 'A modern neckline and versatile silhouette.'),
        ('Mira Flutter-Sleeve Midi Dress', '79.00', 'Soft sleeves add movement to this midi.'),
        ('Nari Button-Front Midi Dress', '75.00', 'A classic button front with an easy fit.'),
        ('Bora Tailored Mini Dress', '82.00', 'A neat tailored shape for day or evening.'),
        ('Yuna Draped Evening Dress', '94.00', 'A softly draped shape for special plans.'),
        ('Jisoo Textured A-Line Dress', '77.00', 'A subtle texture with an easy A-line cut.'),
        ('Haneul Relaxed Maxi Dress', '85.00', 'A relaxed maxi length for everyday wear.'),
        ('Iris Ribbed Column Dress', '72.00', 'A softly ribbed dress with a straight profile.'),
        ('Noeul Cotton Poplin Dress', '67.00', 'Crisp poplin with a relaxed everyday fit.'),
        ('Ari Soft-Twill Dress', '74.00', 'A smooth twill finish with clean details.'),
    ],
    'bags': [
        ('Aria Crescent Shoulder Bag', '62.00', 'A curved shoulder bag for daily essentials.'),
        ('Mori Pebble-Grain Tote', '86.00', 'A roomy tote with a softly textured finish.'),
        ('Sora Mini Box Crossbody', '55.00', 'A compact crossbody with a neat shape.'),
        ('Namu Canvas Market Tote', '48.00', 'A light carryall for errands and weekends.'),
        ('Hana Zip-Top Hobo Bag', '72.00', 'A relaxed hobo shape with a secure top.'),
        ('Seoul Quilted Chain Bag', '79.00', 'A softly quilted bag with a polished finish.'),
        ('Mira Foldover Clutch', '58.00', 'A compact clutch for evening essentials.'),
        ('Bora Soft-Shell Satchel', '83.00', 'A structured satchel with everyday room.'),
        ('Dawn Everyday Shopper', '69.00', 'A versatile shopper with a clean silhouette.'),
        ('Nari Phone Crossbody Bag', '45.00', 'A small hands-free bag for the essentials.'),
        ('Yuna Structured Mini Tote', '74.00', 'A polished mini tote with a firm shape.'),
        ('Jisoo East-West Shoulder Bag', '77.00', 'A streamlined shape with a longer profile.'),
        ('Haneul Weekend Duffle Bag', '98.00', 'A roomy carryall for short trips away.'),
        ('Iris Top-Handle Bag', '81.00', 'A refined top-handle bag for daily use.'),
        ('Noeul Woven-Detail Tote', '73.00', 'A simple tote accented with woven texture.'),
        ('Ari Compact Camera Bag', '57.00', 'A compact camera shape with useful storage.'),
        ('Mila Drawstring Bucket Bag', '68.00', 'A casual bucket shape with a drawstring top.'),
    ],
    'pants': [
        ('Aria Tailored Wide-Leg Pants', '69.00', 'A fluid wide leg with a clean front.'),
        ('Mori Relaxed Tapered Chinos', '54.00', 'A comfortable chino with a neat taper.'),
        ('Sora High-Rise Straight Jeans', '63.00', 'A straight jean with a comfortable high rise.'),
        ('Namu Linen-Blend Pull-On Pants', '58.00', 'Light trousers with an easy pull-on waist.'),
        ('Hana Pleated Ankle Trousers', '67.00', 'A clean ankle length with front pleats.'),
        ('Seoul Soft-Twill Cargo Pants', '61.00', 'A relaxed utility style with practical pockets.'),
        ('Mina Cropped Straight Jeans', '57.00', 'A cropped straight leg for everyday outfits.'),
        ('Dawn Drawstring Wide-Leg Pants', '55.00', 'A relaxed wide leg with an adjustable waist.'),
        ('Mira Classic Bootcut Jeans', '64.00', 'A subtle bootcut with timeless denim details.'),
        ('Nari Tailored Slim Pants', '62.00', 'A streamlined fit for work and weekends.'),
        ('Bora Relaxed Linen Trousers', '59.00', 'A breathable trouser with an easy drape.'),
        ('Yuna High-Rise Mom Jeans', '61.00', 'A relaxed mom fit with a flattering rise.'),
        ('Jisoo Everyday Knit Joggers', '49.00', 'Soft joggers with a tidy everyday profile.'),
        ('Haneul Double-Pleat Trousers', '72.00', 'A tailored shape with a double-pleat front.'),
        ('Iris Straight-Leg Cord Pants', '66.00', 'A straight leg with a softly ribbed texture.'),
        ('Noeul Relaxed Denim Pants', '58.00', 'Easy denim with a comfortable relaxed fit.'),
        ('Ari Cropped Tailored Pants', '63.00', 'A crisp cropped cut with a polished finish.'),
    ],
    'shirts': [
        ('Aria Soft-Drape Blouse', '49.00', 'A fluid blouse with a clean neckline.'),
        ('Mori Heavyweight Cotton Tee', '32.00', 'A substantial tee with an easy relaxed fit.'),
        ('Sora Fine-Stripe Button Shirt', '52.00', 'Fine stripes on a versatile button-up.'),
        ('Namu Relaxed Oxford Shirt', '55.00', 'A relaxed Oxford with a crisp collar.'),
        ('Hana Ribbed Square-Neck Top', '36.00', 'A soft rib top with a modern neckline.'),
        ('Seoul Boxy Linen Shirt', '57.00', 'A breezy shirt with a boxy silhouette.'),
        ('Mina Sleeveless Knit Top', '39.00', 'A lightweight knit for simple layering.'),
        ('Dawn Poplin Tie-Front Shirt', '53.00', 'A crisp poplin shirt with a tie-front detail.'),
        ('Mira Relaxed Collar Blouse', '48.00', 'A relaxed blouse with a neat collar.'),
        ('Nari Longline Cotton Tee', '31.00', 'A longer cotton tee for easy layering.'),
        ('Bora Textured Short-Sleeve Shirt', '46.00', 'A casual shirt with a subtle texture.'),
        ('Yuna Draped Neck Top', '42.00', 'A softly draped neckline with a smooth finish.'),
        ('Jisoo Classic Rib Tank', '27.00', 'A versatile rib tank with a clean shape.'),
        ('Haneul Oversized Denim Shirt', '64.00', 'A relaxed denim layer with a button front.'),
        ('Iris Cotton Mock-Neck Top', '38.00', 'A smooth cotton top with a neat mock neck.'),
        ('Noeul Everyday Henley Top', '35.00', 'A soft henley with simple button details.'),
        ('Ari Relaxed Cuff-Sleeve Shirt', '51.00', 'A relaxed shirt with refined cuff details.'),
    ],
    'shoes': [
        ('Aria Leather-Look Court Shoes', '71.00', 'A clean court shape with a cushioned footbed.'),
        ('Mori Suede-Feel Everyday Trainers', '78.00', 'A versatile trainer with a soft matte finish.'),
        ('Sora Minimal Strap Sandals', '58.00', 'A simple sandal with an adjustable fit.'),
        ('Namu Classic Canvas Sneakers', '56.00', 'A light canvas sneaker for everyday wear.'),
        ('Hana Soft-Leather Loafers', '82.00', 'A polished loafer with a flexible sole.'),
        ('Seoul Retro Panel Trainers', '74.00', 'Retro panels meet an easy everyday profile.'),
        ('Mina Square-Toe Ballet Flats', '61.00', 'A neat square toe with a flexible feel.'),
        ('Dawn Low-Profile Running Shoes', '79.00', 'A lightweight profile for walks and errands.'),
        ('Mira Block-Heel Sandals', '68.00', 'A steady block heel with clean strap details.'),
        ('Nari Everyday Mary Janes', '65.00', 'A classic Mary Jane with an adjustable strap.'),
        ('Bora Lace-Up Walking Shoes', '76.00', 'Comfortable lace-ups for longer days out.'),
        ('Yuna Minimal Ankle Boots', '91.00', 'A clean ankle boot with an easy low heel.'),
        ('Jisoo Soft-Sole Slip-Ons', '52.00', 'Simple slip-ons with a flexible sole.'),
        ('Haneul Platform Canvas Shoes', '69.00', 'A canvas classic with a subtle platform.'),
        ('Iris Pointed-Toe Flats', '63.00', 'A refined pointed toe in a comfortable flat.'),
        ('Noeul Everyday Slides', '47.00', 'Easy slides with a supportive footbed.'),
        ('Ari City Hiker Sneakers', '84.00', 'A sturdy sneaker for city walks and travel.'),
    ],
    'watches': [
        ('Aria Slim Leather-Strap Watch', '94.00', 'A slim dial with a clean leather-look strap.'),
        ('Mori Brushed-Steel Watch', '108.00', 'A brushed bracelet with a clear dial.'),
        ('Sora Petite Mesh Watch', '89.00', 'A petite face with a light mesh bracelet.'),
        ('Namu Classic Date Watch', '102.00', 'A classic analog face with a date window.'),
        ('Hana Two-Tone Slim Watch', '112.00', 'A slim profile with a balanced two-tone finish.'),
        ('Seoul Minimal Square Watch', '98.00', 'A modern square face with understated markers.'),
        ('Mina Everyday Bracelet Watch', '96.00', 'A versatile bracelet watch with a clear face.'),
        ('Dawn Matte-Finish Dial Watch', '91.00', 'A matte dial and a comfortable adjustable strap.'),
        ('Mira Classic Roman Dial Watch', '105.00', 'Roman markers give this classic dial character.'),
        ('Nari Petite Gold-Tone Watch', '99.00', 'A petite dial with a warm gold-tone finish.'),
        ('Bora Sport Chronograph Watch', '118.00', 'A detailed chronograph-style face for daily wear.'),
        ('Yuna Clean-Face Mesh Watch', '93.00', 'A clean face paired with a flexible mesh strap.'),
        ('Jisoo Heritage Dial Watch', '109.00', 'A heritage-inspired dial with a polished bracelet.'),
        ('Haneul Slim Analog Watch', '87.00', 'A slim, easy-to-read face for everyday outfits.'),
        ('Iris Modern Two-Hand Watch', '90.00', 'A minimal two-hand dial with a refined profile.'),
        ('Noeul Everyday Steel Watch', '103.00', 'A durable steel-look bracelet and classic dial.'),
        ('Ari Small-Case Dress Watch', '97.00', 'A compact case with a simple dress-watch finish.'),
    ],
}

EXTRA_LONG_COPY = {
    'dresses': 'Designed for comfortable movement and easy outfit-building. Wear it with simple shoes for daytime or layer it with a light jacket when the weather changes.',
    'bags': 'The considered shape keeps everyday essentials organised without adding unnecessary bulk. Carry it for errands, work, or relaxed weekend plans.',
    'pants': 'Finished with a comfortable waist and useful everyday details. Pair it with a simple tee, a crisp shirt, or a lightweight knit.',
    'shirts': 'Made to work on its own or as an easy layer. Pair it with denim or tailored trousers for a versatile everyday outfit.',
    'shoes': 'Built for repeat wear with a comfortable lining and a practical everyday profile. Easy to pair with casual and smart-casual outfits.',
    'watches': 'A versatile accessory for daily wear, with a clear dial and a comfortable fit. Its restrained design pairs well with casual or tailored looks.',
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


class Command(BaseCommand):
    help = 'Expand the active catalog with 100+ additional products and seed variants, opening stock, suppliers, and price history.'

    @transaction.atomic
    def handle(self, *args, **options):
        categories = {category.slug.casefold(): category for category in Category.objects.filter(is_active=True)}
        if set(categories) < set(PRODUCTS):
            missing = sorted(set(PRODUCTS) - set(categories))
            raise CommandError(f'Missing active catalog categories: {", ".join(missing)}')

        images_by_category = defaultdict(list)
        for item in Item.objects.filter(is_active=True).exclude(image='').order_by('pk'):
            images_by_category[item.category.slug.casefold()].append(item.image.name)
        for key in PRODUCTS:
            if not images_by_category[key]:
                raise CommandError(f'No local product image is available for category {key}.')

        created = 0
        price_history_rows = []
        stock_codes = {'dresses': 'DR', 'bags': 'BG', 'pants': 'PT', 'shirts': 'ST', 'shoes': 'SH', 'watches': 'WT'}
        definitions_by_category = {
            category_key: definitions + [
                (title, price, short_description, f'{title} {short_description[0].lower() + short_description[1:]} {EXTRA_LONG_COPY[category_key]}')
                for title, price, short_description in EXTRA_PRODUCTS[category_key]
            ]
            for category_key, definitions in PRODUCTS.items()
        }
        for category_key, definitions in definitions_by_category.items():
            category = categories[category_key]
            existing_count = Item.objects.filter(category=category, is_active=True).count()
            image_names = list(dict.fromkeys(images_by_category[category_key]))
            for index, (title, price, short_description, long_description) in enumerate(definitions, start=1):
                slug = slugify(title)
                if Item.objects.filter(slug=slug).exists():
                    continue
                stock_no = f'NS{stock_codes[category_key]}{existing_count + index:06d}'
                stock_quantity = 18 + ((existing_count + index) % 5) * 3
                image = image_names[(existing_count + index - 1) % len(image_names)]
                item = Item.objects.create(
                    title=title,
                    price=Decimal(price),
                    category=category,
                    label='N',
                    slug=slug,
                    stock_no=stock_no,
                    stock_quantity=stock_quantity,
                    reorder_level=4,
                    description_short=short_description,
                    description_long=long_description,
                    image=image,
                    is_active=True,
                )
                price_history_rows.append(PriceHistory(
                    item=item,
                    old_price=None,
                    new_price=item.price,
                    new_discount_price=item.discount_price,
                    note='Initial catalog price for local demo data.',
                ))
                created += 1

        PriceHistory.objects.bulk_create(price_history_rows, batch_size=500)

        # Keep all existing prices and stock quantities intact. Variants split
        # the current on-hand quantity. Item IDs make demo SKUs unique even if
        # older catalog rows reused the same stock number.
        variants_to_create = []
        active_items = list(Item.objects.filter(is_active=True).select_related('category').order_by('pk'))
        repaired_descriptions = []
        for item in Item.objects.all():
            if len(item.description_short) > Item._meta.get_field('description_short').max_length:
                shortened = item.description_short[:50].rsplit(' ', 1)[0].rstrip(' .,:;-')
                item.description_short = shortened
                repaired_descriptions.append(item)
        Item.objects.bulk_update(repaired_descriptions, ('description_short',), batch_size=500)
        sample_price_rows = []
        for item in active_items:
            if not PriceHistory.objects.filter(item=item, note='Demo price history entry; sample only.').exists():
                previous_price = (item.price * Decimal('0.90')).quantize(Decimal('0.01'))
                sample_price_rows.append(PriceHistory(
                    item=item,
                    old_price=previous_price,
                    new_price=item.price,
                    old_discount_price=None,
                    new_discount_price=item.discount_price,
                    note='Demo price history entry; sample only.',
                ))
            sizes = SIZES.get(item.category.slug.casefold(), ('One Size',))
            combinations = [(size, color) for size in sizes for color in COLORS]
            existing_combinations = set(item.variants.values_list('size', 'color'))
            for sequence, (size, color) in enumerate(combinations, start=1):
                if (size, color) in existing_combinations:
                    continue
                sku = f'SEED{item.pk:06d}-{sequence:02d}'
                variants_to_create.append(ItemVariant(
                    item=item,
                    size=size,
                    color=color,
                    sku=sku,
                    stock_quantity=0,
                    reorder_level=2,
                ))
        PriceHistory.objects.bulk_create(sample_price_rows, batch_size=500)
        ItemVariant.objects.bulk_create(variants_to_create, batch_size=1000, ignore_conflicts=True)

        # This local seed has no order lines tied to variants yet. Reconcile
        # variant balances to each product's current stock once; after buyers
        # place variant orders, leave the inventory ledger untouched.
        from core.models import OrderItem
        if not OrderItem.objects.filter(item__is_active=True, variant__isnull=False).exists():
            variant_updates = []
            for item in active_items:
                variants = list(ItemVariant.objects.filter(item=item).order_by('size', 'color'))
                if not variants:
                    continue
                base, remainder = divmod(item.stock_quantity, len(variants))
                for sequence, variant in enumerate(variants, start=1):
                    variant.stock_quantity = base + (1 if sequence <= remainder else 0)
                    variant_updates.append(variant)
            ItemVariant.objects.bulk_update(variant_updates, ('stock_quantity',), batch_size=1000)

        demo_supplier, _ = Supplier.objects.get_or_create(
            name='Demo Local Catalog Supplier',
            defaults={
                'contact_name': 'Sample Supplier',
                'email': 'supplier@example.test',
                'phone': '+84900000000',
                'notes': 'Clearly marked supplier record for local demo catalog stock only.',
                'is_active': False,
            },
        )
        receipts = []
        movements = []
        variants = list(ItemVariant.objects.filter(item__is_active=True).select_related('item'))
        seeded_receipts = {
            receipt.variant_id: receipt
            for receipt in StockReceipt.objects.filter(
                item__is_active=True,
                variant__isnull=False,
                note__startswith='Opening stock for a locally seeded product',
            )
        }
        seeded_movements = {
            movement.variant_id: movement
            for movement in StockMovement.objects.filter(
                item__is_active=True,
                variant__isnull=False,
                note='Demo opening balance corresponding to the stock receipt.',
            )
        }
        receipt_updates = []
        movement_updates = []
        for variant in variants:
            if variant.stock_quantity <= 0:
                if receipt := seeded_receipts.get(variant.pk):
                    receipt.delete()
                if movement := seeded_movements.get(variant.pk):
                    movement.delete()
                continue
            reference = f'OPEN-P{variant.item_id}-V{variant.pk}'
            unit_cost = (variant.item.price * Decimal('0.45')).quantize(Decimal('0.01'))
            receipt = seeded_receipts.get(variant.pk)
            if receipt:
                receipt.reference = reference
                receipt.quantity = variant.stock_quantity
                receipt.unit_cost = unit_cost
                receipt.note = 'Opening stock for a locally seeded product; not a real supplier purchase.'
                receipt_updates.append(receipt)
            else:
                receipts.append(StockReceipt(
                    supplier=demo_supplier,
                    item=variant.item,
                    variant=variant,
                    reference=reference,
                    quantity=variant.stock_quantity,
                    unit_cost=unit_cost,
                    note='Opening stock for a locally seeded product; not a real supplier purchase.',
                ))
            movement = seeded_movements.get(variant.pk)
            if movement:
                movement.quantity_change = variant.stock_quantity
                movement.note = 'Demo opening balance corresponding to the stock receipt.'
                movement_updates.append(movement)
            else:
                movements.append(StockMovement(
                    item=variant.item,
                    variant=variant,
                    quantity_change=variant.stock_quantity,
                    reason='purchase',
                    note='Demo opening balance corresponding to the stock receipt.',
                ))
        StockReceipt.objects.bulk_update(receipt_updates, ('reference', 'quantity', 'unit_cost', 'note'), batch_size=1000)
        StockMovement.objects.bulk_update(movement_updates, ('quantity_change', 'note'), batch_size=1000)
        StockReceipt.objects.bulk_create(receipts, batch_size=1000)
        StockMovement.objects.bulk_create(movements, batch_size=1000)

        active_count = Item.objects.filter(is_active=True).count()
        self.stdout.write(self.style.SUCCESS(
            f'Catalog ready: {active_count} active products; {created} added; '
            f'{len(variants_to_create)} variants, {len(sample_price_rows)} sample price-history rows, '
            f'{len(receipts)} opening stock receipts created; '
            f'{len(repaired_descriptions)} legacy descriptions shortened to fit the database field.'
        ))
