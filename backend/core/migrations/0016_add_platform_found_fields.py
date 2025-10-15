from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_add_pricelistitem_missing_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricelistitem',
            name='armtek_found',
            field=models.BooleanField(default=False, verbose_name='Найдено на Armtek'),
        ),
        migrations.AddField(
            model_name='pricelistitem',
            name='autopiter_found',
            field=models.BooleanField(default=False, verbose_name='Найдено на Autopiter'),
        ),
        migrations.AddField(
            model_name='pricelistitem',
            name='emex_found',
            field=models.BooleanField(default=False, verbose_name='Найдено на Emex'),
        ),
    ]
