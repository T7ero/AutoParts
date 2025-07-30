# Исправление проблем с правами доступа

## Проблема
Ошибка `PermissionError: [Errno 13] Permission denied: '/app/media/temp'` при запуске backend и celery сервисов.

## Причина
Пользователь `appuser` не имеет прав на создание директорий в `/app/media`.

## Внесенные исправления

### 1. Исправлены настройки Django
```python
# backend/backend/settings.py
# Создаем директории если их нет (с обработкой ошибок)
try:
    os.makedirs(MEDIA_ROOT, exist_ok=True)
    os.makedirs(os.path.join(MEDIA_ROOT, 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(MEDIA_ROOT, 'results'), exist_ok=True)
    os.makedirs(FILE_UPLOAD_TEMP_DIR, exist_ok=True)
except PermissionError:
    # Если нет прав, используем временную директорию
    import tempfile
    FILE_UPLOAD_TEMP_DIR = tempfile.gettempdir()
    print(f"⚠️ Используем временную директорию: {FILE_UPLOAD_TEMP_DIR}")
except Exception as e:
    print(f"⚠️ Ошибка создания директорий: {e}")
    # Используем временную директорию как fallback
    import tempfile
    FILE_UPLOAD_TEMP_DIR = tempfile.gettempdir()
```

### 2. Обновлен Dockerfile
```dockerfile
# backend/Dockerfile
# Создаем необходимые директории и устанавливаем права
RUN mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static && \
    chown -R appuser:appuser /app
```

### 3. Улучшен entrypoint скрипт
```bash
# backend/entrypoint.sh
# Создаем необходимые директории
echo "📁 Создание директорий..."
mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static || true
```

## Проверка исправления

### 1. Автоматическое исправление
```bash
./fix_permissions.sh
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

### 3. Проверка статуса
```bash
# Проверить статус сервисов
docker compose ps

# Проверить логи backend
docker compose logs backend

# Проверить права доступа в контейнере
docker compose exec backend ls -la /app/media/
```

## Ожидаемые результаты

### После исправления
- Успешный запуск backend и celery сервисов
- Корректное создание директорий
- Работающие API endpoints
- Успешная авторизация

### Логи успешного запуска
```
backend-1   | 🚀 Запуск AutoParts Backend...
backend-1   | 📁 Создание директорий...
backend-1   | ⏳ Ожидание готовности базы данных...
backend-1   | ✅ Подключение к PostgreSQL успешно!
backend-1   | ✅ База данных готова!
backend-1   | 🔄 Выполнение миграций...
backend-1   | 👤 Создание суперпользователя...
backend-1   | 🖥️ Запуск Xvfb...
backend-1   | ✅ Xvfb запущен
backend-1   | 🚀 Запуск приложения...
```

## Дополнительные улучшения

### 1. Скрипт автоматического исправления
Создан `fix_permissions.sh` для автоматического исправления проблем с правами доступа.

### 2. Улучшенная обработка ошибок
- Fallback на временную директорию при ошибках прав доступа
- Более информативные сообщения об ошибках
- Автоматическое создание директорий при запуске

### 3. Оптимизация производительности
- Правильная последовательность создания директорий
- Корректные права доступа
- Улучшенная диагностика

## Если проблемы продолжаются

### 1. Проверка прав доступа
```bash
docker compose exec backend ls -la /app/
docker compose exec backend whoami
```

### 2. Проверка директорий
```bash
docker compose exec backend find /app -type d -ls
```

### 3. Ручное создание директорий
```bash
docker compose exec backend mkdir -p /app/media/uploads /app/media/results /app/media/temp
```

### 4. Полная очистка и перезапуск
```bash
docker compose down -v
docker system prune -a
./fix_permissions.sh
``` 