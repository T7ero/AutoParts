# Исправление проблем с подключением к базе данных

## Проблема
Сервисы не могут подключиться к базе данных PostgreSQL, постоянно выводя сообщения "Database not ready, waiting...".

## Причина
Проблемы с healthcheck и настройками подключения к базе данных.

## Внесенные исправления

### 1. Улучшен healthcheck для PostgreSQL
```yaml
# docker-compose.yml
db:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U postgres -d autoparts"]
    interval: 5s
    timeout: 5s
    retries: 10
    start_period: 10s
```

### 2. Улучшен healthcheck для Redis
```yaml
# docker-compose.yml
redis:
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 3s
    retries: 5
```

### 3. Создан отдельный entrypoint скрипт
```bash
# backend/entrypoint.sh
#!/bin/bash

# Ждем готовности базы данных
echo "Waiting for database..."

max_attempts=60
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if python3 manage.py check --database default 2>/dev/null; then
        echo "Database is ready!"
        break
    else
        echo "Database not ready, waiting... (attempt $((attempt + 1))/$max_attempts)"
        sleep 5
        attempt=$((attempt + 1))
    fi
done

if [ $attempt -eq $max_attempts ]; then
    echo "ERROR: Database connection failed after $max_attempts attempts"
    echo "Trying to connect to database manually..."
    
    # Попытка подключения через psql
    if command -v psql >/dev/null 2>&1; then
        echo "Testing PostgreSQL connection..."
        if PGPASSWORD=postgres psql -h db -U postgres -d autoparts -c "SELECT 1;" >/dev/null 2>&1; then
            echo "PostgreSQL connection successful"
        else
            echo "PostgreSQL connection failed"
        fi
    fi
    
    exit 1
fi

# Выполняем миграции
echo "Running migrations..."
python3 manage.py migrate

# Создаем суперпользователя если не существует
echo "Creating superuser..."
python3 manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    print('Superuser created')
else:
    print('Superuser already exists')
"

# Запускаем Xvfb
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1280x720x24 &
export DISPLAY=:99

# Запускаем приложение
echo "Starting application..."
exec "$@"
```

### 4. Улучшены настройки базы данных в Django
```python
# backend/backend/settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'autoparts',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': 'db',
        'PORT': '5432',
        'OPTIONS': {
            'connect_timeout': 10,
            'options': '-c statement_timeout=60000',
        },
        'CONN_MAX_AGE': 60,
        'CONN_HEALTH_CHECKS': True,
    }
}
```

### 5. Обновлен Dockerfile
```dockerfile
# backend/Dockerfile
# Копируем entrypoint скрипт
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
```

## Проверка исправления

### 1. Автоматическое исправление
```bash
./fix_database.sh
```

### 2. Ручное исправление
```bash
# Остановить сервисы
docker compose down

# Очистить данные PostgreSQL
sudo rm -rf ./pg_data

# Пересобрать образы
docker compose build --no-cache

# Запустить сервисы
docker compose up -d
```

### 3. Проверка статуса
```bash
# Проверить статус сервисов
docker compose ps

# Проверить логи базы данных
docker compose logs db

# Проверить логи backend
docker compose logs backend
```

## Ожидаемые результаты

### После исправления
- Успешное подключение к базе данных
- Корректное выполнение миграций
- Создание суперпользователя
- Стабильная работа приложения

### Логи успешного запуска
```
db-1        | 2025-07-30 06:51:55.296 UTC [1] LOG:  database system is ready to accept connections
backend-1   | Database is ready!
backend-1   | Running migrations...
backend-1   | Superuser already exists
backend-1   | Starting Xvfb...
backend-1   | Starting application...
```

## Дополнительные улучшения

### 1. Скрипт автоматического исправления
Создан `fix_database.sh` для автоматического исправления проблем с базой данных.

### 2. Улучшенная диагностика
- Более информативные сообщения об ошибках
- Проверка подключения через psql
- Лимит попыток подключения

### 3. Оптимизация производительности
- Увеличены таймауты подключения
- Настроены health checks
- Улучшена обработка ошибок

## Если проблемы продолжаются

### 1. Проверка сетевых настроек
```bash
docker network ls
docker network inspect autoparts_default
```

### 2. Проверка контейнера базы данных
```bash
docker compose exec db psql -U postgres -d autoparts -c "SELECT version();"
```

### 3. Проверка переменных окружения
```bash
docker compose exec backend env | grep DATABASE
```

### 4. Полная очистка и перезапуск
```bash
docker compose down -v
docker system prune -a
./fix_database.sh
``` 