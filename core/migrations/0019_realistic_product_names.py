from django.db import migrations


PRODUCT_NAMES = {
    'dresses-1': 'Lena Draped Midi Dress',
    'dresses-2': 'Amara Square-Neck Dress',
    'dresses-3': 'Noelle Strapless Mini Dress',
    'dresses-4': 'Mira Pleated Midi Dress',
    'dresses-5': 'Sienna Evening Dress',
    'dresses-6': 'Elise Soft-Knit Dress',
    'dresses-7': 'Clara Occasion Dress',
    'pants-1': 'Rowan Tailored Wide-Leg Trousers',
    'pants-2': 'Harper Straight-Leg Pants',
    'pants-3': 'Maeve High-Rise Trousers',
    'pants-4': 'Everyday Relaxed-Fit Pants',
    'pants-5': 'Arden Pleated Trousers',
    'pants-6': 'Classic Wide-Leg Denim',
    'pants-7': 'Elio Tapered Trousers',
    'bags-1': 'The Everyday Shoulder Bag',
    'bags-2': 'Marlow Structured Tote',
    'bags-3': 'Mini Top-Handle Bag',
    'bags-4': 'Luna Crossbody Bag',
    'bags-5': 'Quilted Chain Shoulder Bag',
    'bags-6': 'Soft Hobo Bag',
    'bags-7': 'Evening Frame Clutch',
    'shirts-1': 'Elara Relaxed Button-Up Shirt',
    'shirts-2': 'Everyday Ribbed Tee',
    'shirts-3': 'Studio Oversized Shirt',
    'shirts-4': 'Classic Collar Shirt',
    'shirts-5': 'Soft-Drape Blouse',
    'shirts-6': 'Weekend Boxy T-Shirt',
    'shirts-7': 'Essential Long-Sleeve Top',
    'shoes-1': 'Everyday Low-Top Sneakers',
    'shoes-2': 'Classic Court Sneakers',
    'shoes-3': 'Sculpted Block-Heel Sandals',
    'shoes-4': 'Maren Penny Loafers',
    'shoes-5': 'Pointed-Toe Ballet Flats',
    'shoes-6': 'Lena Minimal Strap Sandals',
    'shoes-7': 'Weekend Slide Sandals',
    'watches-1': 'No. 01 Minimal Analog Watch',
    'watches-2': 'Classic Round-Dial Watch',
    'watches-3': 'The Everyday Mesh Watch',
    'watches-4': 'Slim Dress Watch',
    'watches-5': 'Heritage Dial Watch',
    'watches-6': 'Petite Everyday Watch',
    'watches-7': 'Chronograph-Style Watch',
}


def rename_products(apps, schema_editor):
    Item = apps.get_model('core', 'Item')
    for slug, title in PRODUCT_NAMES.items():
        Item.objects.filter(slug=slug).update(title=title)


def restore_product_names(apps, schema_editor):
    Item = apps.get_model('core', 'Item')
    for slug in PRODUCT_NAMES:
        category, number = slug.rsplit('-', 1)
        Item.objects.filter(slug=slug).update(title=f'{category.title()} {number}')


class Migration(migrations.Migration):
    dependencies = [('core', '0018_itemvariant_orderitem_variant_stockmovement_variant_and_more')]

    operations = [migrations.RunPython(rename_products, restore_product_names)]
