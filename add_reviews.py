"""Backward-compatible wrapper for adding sample product reviews safely."""

import os

import django


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo.settings')
django.setup()

from django.core.management import call_command  # noqa: E402


if __name__ == '__main__':
    call_command('seed_product_reviews')
