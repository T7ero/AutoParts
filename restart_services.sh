#!/bin/bash

echo "🔄 Перезапуск сервисов AutoParts..."

# Останавливаем все сервисы
echo "⏹️ Останавливаем сервисы..."
docker compose down

# Очищаем зависшие процессы Chrome
echo "🧹 Очищаем зависшие процессы Chrome..."
docker compose exec celery pkill -f chrome 2>/dev/null || true
docker compose exec celery pkill -f chromedriver 2>/dev/null || true

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
sleep 10

# Проверяем статус
echo "📊 Статус сервисов:"
docker compose ps

echo "✅ Перезапуск завершен!"
echo "🌐 Приложение доступно по адресу: http://localhost"
echo "📝 Логи: docker compose logs -f"