# Generated manually for client server
# Добавляет поля для количества товара, если их еще нет

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_remove_parsingtask_log_remove_parsingtask_progress_and_more'),  # Эта миграция есть на сервере заказчика
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
            field=models.IntegerField(blank=True, null=True, verbose_name='Количество конкурента'),
        ),
    ]

