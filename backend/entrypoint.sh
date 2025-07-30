#!/bin/bash

set -e

echo "🚀 Запуск AutoParts Backend..."

# Создаем необходимые директории с правильными правами
echo "📁 Создание директорий..."
mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static
chmod -R 775 /app/media
chown -R appuser:appuser /app/media || echo "⚠️ Не удалось изменить владельца директорий"

# Проверяем права доступа
echo "🔍 Проверка прав доступа..."
ls -la /app/media/

# Ждем готовности базы данных
echo "⏳ Ожидание готовности базы данных..."

max_attempts=120
attempt=0

while [ $attempt -lt $max_attempts ]; do
    echo "Попытка подключения к базе данных... (попытка $((attempt + 1))/$max_attempts)"
    
    if python3 manage.py check --database default 2>/dev/null; then
        echo "✅ База данных готова!"
        break
    fi
    
    sleep 2
    attempt=$((attempt + 1))
done

if [ $attempt -eq $max_attempts ]; then
    echo "💥 ОШИБКА: Не удалось подключиться к базе данных"
    exit 1
fi

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

# Запускаем приложение
echo "🚀 Запуск приложения..."
exec "$@"