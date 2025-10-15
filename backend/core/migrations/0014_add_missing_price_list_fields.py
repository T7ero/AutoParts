from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_remove_pricelisttask_found_items_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricelisttask',
            name='platform',
            field=models.CharField(choices=[('autopiter', 'АвтоПитер'), ('emex', 'Emex'), ('armtek', 'Armtek')], default='autopiter', max_length=20, verbose_name='Площадка'),
        ),
        migrations.AddField(
            model_name='pricelisttask',
            name='competitor_brand_filter',
            field=models.CharField(blank=True, max_length=100, verbose_name='Фильтр бренда конкурента'),
        ),
        migrations.AddField(
            model_name='pricelisttask',
            name='include_price_analysis',
            field=models.BooleanField(default=True, verbose_name='Включить анализ цен'),
        ),
    ]
