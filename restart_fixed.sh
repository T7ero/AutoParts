#!/bin/bash

echo "🔧 Перезапуск с исправлениями базы данных..."

# Останавливаем все сервисы
echo "⏹️ Останавливаем сервисы..."
docker compose down

# Очищаем данные PostgreSQL
echo "🧹 Очищаем данные PostgreSQL..."
if [ -d "./pg_data" ]; then
    echo "⚠️ Удаляем старые данные PostgreSQL..."
    sudo rm -rf ./pg_data
fi

# Очищаем кеш Docker
echo "🧹 Очищаем кеш Docker..."
docker system prune -f

# Пересобираем образы
echo "🔨 Пересобираем образы..."
docker compose build --no-cache backend

# Запускаем только базу данных и ждем
echo "🚀 Запускаем базу данных..."
docker compose up -d db redis

echo "⏳ Ждем готовности базы данных..."
sleep 15

# Проверяем статус базы данных
echo "📊 Проверяем статус базы данных..."
docker compose ps db redis

# Запускаем backend
echo "🚀 Запускаем backend..."
docker compose up -d backend

echo "⏳ Ждем готовности backend..."
sleep 10

# Запускаем остальные сервисы
echo "🚀 Запускаем остальные сервисы..."
docker compose up -d

# Ждем готовности всех сервисов
echo "⏳ Ждем готовности всех сервисов..."
sleep 20

# Проверяем статус
echo "📊 Статус сервисов:"
docker compose ps

# Проверяем логи backend
echo "📋 Логи backend:"
docker compose logs backend --tail=20

echo "✅ Перезапуск завершен!"
echo "🌐 Приложение доступно по адресу: http://localhost"
echo "📝 Логи: docker compose logs -f" 