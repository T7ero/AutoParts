# Generated manually to add missing fields

from django.db import migrations, models
from django.core.validators import MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_fake_existing_tables'),
    ]

    operations = [
        # Add missing fields to existing models
        migrations.AddField(
            model_name='part',
            name='article',
            field=models.CharField(max_length=100, verbose_name='Артикул', blank=True, default=''),
        ),
        migrations.AddField(
            model_name='pricelisttask',
            name='progress',
            field=models.IntegerField(default=0, verbose_name='Прогресс (%)'),
        ),
    ]
