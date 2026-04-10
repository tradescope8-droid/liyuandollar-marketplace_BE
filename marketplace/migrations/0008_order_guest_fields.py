from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0007_product_category_icons"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="guest_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="order",
            name="guest_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="order",
            name="guest_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
    ]
