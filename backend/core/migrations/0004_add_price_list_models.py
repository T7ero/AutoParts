# Generated manually for price list analysis module

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_auto_add_log_and_result_files'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PriceListTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='uploads/', verbose_name='Файл прайс-листа')),
                ('platform', models.CharField(choices=[('autopiter', 'АвтоПитер'), ('armtek', 'Армтек'), ('emex', 'Емекс')], max_length=20, verbose_name='Площадка')),
                ('status', models.CharField(choices=[('pending', 'Ожидает'), ('processing', 'Обрабатывается'), ('completed', 'Завершена'), ('failed', 'Ошибка')], default='pending', max_length=20, verbose_name='Статус')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')),
                ('completed_at', models.DateTimeField(blank=True, null=True, verbose_name='Дата завершения')),
                ('total_items', models.IntegerField(default=0, verbose_name='Всего позиций')),
                ('processed_items', models.IntegerField(default=0, verbose_name='Обработано позиций')),
                ('found_items', models.IntegerField(default=0, verbose_name='Найдено позиций')),
                ('not_found_items', models.IntegerField(default=0, verbose_name='Не найдено позиций')),
                ('log', models.TextField(blank=True, verbose_name='Лог выполнения')),
                ('result_file', models.FileField(blank=True, null=True, upload_to='results/', verbose_name='Файл результата')),
                ('error_message', models.TextField(blank=True, verbose_name='Сообщение об ошибке')),
                ('competitor_brand_filter', models.CharField(blank=True, max_length=100, verbose_name='Фильтр бренда конкурента')),
                ('include_price_analysis', models.BooleanField(default=True, verbose_name='Включить анализ цен')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='Пользователь')),
            ],
            options={
                'verbose_name': 'Задача анализа прайс-листа',
                'verbose_name_plural': 'Задачи анализа прайс-листа',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PriceListItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('supplier_code', models.CharField(blank=True, max_length=20, verbose_name='Код поставщика')),
                ('manufacturer', models.CharField(max_length=100, verbose_name='Производитель')),
                ('article', models.CharField(max_length=100, verbose_name='Артикул')),
                ('nomenclature', models.TextField(verbose_name='Номенклатура')),
                ('quantity', models.IntegerField(default=0, verbose_name='Количество')),
                ('our_price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Наша цена')),
                ('is_found', models.BooleanField(default=False, verbose_name='Найдено на площадке')),
                ('marketplace_price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Цена на площадке')),
                ('min_competitor_price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Мин. цена конкурента')),
                ('competitor_brand', models.CharField(blank=True, max_length=100, verbose_name='Бренд конкурента с мин. ценой')),
                ('error_message', models.TextField(blank=True, verbose_name='Сообщение об ошибке')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='core.pricelisttask', verbose_name='Задача')),
            ],
            options={
                'verbose_name': 'Позиция прайс-листа',
                'verbose_name_plural': 'Позиции прайс-листа',
                'unique_together': {('task', 'manufacturer', 'article')},
            },
        ),
    ]
