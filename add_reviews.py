import os
import django
import random

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
django.setup()

from django.contrib.auth.models import User
from core.models import Item, Review

def recreate_fake_reviews():
    # Delete existing reviews first
    Review.objects.all().delete()
    print("Old reviews deleted.")

    # Get users
    users = list(User.objects.filter(username__in=['alice', 'bob', 'charlie', 'david', 'emma', 'fiona', 'george']))

    comments_5 = [
        "Absolutely love this product! The quality is amazing.",
        "Exceeded my expectations. Will buy again!",
        "Perfect fit and great style.",
        "This is exactly what I was looking for. 5 stars!"
    ]
    
    comments_4 = [
        "Very nice, highly recommended.",
        "Good quality, but shipping took a while.",
        "Looks great, I really like it."
    ]

    comments_3 = [
        "It's decent, but I expected a bit more.",
        "Not bad for the price.",
        "Looks okay, quality could be better."
    ]
    
    comments_2 = [
        "I didn't really like the material, feels a bit cheap.",
        "Sizing is a bit off for me.",
        "Not exactly as shown in the picture."
    ]
    
    comments_1 = [
        "Terrible experience, arrived damaged.",
        "Very disappointing quality. Would not recommend.",
        "Completely the wrong item. Not happy."
    ]

    items = Item.objects.all()
    for item in items:
        num_reviews = random.randint(3, 6)
        reviewers = random.sample(users, min(num_reviews, len(users)))
        for user in reviewers:
            # Randomize rating with wider distribution (1 to 5)
            # weights: 5(30%), 4(30%), 3(20%), 2(10%), 1(10%)
            rating = random.choices([5, 4, 3, 2, 1], weights=[0.3, 0.3, 0.2, 0.1, 0.1])[0]
            
            if rating == 5:
                comment = random.choice(comments_5)
            elif rating == 4:
                comment = random.choice(comments_4)
            elif rating == 3:
                comment = random.choice(comments_3)
            elif rating == 2:
                comment = random.choice(comments_2)
            else:
                comment = random.choice(comments_1)
            
            Review.objects.create(
                user=user,
                item=item,
                rating=rating,
                comment=comment
            )
    print("New varied dummy reviews created successfully!")

if __name__ == '__main__':
    recreate_fake_reviews()
