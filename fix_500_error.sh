#!/bin/bash

echo "🔧 Исправление ошибки 500 Internal Server Error..."

# Применяем миграцию
echo "🔄 Применение миграции..."
docker compose exec backend python3 manage.py makemigrations core
docker compose exec backend python3 manage.py migrate

# Перезапускаем backend
echo "🔄 Перезапуск backend..."
docker compose restart backend

# Ждем готовности backend
echo "⏳ Ожидание готовности backend..."
sleep 10

echo "✅ Исправления применены!"
echo "🌐 Проверьте: http://87.228.101.164/upload" 