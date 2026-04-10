from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0005_support_ticket_supportmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="subcategory",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
