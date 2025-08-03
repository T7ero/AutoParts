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
python3 manage.py migrate

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

# Запускаем Xvfb для Selenium (проверяем, не запущен ли уже)
echo "🖥️ Запуск виртуального дисплея..."
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