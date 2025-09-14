#!/bin/bash

echo "🔧 Исправление ошибки UnboundLocalError в tasks.py..."

# Перезапускаем только Celery для применения исправлений
echo "🔄 Перезапускаем Celery..."
docker-compose restart celery

# Ждем запуска
echo "⏳ Ждем запуска Celery..."
sleep 5

# Проверяем статус
echo "📊 Статус Celery:"
docker-compose ps celery

echo "✅ Исправление завершено!"
echo ""
echo "🎯 Проблема была в том, что функция 'log' вызывалась до её определения."
echo "📝 Теперь функция 'log' определена в правильном месте в коде."
echo ""
echo "🚀 Можете снова загружать файлы для парсинга!"
