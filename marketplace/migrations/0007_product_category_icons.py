from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0006_product_subcategory"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="category_icon",
            field=models.ImageField(blank=True, null=True, upload_to="product-categories/"),
        ),
        migrations.AddField(
            model_name="product",
            name="subcategory_icon",
            field=models.ImageField(blank=True, null=True, upload_to="product-subcategories/"),
        ),
    ]
