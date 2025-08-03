#!/bin/bash

echo "🔧 Исправление ошибок Celery и 405..."

# Останавливаем контейнеры
echo "⏹️ Останавливаем контейнеры..."
docker compose down

# Очищаем кэш и образы
echo "🧹 Очищаем кэш Docker..."
docker system prune -f
docker volume prune -f

# Пересобираем все контейнеры
echo "🔨 Пересобираем контейнеры..."
docker compose build --no-cache

# Запускаем контейнеры
echo "🚀 Запускаем контейнеры..."
docker compose up -d

# Ждем готовности сервисов
echo "⏳ Ожидание готовности сервисов..."
sleep 60

# Проверяем статус
echo "📊 Проверяем статус сервисов..."
docker compose ps

echo "✅ Исправления применены!"
echo "🌐 Приложение доступно по адресу: http://87.228.101.164"
echo "🔗 Страница прокси: http://87.228.101.164/proxy-manager"
echo ""
echo "📝 Логи для проверки:"
echo "docker compose logs -f" 