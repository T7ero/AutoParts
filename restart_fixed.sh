#!/bin/bash

echo "🔄 Перезапуск системы AutoParts с исправлениями..."

# Останавливаем все контейнеры
echo "⏹️ Остановка контейнеров..."
docker compose down

# Удаляем старые образы
echo "🗑️ Удаление старых образов..."
docker system prune -f

# Пересобираем образы
echo "🔨 Пересборка образов..."
docker compose build --no-cache

# Запускаем систему
echo "🚀 Запуск системы..."
docker compose up -d

# Ждем запуска
echo "⏳ Ожидание запуска сервисов..."
sleep 10

# Проверяем статус
echo "📊 Проверка статуса..."
docker compose ps

# Показываем логи
echo "📋 Логи системы:"
docker compose logs --tail=20

echo "✅ Система перезапущена!"
echo "🌐 Доступ к веб-интерфейсу: http://localhost"
echo "👤 Логин: admin"
echo "🔑 Пароль: admin" 