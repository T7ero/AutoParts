#!/bin/bash

echo "🔧 Исправление проблем с базой данных..."

# Останавливаем все сервисы
echo "⏹️ Останавливаем сервисы..."
docker compose down

# Очищаем данные PostgreSQL если есть проблемы
echo "🧹 Очищаем данные PostgreSQL..."
if [ -d "./pg_data" ]; then
    echo "⚠️ Найдена директория pg_data. Удаляем для чистой установки..."
    sudo rm -rf ./pg_data
fi

# Очищаем кеш Docker
echo "🧹 Очищаем кеш Docker..."
docker system prune -f

# Пересобираем образы
echo "🔨 Пересобираем образы..."
docker compose build --no-cache

# Запускаем сервисы
echo "🚀 Запускаем сервисы..."
docker compose up -d

# Ждем готовности сервисов
echo "⏳ Ждем готовности сервисов..."
sleep 30

# Проверяем статус
echo "📊 Статус сервисов:"
docker compose ps

# Проверяем логи базы данных
echo "📋 Логи базы данных:"
docker compose logs db

echo "✅ Исправление завершено!"
echo "🌐 Приложение доступно по адресу: http://localhost"
echo "📝 Логи: docker compose logs -f" 