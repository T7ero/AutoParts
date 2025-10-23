#!/bin/bash

echo "🚀 Быстрое исправление полей progress..."

# Запустить контейнеры
echo "▶️ Запуск контейнеров..."
sudo docker compose up -d

# Подождать запуска
echo "⏳ Ожидание запуска..."
sleep 15

# Исправить поля в базе данных
echo "🔧 Исправление полей в базе данных..."

# Исправить core_pricelisttask
echo "📋 Исправление core_pricelisttask..."
sudo docker compose exec db psql -U postgres -d autoparts -c "
ALTER TABLE core_pricelisttask DROP COLUMN IF EXISTS progress;
ALTER TABLE core_pricelisttask ALTER COLUMN found_items SET DEFAULT 0;
ALTER TABLE core_pricelisttask ALTER COLUMN not_found_items SET DEFAULT 0;
ALTER TABLE core_pricelisttask ALTER COLUMN log SET DEFAULT '';
UPDATE core_pricelisttask SET found_items = 0 WHERE found_items IS NULL;
UPDATE core_pricelisttask SET not_found_items = 0 WHERE not_found_items IS NULL;
UPDATE core_pricelisttask SET log = '' WHERE log IS NULL;
"

# Исправить core_parsingtask
echo "📋 Исправление core_parsingtask..."
sudo docker compose exec db psql -U postgres -d autoparts -c "
ALTER TABLE core_parsingtask DROP COLUMN IF EXISTS progress;
ALTER TABLE core_parsingtask ALTER COLUMN log SET DEFAULT '';
UPDATE core_parsingtask SET log = '' WHERE log IS NULL;
"

echo "✅ Исправление завершено!"
echo "Теперь попробуйте загрузить файлы в модули."
