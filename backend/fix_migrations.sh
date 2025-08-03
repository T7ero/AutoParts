#!/bin/bash

echo "🔄 Выполнение миграций базы данных..."

# Выполняем makemigrations
echo "📝 Создание миграций..."
python3 manage.py makemigrations core

# Выполняем migrate
echo "🔄 Применение миграций..."
python3 manage.py migrate

echo "✅ Миграции выполнены успешно!" 