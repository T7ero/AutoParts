#!/bin/bash

echo "🔧 Исправление всех проблем..."

# Останавливаем контейнеры
echo "⏹️ Останавливаем контейнеры..."
docker compose down

# Очищаем кэш Docker
echo "🧹 Очищаем кэш Docker..."
docker system prune -f

# Пересобираем все контейнеры
echo "🔨 Пересобираем контейнеры..."
docker compose build --no-cache

# Запускаем контейнеры
echo "🚀 Запускаем контейнеры..."
docker compose up -d

# Ждем готовности сервисов
echo "⏳ Ожидание готовности сервисов..."
sleep 45

# Выполняем миграции
echo "🔄 Выполняем миграции..."
docker compose exec backend python3 manage.py makemigrations core
docker compose exec backend python3 manage.py migrate

# Проверяем статус
echo "📊 Проверяем статус сервисов..."
docker compose ps

echo "✅ Все исправления применены!"
echo "🌐 Приложение доступно по адресу: http://87.228.101.164"
echo "🔗 Страница прокси: http://87.228.101.164/proxy-manager"
echo ""
echo "📝 Логи для проверки:"
echo "docker compose logs -f" 