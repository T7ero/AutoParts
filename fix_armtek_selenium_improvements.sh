#!/bin/bash

echo "🔧 Применяем улучшения Armtek парсера..."

# Останавливаем контейнеры
echo "⏹️ Останавливаем контейнеры..."
docker-compose down

# Очищаем кэш Redis
echo "🧹 Очищаем кэш Redis..."
docker-compose run --rm redis redis-cli FLUSHALL

# Очищаем временные файлы
echo "🗑️ Очищаем временные файлы..."
rm -rf media/temp/*
rm -rf /tmp/chrome_*
rm -rf /tmp/chromium_*

# Убиваем процессы Chrome
echo "🔪 Убиваем процессы Chrome..."
pkill -f chrome || true
pkill -f chromedriver || true

# Пересобираем backend с новыми изменениями
echo "🔨 Пересобираем backend..."
docker-compose build --no-cache backend

# Запускаем контейнеры
echo "🚀 Запускаем контейнеры..."
docker-compose up -d

# Ждем запуска
echo "⏳ Ждем запуска сервисов..."
sleep 10

# Проверяем статус
echo "📊 Проверяем статус контейнеров..."
docker-compose ps

echo "✅ Улучшения Armtek парсера применены!"
echo ""
echo "Основные улучшения:"
echo "• Увеличены таймауты для стабильности (5-10 сек)"
echo "• Улучшены селекторы для поиска брендов"
echo "• Добавлено детальное логирование"
echo "• Улучшен fallback механизм"
echo "• Расширен API fallback с BeautifulSoup"
echo "• Улучшена обработка ошибок"
echo ""
echo "Теперь Armtek парсер должен работать более стабильно и находить больше брендов!"
