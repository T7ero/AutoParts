#!/bin/bash

echo "🔧 Пересборка только frontend для исправления ошибки 405..."

# Останавливаем frontend
echo "⏹️ Останавливаем frontend..."
docker compose stop frontend

# Удаляем образ frontend
echo "🗑️ Удаляем образ frontend..."
docker compose rm -f frontend
docker rmi $(docker images -q autoparts-frontend) 2>/dev/null || true

# Пересобираем frontend
echo "🔨 Пересобираем frontend..."
docker compose build --no-cache frontend

# Запускаем frontend
echo "🚀 Запускаем frontend..."
docker compose up -d frontend

echo "✅ Frontend пересобран!"
echo "🌐 Проверьте: http://87.228.101.164/upload" 