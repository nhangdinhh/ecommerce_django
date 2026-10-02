import os
import django
import random

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
django.setup()

from core.models import Item

for item in Item.objects.all():
    base_price = random.randint(15, 80)
    cents = random.choice([0, 50, 99])
    item.price = float(f"{base_price}.{cents:02d}")
    if random.random() > 0.7:
        discount_base = base_price - random.randint(3, 10)
        if discount_base < 1:
            discount_base = 1
        item.discount_price = float(f"{discount_base}.{cents:02d}")
    else:
        item.discount_price = None
    item.save()

print("Updated all item prices successfully!")
