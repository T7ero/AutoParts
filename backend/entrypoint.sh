#!/bin/bash
set -e

# Если не root, перезапускаем скрипт через gosu
if [ "$(id -u)" = "0" ]; then
    # Запускаем подготовку от root
    echo "🔧 Настройка прав доступа..."
    mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static
    chown -R appuser:appuser /app/media
    chmod -R 775 /app/media
    
    # Переключаемся на appuser и запускаем основной скрипт
    exec gosu appuser "$0" "$@"
    exit $?
fi

# Основной код выполняется от appuser
echo "🚀 Запуск AutoParts Backend..."

# Проверяем права доступа
echo "🔍 Проверка прав доступа..."
ls -la /app/media/

# Ждем готовности базы данных
echo "⏳ Ожидание готовности базы данных..."
max_attempts=120
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if python3 manage.py check --database default 2>/dev/null; then
        echo "✅ База данных готова!"
        break
    fi
    echo "Попытка $((attempt + 1))/$max_attempts..."
    sleep 2
    attempt=$((attempt + 1))
done

if [ $attempt -eq $max_attempts ]; then
    echo "💥 Ошибка: Не удалось подключиться к базе данных"
    exit 1
fi

# Выполняем миграции
echo "🔄 Выполнение миграций..."
python3 manage.py migrate --noinput

# Создаем суперпользователя
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