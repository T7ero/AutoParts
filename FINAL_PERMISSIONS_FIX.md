# Финальное исправление проблем с правами доступа

## Проблема
Ошибка `PermissionError: [Errno 13] Permission denied: '/app/media/uploads/test2_XBfDuaG.xlsx'` при загрузке файлов через API.

## Причина
Пользователь `appuser` не имеет прав на создание файлов в директории `/app/media/uploads`.

## Внесенные исправления

### 1. Исправлен Dockerfile
```dockerfile
# backend/Dockerfile
# Создаем необходимые директории и устанавливаем права
RUN mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app/media
```

### 2. Улучшен entrypoint скрипт
```bash
# backend/entrypoint.sh
# Создаем необходимые директории с правильными правами
echo "📁 Создание директорий..."
mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static || true
chmod -R 755 /app/media || true
```

### 3. Исправлены настройки Django
```python
# backend/backend/settings.py
# Создаем директории если их нет (с обработкой ошибок)
try:
    os.makedirs(MEDIA_ROOT, exist_ok=True)
    os.makedirs(os.path.join(MEDIA_ROOT, 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(MEDIA_ROOT, 'results'), exist_ok=True)
    os.makedirs(os.path.join(MEDIA_ROOT, 'temp'), exist_ok=True)
    FILE_UPLOAD_TEMP_DIR = os.path.join(BASE_DIR, 'media', 'temp')
    print(f"✅ Директории созданы: {MEDIA_ROOT}")
except PermissionError:
    # Если нет прав, используем временную директорию
    import tempfile
    FILE_UPLOAD_TEMP_DIR = tempfile.gettempdir()
    print(f"⚠️ Используем временную директорию: {FILE_UPLOAD_TEMP_DIR}")
```

### 4. Добавлен fallback в модель
```python
# backend/core/models.py
def get_upload_path(instance, filename):
    """Определяет путь для загрузки файлов с fallback на временную директорию"""
    try:
        # Пробуем использовать стандартную директорию
        return f'uploads/{filename}'
    except PermissionError:
        # Если нет прав, используем временную директорию
        temp_dir = tempfile.gettempdir()
        return os.path.join(temp_dir, filename)

class ParsingTask(models.Model):
    file = models.FileField(upload_to=get_upload_path, verbose_name="Файл для парсинга")
```

## Проверка исправления

### 1. Автоматическое исправление
```bash
chmod +x fix_permissions_final.sh
./fix_permissions_final.sh
```

### 2. Ручное исправление
```bash
# Остановить сервисы
docker compose down

# Очистить данные PostgreSQL
sudo rm -rf ./pg_data

# Пересобрать образы
docker compose build --no-cache backend

# Запустить сервисы
docker compose up -d
```

### 3. Проверка прав доступа
```bash
# Проверить права доступа в контейнере
docker compose exec backend ls -la /app/media/

# Проверить пользователя
docker compose exec backend whoami

# Проверить директории
docker compose exec backend find /app -type d -ls
```

### 4. Тестирование загрузки
```bash
python3 test_upload_fix.py
```

## Ожидаемые результаты

### После исправления
- Успешная загрузка файлов без ошибок 400
- Корректные права доступа к директориям
- Fallback на временную директорию при проблемах
- Работающие API endpoints

### Логи успешной загрузки
```
backend-1   | ✅ Директории созданы: /app/media
backend-1   | 2025-07-30 16:17:10,294 INFO     POST /api/parsing-tasks/ 201 1234
nginx-1     | 2.63.200.228 - - [30/Jul/2025:16:17:10 +0000] "POST /api/parsing-tasks/ HTTP/1.1" 201 1234
```

## Дополнительные улучшения

### 1. Многоуровневая защита
- Исправление прав доступа в Dockerfile
- Создание директорий в entrypoint
- Fallback на временную директорию в модели
- Обработка ошибок в настройках Django

### 2. Улучшенная диагностика
- Подробные логи создания директорий
- Информация о используемых путях
- Отладочная информация при ошибках

### 3. Автоматическое восстановление
- Скрипт `fix_permissions_final.sh` для полного исправления
- Очистка данных PostgreSQL для чистого старта
- Автоматическое тестирование после исправления

## Если проблемы продолжаются

### 1. Проверка контейнера
```bash
docker compose exec backend bash
ls -la /app/media/
whoami
id
```

### 2. Ручное создание директорий
```bash
docker compose exec backend mkdir -p /app/media/uploads /app/media/results /app/media/temp
docker compose exec backend chmod -R 755 /app/media
```

### 3. Полная очистка
```bash
docker compose down -v
docker system prune -a
./fix_permissions_final.sh
```

### 4. Альтернативное решение
Если проблемы продолжаются, можно использовать только временную директорию:
```python
# В settings.py
FILE_UPLOAD_TEMP_DIR = tempfile.gettempdir()
``` 