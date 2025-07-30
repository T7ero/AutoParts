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