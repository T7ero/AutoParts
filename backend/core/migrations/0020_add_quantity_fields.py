from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_add_created_at_to_pricelistitem'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricelistitem',
            name='quantity_in_stock',
            field=models.IntegerField(blank=True, null=True, verbose_name='Количество в наличии'),
        ),
        migrations.AddField(
            model_name='pricelistitem',
            name='competitor_quantity',
            field=models.IntegerField(blank=True, null=True, verbose_name='Количество у конкурента'),
        ),
    ]
