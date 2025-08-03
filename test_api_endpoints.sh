#!/bin/bash

echo "🧪 Тестирование API эндпоинтов..."

# Ждем готовности backend
echo "⏳ Ожидание готовности backend..."
sleep 30

# Тестируем эндпоинт создания задачи
echo "📝 Тестируем POST /api/parsing-tasks/create/"
curl -X POST http://localhost/api/parsing-tasks/create/ \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}' \
  -w "\nHTTP Status: %{http_code}\n" || echo "❌ Ошибка подключения"

# Тестируем эндпоинт списка задач
echo "📋 Тестируем GET /api/parsing-tasks/"
curl -X GET http://localhost/api/parsing-tasks/ \
  -w "\nHTTP Status: %{http_code}\n" || echo "❌ Ошибка подключения"

echo "✅ Тестирование завершено!" 