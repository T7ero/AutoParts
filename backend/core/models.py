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

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to=get_upload_path, verbose_name="Файл для парсинга")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0)
    result_file = models.FileField(upload_to='results/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(null=True, blank=True)
    log = models.TextField(null=True, blank=True, verbose_name="Лог задачи")
    result_files = JSONField(null=True, blank=True, verbose_name="Ссылки на все файлы")

    class Meta:
        verbose_name = "Задача парсинга"
        verbose_name_plural = "Задачи парсинга"

    def __str__(self):
        return f"Задача {self.id} - {self.status}" 