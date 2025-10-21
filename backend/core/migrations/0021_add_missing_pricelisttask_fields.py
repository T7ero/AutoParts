# Generated manually for adding missing fields to PriceListTask

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_remove_parsingtask_log_remove_parsingtask_progress_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricelisttask',
            name='found_items',
            field=models.IntegerField(default=0, verbose_name='Найденные позиции'),
        ),
        migrations.AddField(
            model_name='pricelisttask',
            name='not_found_items',
            field=models.IntegerField(default=0, verbose_name='Ненайденные позиции'),
        ),
        migrations.AddField(
            model_name='pricelisttask',
            name='log',
            field=models.TextField(blank=True, verbose_name='Лог выполнения'),
        ),
    ]
