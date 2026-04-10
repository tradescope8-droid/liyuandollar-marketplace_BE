from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0009_product_rating"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="quantity",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
