#!/bin/bash

echo "🔧 Переключение Dockerfile для исправления GPG проблем..."

# Проверяем аргументы
if [ "$1" = "alternative" ]; then
    echo "📦 Используем альтернативный Dockerfile (python:3.10-slim)"
    cp backend/Dockerfile.alternative backend/Dockerfile
    echo "✅ Переключено на альтернативный Dockerfile"
elif [ "$1" = "main" ]; then
    echo "📦 Используем основной Dockerfile (ubuntu:22.04)"
    cp backend/Dockerfile.backup backend/Dockerfile 2>/dev/null || echo "⚠️ Резервная копия не найдена"
    echo "✅ Переключено на основной Dockerfile"
else
    echo "❌ Неизвестный аргумент. Используйте:"
    echo "   ./switch_dockerfile.sh alternative  # Использовать python:3.10-slim"
    echo "   ./switch_dockerfile.sh main         # Использовать ubuntu:22.04"
    exit 1
fi

echo "🚀 Теперь можно пересобрать образ:"
echo "   docker compose build --no-cache backend"