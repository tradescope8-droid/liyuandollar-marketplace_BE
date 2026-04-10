from django.db import migrations, models
import decimal


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0008_order_guest_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="rating",
            field=models.DecimalField(
                decimal_places=1,
                default=decimal.Decimal("4.8"),
                max_digits=3,
            ),
        ),
    ]
