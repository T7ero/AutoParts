#!/bin/bash

echo "🔧 Исправление проблем с загрузкой файлов..."

# Останавливаем все сервисы
echo "⏹️ Останавливаем сервисы..."
docker compose down

# Пересобираем образы
echo "🔨 Пересобираем образы..."
docker compose build --no-cache backend

# Запускаем сервисы
echo "🚀 Запускаем сервисы..."
docker compose up -d

# Ждем готовности сервисов
echo "⏳ Ждем готовности сервисов..."
sleep 20

# Проверяем статус
echo "📊 Статус сервисов:"
docker compose ps

# Проверяем логи backend
echo "📋 Логи backend:"
docker compose logs backend --tail=20

# Тестируем загрузку файла
echo "🧪 Тестируем загрузку файла..."
python3 test_upload_fix.py

echo "✅ Исправление завершено!"
echo "🌐 Приложение доступно по адресу: http://localhost"
echo "📝 Логи: docker compose logs -f" 