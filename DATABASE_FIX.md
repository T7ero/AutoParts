# Исправление проблемы с базой данных

## Проблема
```
ERROR: relation "auth_user" does not exist
```

## Причина
База данных не инициализирована - таблицы Django не созданы.

## Решение

### Вариант 1: Автоматическое исправление (рекомендуется)

Используйте обновленный Dockerfile и docker-compose.yml:

```bash
# Остановить все контейнеры
docker compose down

# Пересобрать образы
docker compose build --no-cache

# Запустить с новой конфигурацией
docker compose up -d
```

### Вариант 2: Ручное исправление

Если автоматическое исправление не работает:

```bash
# 1. Остановить контейнеры
docker compose down

# 2. Удалить старые данные базы
sudo rm -rf ./pg_data

# 3. Запустить только базу данных
docker compose up -d db

# 4. Подождать готовности базы
sleep 10

# 5. Запустить backend и выполнить миграции
docker compose up -d backend
docker exec -it autoparts-backend-1 python3 manage.py migrate

# 6. Создать суперпользователя
docker exec -it autoparts-backend-1 python3 manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    print('Superuser created')
else:
    print('Superuser already exists')
"

# 7. Запустить остальные сервисы
docker compose up -d
```

### Вариант 3: Использовать скрипт инициализации

```bash
# Сделать скрипт исполняемым (Linux/Mac)
chmod +x init_db.sh

# Запустить инициализацию
./init_db.sh

# Или с очисткой старых данных
./init_db.sh --clean
```

## Внесенные исправления

### 1. Обновленный Dockerfile
- Добавлен скрипт entrypoint.sh с автоматическими миграциями
- Ожидание готовности базы данных
- Автоматическое создание суперпользователя

### 2. Обновленный docker-compose.yml
- Добавлены healthcheck для базы данных и Redis
- Правильные зависимости между сервисами
- Использование entrypoint.sh для backend и celery

### 3. Скрипт инициализации init_db.sh
- Автоматическая инициализация базы данных
- Проверка статуса сервисов
- Очистка старых данных при необходимости

## Проверка работоспособности

### 1. Проверка статуса сервисов
```bash
docker compose ps
```

### 2. Проверка логов
```bash
docker compose logs backend
```

### 3. Проверка базы данных
```bash
docker exec -it autoparts-db-1 psql -U postgres -d autoparts -c "\dt"
```

### 4. Проверка входа в систему
- URL: http://localhost/login
- Логин: admin
- Пароль: admin

## Ожидаемые результаты

### После исправления
- Успешная инициализация базы данных
- Создание всех необходимых таблиц Django
- Работающий суперпользователь admin/admin
- Стабильная работа приложения

### Логи успешной инициализации
```
Waiting for database...
Database is ready!
Running migrations...
Creating superuser...
Superuser created
```

## Если проблемы продолжаются

### 1. Проверьте подключение к базе
```bash
docker exec -it autoparts-backend-1 python3 manage.py check --database default
```

### 2. Проверьте миграции
```bash
docker exec -it autoparts-backend-1 python3 manage.py showmigrations
```

### 3. Принудительно выполните миграции
```bash
docker exec -it autoparts-backend-1 python3 manage.py migrate --run-syncdb
```

### 4. Создайте суперпользователя вручную
```bash
docker exec -it autoparts-backend-1 python3 manage.py createsuperuser
```

## Дополнительные команды

### Очистка всех данных
```bash
docker compose down -v
sudo rm -rf ./pg_data
docker system prune -a
```

### Пересборка с нуля
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Просмотр логов в реальном времени
```bash
docker compose logs -f backend
```

## Быстрое решение

Если нужно быстро исправить проблему:

```bash
# Остановить все
docker compose down

# Удалить данные базы
sudo rm -rf ./pg_data

# Пересобрать и запустить
docker compose build --no-cache
docker compose up -d

# Подождать и проверить
sleep 30
docker compose ps
``` 