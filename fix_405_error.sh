#!/bin/bash

echo "🔧 Исправление ошибки 405 Method Not Allowed..."

# Останавливаем контейнеры
echo "⏹️ Останавливаем контейнеры..."
docker compose down

# Пересобираем frontend
echo "🔨 Пересобираем frontend..."
docker compose build --no-cache frontend

# Запускаем контейнеры
echo "🚀 Запускаем контейнеры..."
docker compose up -d

# Ждем готовности backend
echo "⏳ Ожидание готовности backend..."
sleep 30

# Выполняем миграции
echo "🔄 Выполняем миграции..."
docker compose exec backend python3 manage.py makemigrations core
docker compose exec backend python3 manage.py migrate

echo "✅ Исправления применены!"
echo "🌐 Приложение доступно по адресу: http://87.228.101.164" 