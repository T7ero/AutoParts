#!/bin/bash

echo "🔧 Исправление фильтрации брендов для Autopiter и Armtek..."

# Останавливаем контейнеры
echo "⏹️ Останавливаем контейнеры..."
docker compose down

# Пересобираем контейнеры
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
echo ""
echo "📝 Логи для проверки:"
echo "docker compose logs -f celery"
echo ""
echo "🔍 Изменения:"
echo "1. Autopiter: добавлена строгая фильтрация брендов"
echo "2. Armtek: добавлена строгая фильтрация брендов"
echo "3. Убраны все элементы интерфейса и навигации"
echo "4. Оставлены только чистые названия брендов"
echo ""
echo "📋 Ожидаемые результаты:"
echo "- Autopiter: только бренды (Дизель, JAC, Jashi, Sollers)"
echo "- Armtek: только бренды (PAZ, PRC, JAC, SOLLERS)"
echo "- Emex: продолжит работать как раньше"
echo ""
echo "📊 Мониторинг работы:"
echo "docker compose logs -f celery" 