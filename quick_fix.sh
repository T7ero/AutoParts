#!/bin/bash
echo "🔧 Быстрое исправление проблем с правами доступа..."

# Останавливаем сервисы
docker compose down

# Очищаем данные PostgreSQL
sudo rm -rf ./pg_data

# Пересобираем backend
docker compose build --no-cache backend

# Запускаем сервисы
docker compose up -d

echo "✅ Исправление завершено!"
echo "🌐 Приложение доступно по адресу: http://localhost"
echo "👤 Логин: admin"
echo "🔑 Пароль: admin" 