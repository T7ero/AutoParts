#!/bin/bash

echo "🔍 Диагностика сервера заказчика..."

# 1. Проверить статус контейнеров
echo "📊 Статус контейнеров:"
docker compose ps

# 2. Проверить структуру таблицы core_pricelisttask
echo "🗄️ Структура таблицы core_pricelisttask:"
docker compose exec db psql -U postgres -d autoparts -c "\d core_pricelisttask"

# 3. Проверить структуру таблицы core_parsingtask
echo "🗄️ Структура таблицы core_parsingtask:"
docker compose exec db psql -U postgres -d autoparts -c "\d core_parsingtask"

# 4. Проверить миграции
echo "📋 Статус миграций:"
docker compose exec backend python manage.py showmigrations core | tail -10

# 5. Проверить последние ошибки в логах
echo "🚨 Последние ошибки в логах backend:"
docker compose logs backend --tail=20 | grep -E "(ERROR|Exception|Traceback)" || echo "✅ Нет ошибок"

# 6. Проверить код на наличие поля progress
echo "🔍 Проверка кода на наличие поля progress:"
docker compose exec backend grep -n "progress" /app/api/views.py || echo "✅ Поле progress удалено из views.py"
docker compose exec backend grep -n "task.progress" /app/api/tasks.py || echo "✅ Все ссылки на task.progress удалены из tasks.py"

echo "✅ Диагностика завершена!"
