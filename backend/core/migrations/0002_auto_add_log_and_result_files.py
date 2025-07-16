from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='parsingtask',
            name='log',
            field=models.TextField(null=True, blank=True, verbose_name='Лог задачи'),
        ),
        migrations.AddField(
            model_name='parsingtask',
            name='result_files',
            field=models.JSONField(null=True, blank=True, verbose_name='Ссылки на все файлы'),
        ),
    ] 