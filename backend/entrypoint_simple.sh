#!/bin/bash

set -e

echo "🔧 Настройка прав доступа..."

# Создаем директории если их нет
mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static
chmod -R 775 /app/media

# Ждем готовности базы данных
echo "⏳ Ожидание готовности базы данных..."
max_attempts=120
attempt=0

while [ $attempt -lt $max_attempts ]; do
    echo "Попытка подключения к базе данных... (попытка $((attempt + 1))/$max_attempts)"
    
    if command -v psql >/dev/null 2>&1; then
        if PGPASSWORD=postgres psql -h db -U postgres -d autoparts -c "SELECT 1;" >/dev/null 2>&1; then
            echo "✅ Подключение к PostgreSQL успешно!"
            break
        else
            echo "❌ Подключение к PostgreSQL не удалось"
        fi
    fi
    
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
    echo "❌ Не удалось подключиться к базе данных после $max_attempts попыток"
    exit 1
fi

# Выполняем миграции
echo "🔄 Выполнение миграций..."
max_migrate_attempts=20
migrate_attempt=0
until python3 manage.py migrate --noinput; do
    migrate_attempt=$((migrate_attempt + 1))
    if [ $migrate_attempt -ge $max_migrate_attempts ]; then
        echo "❌ Миграции не удалось применить после $max_migrate_attempts попыток"
        exit 1
    fi
    echo "⚠️ Миграции не применились (DB еще поднимается?), повтор через 5 секунд... ($migrate_attempt/$max_migrate_attempts)"
    sleep 5
done

# Создаем суперпользователя только по явному флагу (без дефолтного admin/admin)
if [ "${CREATE_SUPERUSER:-0}" = "1" ]; then
    echo "👤 Создание суперпользователя (CREATE_SUPERUSER=1)..."
    python3 manage.py shell -c "
from django.contrib.auth.models import User
import os
username = os.getenv('ADMIN_USERNAME', 'admin')
email = os.getenv('ADMIN_EMAIL', 'admin@example.com')
password = os.getenv('ADMIN_PASSWORD', '')
if not password:
    print('❌ ADMIN_PASSWORD пустой — суперпользователь не создан')
else:
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username, email, password)
        print('✅ Суперпользователь создан')
    else:
        print('ℹ️ Суперпользователь уже существует')
"
else
    echo "ℹ️ CREATE_SUPERUSER=0 — пропускаем создание суперпользователя"
fi

# Запускаем Xvfb для Selenium (проверяем, не запущен ли уже)
echo "🖥️ Запуск виртуального дисплея..."
# Удаляем старый lock файл если есть
rm -f /tmp/.X99-lock
if ! pgrep -x "Xvfb" > /dev/null; then
    Xvfb :99 -screen 0 1280x720x24 &
    echo "✅ Xvfb запущен"
else
    echo "ℹ️ Xvfb уже запущен"
fi
export DISPLAY=:99

# Очищаем процессы Chrome если есть
echo "🧹 Очистка процессов Chrome..."
pkill -f chrome || true
pkill -f chromedriver || true

echo "✅ Настройка завершена!"

# Запускаем команду
exec "$@" 