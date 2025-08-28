from django.db import migrations, models
import django.db.models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_auto_add_log_and_result_files'),
    ]

    operations = [
        migrations.AddField(
            model_name='parsingtask',
            name='sources',
            field=models.JSONField(null=True, blank=True, verbose_name='Выбранные источники'),
        ),
    ]
