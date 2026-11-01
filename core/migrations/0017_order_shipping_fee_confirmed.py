from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_order_shipping_fee'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='shipping_fee_confirmed',
            field=models.BooleanField(default=False),
        ),
    ]
