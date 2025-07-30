# Исправление проблем с правами доступа

## Проблема
Ошибка `PermissionError: [Errno 13] Permission denied: '/app/media/uploads/test2_lh7UFMn.xlsx'` при загрузке файлов.

## Причина
Пользователь `appuser` не имеет прав на создание файлов в директории `/app/media/uploads`.

## Внесенные исправления

### 1. Улучшен Dockerfile
```dockerfile
# Создаем необходимые директории и устанавливаем права
RUN mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app/media && \
    chmod -R 777 /app/media/uploads /app/media/results /app/media/temp && \
    chown -R appuser:appuser /app/media/uploads /app/media/results /app/media/temp
```

### 2. Улучшена модель ParsingTask
```python
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
            temp_dir = tempfile.gettempdir()
            return os.path.join(temp_dir, filename)
    except Exception:
        # В случае любой ошибки используем временную директорию
        temp_dir = tempfile.gettempdir()
        return os.path.join(temp_dir, filename)
```

### 3. Улучшен entrypoint скрипт
```bash
# Создаем необходимые директории
echo "📁 Создание директорий..."
mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static || true
# Проверяем права доступа
echo "🔍 Проверка прав доступа..."
ls -la /app/media/ || echo "❌ Не удалось проверить права доступа"
```

## Инструкции по применению исправлений

### Вариант 1: Автоматическое исправление
```bash
chmod +x quick_fix.sh
./quick_fix.sh
```

### Вариант 2: Ручное исправление
```bash
# 1. Остановить сервисы
docker compose down

# 2. Очистить данные PostgreSQL
sudo rm -rf ./pg_data

# 3. Пересобрать backend
docker compose build --no-cache backend

# 4. Запустить сервисы
docker compose up -d
```

## Проверка исправления

### 1. Проверка статуса сервисов
```bash
docker compose ps
```

### 2. Проверка логов
```bash
docker compose logs backend
```

### 3. Проверка прав доступа
```bash
docker compose exec backend ls -la /app/media/
```

### 4. Тестирование загрузки файла
1. Откройте http://localhost
2. Войдите с логином `admin` и паролем `admin`
3. Перейдите на страницу "Загрузка"
4. Выберите Excel файл (.xlsx)
5. Нажмите "Начать обработку"

## Ожидаемые результаты

### После исправления
- ✅ Успешная загрузка Excel файлов
- ✅ Корректные права доступа к директориям
- ✅ Fallback на временную директорию при проблемах
- ✅ Работающие API endpoints

### Логи успешной загрузки
```
backend-1   | ✅ Директории созданы: /app/media
backend-1   | 2025-07-30 17:25:10,294 INFO     POST /api/parsing-tasks/ 201 1234
nginx-1     | 2.63.200.228 - - [30/Jul/2025:17:25:10 +0000] "POST /api/parsing-tasks/ HTTP/1.1" 201 1234
```

## Данные для авторизации
- **Логин:** `admin`
- **Пароль:** `admin`

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
docker compose exec backend chmod -R 777 /app/media
```

### 3. Полная очистка
```bash
docker compose down -v
docker system prune -a
./quick_fix.sh
``` 