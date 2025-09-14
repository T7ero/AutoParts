#!/bin/bash

echo "🔧 Исправление ошибок tab crashed в Armtek парсере..."

# Останавливаем сервисы
echo "⏹️  Останавливаем сервисы..."
docker-compose down

# Очищаем процессы Chrome
echo "🧹 Очищаем процессы Chrome..."
pkill -f chrome || true
pkill -f chromedriver || true

# Очищаем кэш Redis
echo "🧹 Очищаем кэш Redis..."
docker run --rm -v redis_data:/data redis:alpine redis-cli -h redis FLUSHALL || echo "Redis не запущен, пропускаем очистку"

# Пересобираем backend с исправлениями
echo "🔨 Пересобираем backend с исправлениями Armtek..."
docker-compose build --no-cache backend

# Запускаем сервисы
echo "🚀 Запускаем сервисы с исправлениями..."
docker-compose up -d

# Ждем запуска
echo "⏳ Ждем запуска сервисов..."
sleep 10

# Проверяем статус
echo "📊 Статус сервисов:"
docker-compose ps

echo ""
echo "✅ Исправления применены!"
echo ""
echo "🎯 Выполненные исправления:"
echo "   • Добавлен новый точный селектор для Armtek"
echo "   • Улучшена обработка ошибок 'tab crashed'"
echo "   • Добавлен механизм fallback через API"
echo "   • Улучшены настройки Chrome для стабильности"
echo "   • Добавлена очистка процессов Chrome при критических ошибках"
echo ""
echo "🚀 Теперь Armtek парсер должен работать стабильно!"
