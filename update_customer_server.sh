#!/bin/bash

echo "🔄 Обновление сервера заказчика..."

# 1. Остановить контейнеры
echo "⏹️ Остановка контейнеров..."
docker compose down

# 2. Обновить код из репозитория
echo "📥 Обновление кода..."
git pull origin main

# 3. Запустить только базу данных
echo "🗄️ Запуск базы данных..."
docker compose up -d db

# 4. Подождать готовности БД
echo "⏳ Ожидание готовности базы данных..."
sleep 10

# 5. Проверить структуру таблицы core_pricelisttask
echo "🔍 Проверка структуры таблицы core_pricelisttask..."
docker compose exec db psql -U postgres -d autoparts -c "\d core_pricelisttask" | grep -E "(progress|found_items|not_found_items|log)"

# 6. Если поле progress есть в таблице, удалить его
echo "🗑️ Удаление поля progress из core_pricelisttask..."
docker compose exec db psql -U postgres -d autoparts -c "ALTER TABLE core_pricelisttask DROP COLUMN IF EXISTS progress;"

# 7. Добавить недостающие поля если их нет
echo "➕ Добавление недостающих полей..."
docker compose exec db psql -U postgres -d autoparts -c "
ALTER TABLE core_pricelisttask ADD COLUMN IF NOT EXISTS found_items INTEGER DEFAULT 0 NOT NULL;
ALTER TABLE core_pricelisttask ADD COLUMN IF NOT EXISTS not_found_items INTEGER DEFAULT 0 NOT NULL;
ALTER TABLE core_pricelisttask ADD COLUMN IF NOT EXISTS log TEXT DEFAULT '' NOT NULL;
"

# 8. Запустить все контейнеры
echo "🚀 Запуск всех контейнеров..."
docker compose up -d

# 9. Подождать запуска
echo "⏳ Ожидание запуска сервисов..."
sleep 15

# 10. Проверить статус
echo "✅ Проверка статуса..."
docker compose ps

echo "🎉 Обновление завершено!"
echo "Теперь попробуйте загрузить файл в модуль 'Анализ прайс-листа'"
