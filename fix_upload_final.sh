#!/bin/bash

echo "🔧 Финальное исправление проблем с загрузкой файлов..."

# Останавливаем сервисы
echo "⏹️ Останавливаем сервисы..."
docker compose down

# Очищаем данные PostgreSQL
echo "🧹 Очищаем данные PostgreSQL..."
sudo rm -rf ./pg_data

# Пересобираем backend
echo "🔨 Пересобираем backend..."
docker compose build --no-cache backend

# Запускаем сервисы
echo "🚀 Запускаем сервисы..."
docker compose up -d

# Ждем готовности сервисов
echo "⏳ Ждем готовности сервисов..."
sleep 30

# Проверяем статус
echo "📊 Статус сервисов:"
docker compose ps

# Проверяем логи backend
echo "📋 Логи backend:"
docker compose logs backend --tail=10

# Проверяем права доступа
echo "🔍 Проверяем права доступа:"
docker compose exec backend ls -la /app/media/ || echo "❌ Не удалось проверить права доступа"

echo "✅ Исправление завершено!"
echo "🌐 Приложение доступно по адресу: http://localhost"
echo "👤 Логин: admin"
echo "🔑 Пароль: admin"
echo "📝 Логи: docker compose logs -f" 