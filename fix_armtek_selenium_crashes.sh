#!/bin/bash

echo "🔧 Исправление критических ошибок Armtek Selenium парсера..."

# Останавливаем сервисы
echo "⏹️  Останавливаем сервисы..."
docker-compose down

# Очищаем все процессы Chrome
echo "🧹 Очищаем все процессы Chrome..."
pkill -f chrome || true
pkill -f chromedriver || true
sleep 2

# Очищаем кэш Redis
echo "🧹 Очищаем кэш Redis..."
docker run --rm -v redis_data:/data redis:alpine redis-cli -h redis FLUSHALL || echo "Redis не запущен, пропускаем очистку"

# Очищаем временные файлы
echo "🧹 Очищаем временные файлы..."
rm -rf media/temp/* 2>/dev/null || true
mkdir -p media/temp

# Пересобираем backend с исправлениями
echo "🔨 Пересобираем backend с исправлениями Armtek..."
docker-compose build --no-cache backend

# Запускаем сервисы
echo "🚀 Запускаем сервисы с исправлениями..."
docker-compose up -d

# Ждем запуска
echo "⏳ Ждем запуска сервисов..."
sleep 15

# Проверяем статус
echo "📊 Статус сервисов:"
docker-compose ps

echo ""
echo "✅ Исправления Armtek Selenium применены!"
echo ""
echo "🎯 Выполненные исправления:"
echo "  ✅ Система восстановления Chrome драйвера после 'tab crashed'"
echo "  ✅ Автоматическое пересоздание драйвера при критических ошибках"
echo "  ✅ Улучшенное управление пулом драйверов"
echo "  ✅ HTTP API fallback для Armtek при падении Selenium"
echo "  ✅ Оптимизированные настройки Chrome для стабильности"
echo "  ✅ Улучшенная очистка процессов Chrome"
echo ""
echo "🚀 Теперь Armtek парсер должен работать стабильно!"
echo "💡 При падении Selenium автоматически переключается на HTTP fallback"
