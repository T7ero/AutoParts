from django.db import migrations, models
import django.db.models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_add_price_list_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='parsingtask',
            name='sources',
            field=models.JSONField(null=True, blank=True, verbose_name='Выбранные источники'),
        ),
    ]
