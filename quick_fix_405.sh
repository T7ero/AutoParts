#!/bin/bash

echo "🚀 Быстрое исправление ошибки 405..."

# Пересобираем только frontend
echo "🔨 Пересобираем frontend..."
docker compose build --no-cache frontend

# Перезапускаем frontend
echo "🔄 Перезапускаем frontend..."
docker compose up -d frontend

echo "✅ Frontend пересобран!"
echo "🌐 Проверьте: http://87.228.101.164/upload" 