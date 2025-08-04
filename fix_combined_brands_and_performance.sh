#!/bin/bash

echo "🔧 Исправления объединенных брендов и производительности..."

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
echo "1. Добавлена функция split_combined_brands для разделения объединенных брендов"
echo "2. GSPARTSHINOTOYOTA / LEXUS теперь разделяется на GSPARTS, HINO, TOYOTA, LEXUS"
echo "3. Увеличен таймаут Celery задачи до 3 часов"
echo "4. Увеличены таймауты для Autopiter/Emex до 120с, Armtek до 300с"
echo "5. Улучшена фильтрация мусора в Armtek"
echo "6. Добавлены исключения для объединенных брендов"
echo ""
echo "📋 Ожидаемые результаты:"
echo "- Armtek: GSPARTSHINOTOYOTA / LEXUS → GSPARTS, HINO, TOYOTA, LEXUS"
echo "- Обработка всех 123 артикулов без таймаута"
echo "- Ускоренная обработка благодаря увеличенным таймаутам"
echo "- Чистые бренды без мусора"
echo ""
echo "📊 Мониторинг работы:"
echo "docker compose logs -f celery" 