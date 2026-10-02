import os
import django
import random

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
django.setup()

from core.models import Item

descriptions = [
    "Experience the perfect blend of comfort and style. Made from premium, breathable materials, this piece is designed to keep you looking effortlessly chic all day long. Its versatile design makes it ideal for both casual outings and more formal occasions.",
    "A timeless classic redefined for the modern wardrobe. Featuring meticulous craftsmanship and a tailored fit, this item promises exceptional durability without compromising on elegance. It's a must-have staple for anyone who values quality.",
    "Elevate your everyday look with this stunning statement piece. The attention to detail is evident in every stitch, offering a sophisticated silhouette that flatters any body type. Perfect for making a lasting impression wherever you go.",
    "Designed with both aesthetics and functionality in mind. This product offers maximum comfort and a sleek, contemporary look. Whether you're heading to the office or a weekend getaway, it adapts seamlessly to your lifestyle."
]

shorts = [
    "Weight: 0.5 kg | Dimensions: 40 x 30 x 10 cm | Material: 100% Organic Cotton",
    "Weight: 1.2 kg | Dimensions: 50 x 35 x 15 cm | Material: Genuine Leather & Canvas",
    "Weight: 0.3 kg | Dimensions: 25 x 20 x 5 cm | Material: Premium Silk Blend",
    "Weight: 0.8 kg | Dimensions: 45 x 25 x 12 cm | Material: Recycled Polyester",
    "Weight: 0.6 kg | Dimensions: 35 x 25 x 8 cm | Material: Durable Denim"
]

for item in Item.objects.all():
    item.description_long = random.choice(descriptions)
    item.description_short = random.choice(shorts)
    item.save()

print("Updated all item descriptions successfully!")
