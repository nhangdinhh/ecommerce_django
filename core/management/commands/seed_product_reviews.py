from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Item, Order, Review


DEMO_COMMENTS = (
    'Demo review: the fit is comfortable and the finish feels well made.',
    'Demo review: a versatile piece that is easy to style for everyday wear.',
    'Demo review: the details look lovely and the product matches its description.',
    'Demo review: good value, comfortable to use, and nicely finished.',
    'Demo review: a thoughtful design and a welcome addition to my wardrobe.',
)


class Command(BaseCommand):
    help = 'Ensure each active product has at least three clearly marked demo reviews.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--per-product', type=int, default=3,
            help='Minimum number of reviews to keep per active product (default: 3).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        target = options['per_product']
        if target < 1:
            self.stderr.write(self.style.ERROR('--per-product must be at least 1.'))
            return

        User = get_user_model()
        delivered_statuses = ('delivered', 'refund_requested', 'refunded')
        created_total = 0
        shortfall = []

        for item in Item.objects.filter(is_active=True).order_by('pk'):
            existing_ids = set(
                Review.objects.filter(item=item).values_list('user_id', flat=True)
            )
            needed = max(0, target - len(existing_ids))
            if not needed:
                continue

            purchaser_ids = list(
                Order.objects.filter(
                    ordered=True,
                    status__in=delivered_statuses,
                    items__item=item,
                ).values_list('user_id', flat=True).distinct().order_by('user_id')
            )
            reviewers = list(
                User.objects.filter(pk__in=purchaser_ids)
                .exclude(pk__in=existing_ids)
                .order_by('pk')[:needed]
            )

            # If the demo database has no delivered buyers for this item, add
            # explicitly labelled review-only accounts. Their reviews stay
            # unverified because these accounts have no matching delivered order.
            while len(reviewers) < needed:
                index = 1
                while User.objects.filter(username=f'demo-reviewer-{index:04d}').exists():
                    index += 1
                reviewer = User.objects.create_user(
                    username=f'demo-reviewer-{index:04d}',
                    email=f'demo-reviewer-{index:04d}@example.test',
                )
                reviewer.set_unusable_password()
                reviewer.save(update_fields=['password'])
                reviewers.append(reviewer)

            rows = []
            for offset, reviewer in enumerate(reviewers):
                comment_index = (item.pk + len(existing_ids) + offset) % len(DEMO_COMMENTS)
                rating = 5 if offset % 2 == 0 else 4
                rows.append(Review(
                    user=reviewer,
                    item=item,
                    rating=rating,
                    comment=DEMO_COMMENTS[comment_index],
                ))
            Review.objects.bulk_create(rows)
            created_total += len(rows)

            final_count = len(existing_ids) + len(rows)
            if final_count < target:
                shortfall.append((item.title, final_count))

        self.stdout.write(self.style.SUCCESS(
            f'Added {created_total} demo reviews. Each active product now has at least '
            f'{target} reviews where possible.'
        ))
        if shortfall:
            self.stdout.write(self.style.WARNING(
                'Products below the requested review count: '
                + ', '.join(f'{title} ({count})' for title, count in shortfall)
            ))
