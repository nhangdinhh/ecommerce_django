import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
django.setup()

from core.models import Coupon

def create_coupons():
    Coupon.objects.all().delete()
    print("Old coupons deleted.")
    
    coupons = [
        {"code": "NHANG1", "amount": 10.0},
        {"code": "NHANG2", "amount": 20.0},
        {"code": "NHANG3", "amount": 30.0}
    ]
    
    for c in coupons:
        Coupon.objects.create(code=c["code"], amount=c["amount"])
        print(f"Created coupon: {c['code']}")
            
    print("Coupons added successfully!")

if __name__ == '__main__':
    create_coupons()
