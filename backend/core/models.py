import os
import tempfile
from django.db import models
from django.contrib.auth.models import User
from django.db.models import JSONField
from django.conf import settings

class Part(models.Model):
    """Модель для хранения информации о запчастях"""
    name = models.CharField(max_length=255, verbose_name="Название")
    part_number = models.CharField(max_length=100, verbose_name="Номер детали")
    article = models.CharField(max_length=100, verbose_name="Артикул", blank=True, default='')
    brand = models.CharField(max_length=100, verbose_name="Бренд")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Запчасть"
        verbose_name_plural = "Запчасти"

    def __str__(self):
        return f"{self.brand} - {self.part_number}"

class CrossReference(models.Model):
    """Модель для хранения кросс-номеров"""
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='cross_references')
    competitor_brand = models.CharField(max_length=100, verbose_name="Бренд конкурента")
    competitor_number = models.CharField(max_length=100, verbose_name="Номер конкурента")
    source_url = models.URLField(verbose_name="URL источника")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Кросс-номер"
        verbose_name_plural = "Кросс-номера"

    def __str__(self):
        return f"{self.competitor_brand} - {self.competitor_number}"

def get_upload_path(instance, filename):
    """Определяет путь для загрузки файлов с fallback на временную директорию"""
    try:
        # Проверяем доступность стандартной директории
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads')
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir, exist_ok=True)
        
        # Проверяем права на запись
        test_file = os.path.join(upload_dir, '.test')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return f'uploads/{filename}'
        except (PermissionError, OSError):
            # Если нет прав, используем временную директорию
            # Возвращаем относительный путь для Django
            return f'temp/{filename}'
    except Exception:
        # В случае любой ошибки используем временную директорию
        # Возвращаем относительный путь для Django
        return f'temp/{filename}'

class ParsingTask(models.Model):
    """Модель для отслеживания задач парсинга"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('in_progress', 'В процессе'),
        ('completed', 'Завершено'),
        ('failed', 'Ошибка'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    file = models.FileField(upload_to=get_upload_path, verbose_name="Файл для парсинга")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0)
    result_file = models.FileField(upload_to='results/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(null=True, blank=True)
    log = models.TextField(null=True, blank=True, verbose_name="Лог задачи")
    result_files = JSONField(null=True, blank=True, verbose_name="Ссылки на все файлы")
    sources = JSONField(null=True, blank=True, verbose_name="Выбранные источники")

    class Meta:
        verbose_name = "Задача парсинга"
        verbose_name_plural = "Задачи парсинга"

    def __str__(self):
        return f"Задача {self.id} - {self.status}" 

class PriceListTask(models.Model):
    """Задача анализа прайс-листа на площадках"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('processing', 'Обрабатывается'),
        ('completed', 'Завершена'),
        ('failed', 'Ошибка'),
    ]
    
    PLATFORM_CHOICES = [
        ('autopiter', 'АвтоПитер'),
        ('armtek', 'Армтек'),
        ('emex', 'Емекс'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    file = models.FileField(upload_to='uploads/', verbose_name="Файл прайс-листа")
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, verbose_name="Площадка")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    progress = models.IntegerField(default=0, verbose_name="Прогресс (%)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата завершения")
    total_items = models.IntegerField(default=0, verbose_name="Всего позиций")
    processed_items = models.IntegerField(default=0, verbose_name="Обработано позиций")
    found_items = models.IntegerField(default=0, verbose_name="Найдено позиций")
    not_found_items = models.IntegerField(default=0, verbose_name="Не найдено позиций")
    log = models.TextField(blank=True, verbose_name="Лог выполнения")
    result_file = models.FileField(upload_to='results/', null=True, blank=True, verbose_name="Файл результата")
    log_file = models.FileField(upload_to='logs/', null=True, blank=True, verbose_name="Файл логов")
    error_message = models.TextField(blank=True, verbose_name="Сообщение об ошибке")
    
    # Фильтры для анализа цен
    competitor_brand_filter = models.CharField(max_length=100, blank=True, verbose_name="Фильтр бренда конкурента")
    include_price_analysis = models.BooleanField(default=True, verbose_name="Включить анализ цен")
    
    class Meta:
        verbose_name = "Задача анализа прайс-листа"
        verbose_name_plural = "Задачи анализа прайс-листа"
        ordering = ['-created_at']

class PriceListItem(models.Model):
    """Позиция из прайс-листа"""
    task = models.ForeignKey(PriceListTask, on_delete=models.CASCADE, related_name='items', verbose_name="Задача")
    supplier_code = models.CharField(max_length=20, blank=True, verbose_name="Код поставщика")
    manufacturer = models.CharField(max_length=100, verbose_name="Производитель")
    article = models.CharField(max_length=100, verbose_name="Артикул")
    nomenclature = models.TextField(verbose_name="Номенклатура")
    quantity = models.IntegerField(default=0, verbose_name="Количество")
    our_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Наша цена")
    
    # Результаты парсинга
    is_found = models.BooleanField(default=False, verbose_name="Найдено на площадке")
    marketplace_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Цена на площадке")
    min_competitor_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Мин. цена конкурента")
    competitor_brand = models.CharField(max_length=100, blank=True, verbose_name="Бренд конкурента с мин. ценой")
    error_message = models.TextField(blank=True, verbose_name="Сообщение об ошибке")
    
    class Meta:
        verbose_name = "Позиция прайс-листа"
        verbose_name_plural = "Позиции прайс-листа"
        unique_together = ['task', 'manufacturer', 'article'] 