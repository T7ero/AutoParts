from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_add_missing_price_list_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricelistitem',
            name='is_found',
            field=models.BooleanField(default=False, verbose_name='Найдено на площадке'),
        ),
        migrations.AddField(
            model_name='pricelistitem',
            name='marketplace_price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Цена на площадке'),
        ),
        migrations.AddField(
            model_name='pricelistitem',
            name='min_competitor_price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Мин. цена конкурента'),
        ),
        migrations.AddField(
            model_name='pricelistitem',
            name='competitor_brand',
            field=models.CharField(blank=True, max_length=100, verbose_name='Бренд конкурента с мин. ценой'),
        ),
        migrations.AddField(
            model_name='pricelistitem',
            name='error_message',
            field=models.TextField(blank=True, verbose_name='Сообщение об ошибке'),
        ),
    ]
