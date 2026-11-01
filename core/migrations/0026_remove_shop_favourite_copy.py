import re

from django.db import migrations


_SHOP_FAVOURITE_COPY = re.compile(r"a\s+nhang\s+shop\s+favourite", re.IGNORECASE)


def remove_shop_favourite_copy(apps, schema_editor):
    Item = apps.get_model("core", "Item")

    for item in Item.objects.only("pk", "description_short", "description_long").iterator():
        changed_fields = []
        for field in ("description_short", "description_long"):
            original = getattr(item, field) or ""
            cleaned = _SHOP_FAVOURITE_COPY.sub("", original)
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" \t\r\n.,;:-–—")
            if cleaned != original:
                setattr(item, field, cleaned)
                changed_fields.append(field)

        if changed_fields:
            item.save(update_fields=changed_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_alter_order_status_alter_orderstatushistory_status_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_shop_favourite_copy, migrations.RunPython.noop),
    ]
