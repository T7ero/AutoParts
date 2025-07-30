#!/bin/bash

set -e

echo "🚀 Запуск AutoParts Backend..."

# Создаем необходимые директории с правильными правами
echo "📁 Создание директорий..."
mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static || true
chmod -R 755 /app/media || true

# Ждем готовности базы данных
echo "⏳ Ожидание готовности базы данных..."

max_attempts=120
attempt=0

while [ $attempt -lt $max_attempts ]; do
    echo "Попытка подключения к базе данных... (попытка $((attempt + 1))/$max_attempts)"
    
    # Проверяем подключение через psql
    if command -v psql >/dev/null 2>&1; then
        if PGPASSWORD=postgres psql -h db -U postgres -d autoparts -c "SELECT 1;" >/dev/null 2>&1; then
            echo "✅ Подключение к PostgreSQL успешно!"
            break
        else
            echo "❌ Подключение к PostgreSQL не удалось"
        fi
    fi
    
    # Проверяем через Django
    if python3 manage.py check --database default 2>/dev/null; then
        echo "✅ Django подключение к базе данных успешно!"
        break
    else
        echo "❌ Django подключение к базе данных не удалось"
    fi
    
    echo "⏳ Ожидание 5 секунд..."
    sleep 5
    attempt=$((attempt + 1))
done

if [ $attempt -eq $max_attempts ]; then
    echo "💥 ОШИБКА: Не удалось подключиться к базе данных после $max_attempts попыток"
    echo "🔍 Диагностика:"
    
    # Проверяем сеть
    echo "📡 Проверка сети..."
    ping -c 3 db || echo "❌ Не удается пинговать db"
    
    # Проверяем порт
    echo "🔌 Проверка порта PostgreSQL..."
    nc -z db 5432 && echo "✅ Порт 5432 доступен" || echo "❌ Порт 5432 недоступен"
    
    # Проверяем переменные окружения
    echo "🔧 Переменные окружения:"
    echo "DATABASE_URL: $DATABASE_URL"
    echo "POSTGRES_DB: $POSTGRES_DB"
    echo "POSTGRES_USER: $POSTGRES_USER"
    
    exit 1
fi

echo "✅ База данных готова!"

# Выполняем миграции
echo "🔄 Выполнение миграций..."
python3 manage.py migrate --noinput

# Создаем суперпользователя если не существует
echo "👤 Создание суперпользователя..."
python3 manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    print('✅ Суперпользователь создан')
else:
    print('ℹ️ Суперпользователь уже существует')
"

# Запускаем Xvfb
echo "🖥️ Запуск Xvfb..."
Xvfb :99 -screen 0 1280x720x24 &
export DISPLAY=:99

# Проверяем что Xvfb запустился
sleep 2
if pgrep Xvfb >/dev/null; then
    echo "✅ Xvfb запущен"
else
    echo "⚠️ Xvfb не запустился, но продолжаем..."
fi

# Запускаем приложение
echo "🚀 Запуск приложения..."
exec "$@" 