#!/bin/bash

echo "🔄 Создание и применение миграции для поля user..."

# Создаем миграцию
echo "📝 Создание миграции..."
docker compose exec backend python3 manage.py makemigrations core

# Применяем миграцию
echo "🔄 Применение миграции..."
docker compose exec backend python3 manage.py migrate

echo "✅ Миграция выполнена успешно!" 