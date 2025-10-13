from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
import uuid
import os


def get_upload_path(instance, filename):
    """Генерирует путь для загрузки файлов"""
    return os.path.join('uploads', str(instance.id), filename)


class ParsingTask(models.Model):
    """Модель задачи парсинга"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('processing', 'Обрабатывается'),
        ('completed', 'Завершена'),
        ('failed', 'Ошибка'),
    ]
    
    SOURCE_CHOICES = [
        ('autopiter', 'АвтоПитер'),
        ('emex', 'Емекс'),
        ('armtek', 'Армтек'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to='uploads/', verbose_name="Файл")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлена")
    result_file = models.FileField(upload_to='results/', blank=True, null=True, verbose_name="Файл результата")
    log_file = models.FileField(upload_to='logs/', blank=True, null=True, verbose_name="Файл логов")
    error_message = models.TextField(blank=True, null=True, verbose_name="Сообщение об ошибке")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    sources = models.JSONField(default=list, verbose_name="Источники")

    class Meta:
        verbose_name = "Задача парсинга"
        verbose_name_plural = "Задачи парсинга"
        ordering = ['-created_at']

    def __str__(self):
        return f"Задача {self.id} - {self.status}"


class Part(models.Model):
    """Модель запчасти"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.CharField(max_length=100, verbose_name="Артикул")
    brand = models.CharField(max_length=100, verbose_name="Бренд")
    name = models.CharField(max_length=500, verbose_name="Наименование")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")

    class Meta:
        verbose_name = "Запчасть"
        verbose_name_plural = "Запчасти"
        ordering = ['article', 'brand']

    def __str__(self):
        return f"{self.brand} {self.article}"


class CrossReference(models.Model):
    """Модель кросс-ссылки"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    part = models.ForeignKey(Part, on_delete=models.CASCADE, verbose_name="Запчасть")
    cross_article = models.CharField(max_length=100, blank=True, null=True, verbose_name="Кросс-артикул")
    cross_brand = models.CharField(max_length=100, verbose_name="Кросс-бренд")
    source = models.CharField(max_length=20, choices=ParsingTask.SOURCE_CHOICES, verbose_name="Источник")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")

    class Meta:
        verbose_name = "Кросс-ссылка"
        verbose_name_plural = "Кросс-ссылки"
        ordering = ['cross_brand', 'cross_article']

    def __str__(self):
        return f"{self.cross_brand} {self.cross_article}"


class PriceListTask(models.Model):
    """Модель задачи анализа прайс-листа"""
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('processing', 'Обрабатывается'),
        ('completed', 'Завершена'),
        ('failed', 'Ошибка'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to='uploads/', verbose_name="Файл прайс-листа")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлена")
    result_file = models.FileField(upload_to='results/', blank=True, null=True, verbose_name="Файл результата")
    error_message = models.TextField(blank=True, null=True, verbose_name="Сообщение об ошибке")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    total_items = models.IntegerField(default=0, verbose_name="Всего позиций")
    processed_items = models.IntegerField(default=0, verbose_name="Обработано позиций")

    class Meta:
        verbose_name = "Задача анализа прайс-листа"
        verbose_name_plural = "Задачи анализа прайс-листов"
        ordering = ['-created_at']

    def __str__(self):
        return f"Анализ прайс-листа {self.id} - {self.status}"


class PriceListItem(models.Model):
    """Модель позиции в прайс-листе"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(PriceListTask, on_delete=models.CASCADE, verbose_name="Задача")
    supplier_code = models.CharField(max_length=50, verbose_name="Код поставщика")
    manufacturer = models.CharField(max_length=100, verbose_name="Производитель")
    article = models.CharField(max_length=100, verbose_name="Артикул")
    nomenclature = models.CharField(max_length=500, verbose_name="Номенклатура")
    quantity = models.IntegerField(default=0, verbose_name="Количество")
    our_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Наша цена")
    
    # Результаты анализа
    autopiter_found = models.BooleanField(default=False, verbose_name="Найдено на АвтоПитере")
    autopiter_our_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Наша цена на АвтоПитере")
    autopiter_min_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Мин. цена на АвтоПитере")
    
    emex_found = models.BooleanField(default=False, verbose_name="Найдено на Емекс")
    emex_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Цена на Емекс")
    
    armtek_found = models.BooleanField(default=False, verbose_name="Найдено на Армтек")
    armtek_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Цена на Армтек")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создана")

    class Meta:
        verbose_name = "Позиция прайс-листа"
        verbose_name_plural = "Позиции прайс-листов"
        ordering = ['task', 'article']

    def __str__(self):
        return f"{self.manufacturer} {self.article} - {self.our_price}₽"


# Новые модели для анализа прайс-листов конкурентов
class Competitor(models.Model):
    """Модель конкурента"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name="Название конкурента")
    contact_email = models.EmailField(blank=True, null=True, verbose_name="Контактный email")
    website = models.URLField(blank=True, null=True, verbose_name="Сайт")
    notes = models.TextField(blank=True, null=True, verbose_name="Заметки")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    class Meta:
        verbose_name = "Конкурент"
        verbose_name_plural = "Конкуренты"
        ordering = ['name']

    def __str__(self):
        return self.name


class CompetitorPriceList(models.Model):
    """Модель прайс-листа конкурента"""
    STATUS_CHOICES = [
        ('uploaded', 'Загружен'),
        ('processing', 'Обрабатывается'),
        ('processed', 'Обработан'),
        ('error', 'Ошибка'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    competitor = models.ForeignKey(Competitor, on_delete=models.CASCADE, verbose_name="Конкурент")
    file_name = models.CharField(max_length=500, verbose_name="Имя файла")
    file_path = models.CharField(max_length=1000, verbose_name="Путь к файлу")
    file_size = models.BigIntegerField(verbose_name="Размер файла (байт)")
    upload_date = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")
    processing_date = models.DateTimeField(blank=True, null=True, verbose_name="Дата обработки")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded', verbose_name="Статус")
    error_message = models.TextField(blank=True, null=True, verbose_name="Сообщение об ошибке")
    total_positions = models.IntegerField(default=0, verbose_name="Всего позиций")
    processed_positions = models.IntegerField(default=0, verbose_name="Обработано позиций")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Загрузил")

    class Meta:
        verbose_name = "Прайс-лист конкурента"
        verbose_name_plural = "Прайс-листы конкурентов"
        ordering = ['-upload_date']

    def __str__(self):
        return f"{self.competitor.name} - {self.file_name} ({self.upload_date.strftime('%d.%m.%Y')})"


class CompetitorPosition(models.Model):
    """Модель позиции в прайс-листе конкурента"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    price_list = models.ForeignKey(CompetitorPriceList, on_delete=models.CASCADE, verbose_name="Прайс-лист")
    
    # Основная информация о товаре
    article = models.CharField(max_length=100, verbose_name="Артикул")
    brand = models.CharField(max_length=100, blank=True, null=True, verbose_name="Бренд")
    name = models.CharField(max_length=500, verbose_name="Наименование")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    
    # Цена и остатки
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Цена")
    quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)], verbose_name="Остаток")
    
    # Дополнительные поля
    unit = models.CharField(max_length=20, blank=True, null=True, verbose_name="Единица измерения")
    category = models.CharField(max_length=200, blank=True, null=True, verbose_name="Категория")
    supplier_code = models.CharField(max_length=100, blank=True, null=True, verbose_name="Код поставщика")
    
    # Метаданные
    row_number = models.IntegerField(verbose_name="Номер строки в файле")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Позиция конкурента"
        verbose_name_plural = "Позиции конкурентов"
        ordering = ['price_list', 'article', 'brand']
        indexes = [
            models.Index(fields=['price_list', 'article']),
            models.Index(fields=['article', 'brand']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.article} - {self.name} ({self.quantity} шт.)"


class InventoryChange(models.Model):
    """Модель для отслеживания изменений остатков"""
    CHANGE_TYPE_CHOICES = [
        ('increase', 'Увеличение'),
        ('decrease', 'Уменьшение'),
        ('new', 'Новая позиция'),
        ('removed', 'Удаленная позиция'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Связь с позициями
    current_position = models.ForeignKey(
        CompetitorPosition, 
        on_delete=models.CASCADE, 
        related_name='current_changes',
        verbose_name="Текущая позиция"
    )
    previous_position = models.ForeignKey(
        CompetitorPosition, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='previous_changes',
        verbose_name="Предыдущая позиция"
    )
    
    # Данные об изменении
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPE_CHOICES, verbose_name="Тип изменения")
    quantity_change = models.IntegerField(verbose_name="Изменение количества")
    price_change = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Изменение цены")
    
    # Временные метки
    change_date = models.DateTimeField(verbose_name="Дата изменения")
    days_since_last_change = models.IntegerField(blank=True, null=True, verbose_name="Дней с последнего изменения")
    
    # Аналитические поля
    is_significant_change = models.BooleanField(default=False, verbose_name="Значимое изменение")
    change_percentage = models.FloatField(blank=True, null=True, verbose_name="Процент изменения")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Изменение остатков"
        verbose_name_plural = "Изменения остатков"
        ordering = ['-change_date']
        indexes = [
            models.Index(fields=['change_date']),
            models.Index(fields=['change_type']),
            models.Index(fields=['current_position', 'change_date']),
        ]

    def __str__(self):
        return f"{self.current_position.article}: {self.change_type} на {self.quantity_change}"


class CompetitorAnalysis(models.Model):
    """Модель для хранения результатов анализа"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Параметры анализа
    competitor = models.ForeignKey(Competitor, on_delete=models.CASCADE, verbose_name="Конкурент")
    analysis_period_start = models.DateField(verbose_name="Начало периода анализа")
    analysis_period_end = models.DateField(verbose_name="Конец периода анализа")
    
    # Результаты анализа
    total_positions_analyzed = models.IntegerField(verbose_name="Всего позиций проанализировано")
    positions_with_changes = models.IntegerField(verbose_name="Позиций с изменениями")
    total_quantity_changes = models.IntegerField(verbose_name="Всего изменений количества")
    total_sales_estimated = models.IntegerField(verbose_name="Оценка общих продаж")
    
    # Статистика изменений
    avg_change_frequency = models.FloatField(verbose_name="Средняя частота изменений")
    most_active_positions = models.JSONField(blank=True, null=True, verbose_name="Самые активные позиции")
    trend_analysis = models.JSONField(blank=True, null=True, verbose_name="Анализ трендов")
    
    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Создал")

    class Meta:
        verbose_name = "Анализ конкурента"
        verbose_name_plural = "Анализы конкурентов"
        ordering = ['-created_at']

    def __str__(self):
        return f"Анализ {self.competitor.name} ({self.analysis_period_start} - {self.analysis_period_end})"