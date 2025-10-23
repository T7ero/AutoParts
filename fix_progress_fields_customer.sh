#!/bin/bash

echo "🔧 Исправление полей progress на сервере заказчика..."

# 1. Остановить контейнеры
echo "⏹️ Остановка контейнеров..."
docker compose down

# 2. Запустить только базу данных
echo "🗄️ Запуск базы данных..."
docker compose up -d db

# 3. Подождать готовности БД
echo "⏳ Ожидание готовности базы данных..."
sleep 10

# 4. Исправить поле progress в core_pricelisttask
echo "🔧 Исправление поля progress в core_pricelisttask..."
docker compose exec db psql -U postgres -d autoparts -c "
-- Удалить поле progress если оно есть
ALTER TABLE core_pricelisttask DROP COLUMN IF EXISTS progress;

-- Убедиться что все нужные поля есть с правильными значениями по умолчанию
ALTER TABLE core_pricelisttask ALTER COLUMN found_items SET DEFAULT 0;
ALTER TABLE core_pricelisttask ALTER COLUMN not_found_items SET DEFAULT 0;
ALTER TABLE core_pricelisttask ALTER COLUMN log SET DEFAULT '';

-- Обновить существующие записи
UPDATE core_pricelisttask SET found_items = 0 WHERE found_items IS NULL;
UPDATE core_pricelisttask SET not_found_items = 0 WHERE not_found_items IS NULL;
UPDATE core_pricelisttask SET log = '' WHERE log IS NULL;
"

# 5. Исправить поле progress в core_parsingtask
echo "🔧 Исправление поля progress в core_parsingtask..."
docker compose exec db psql -U postgres -d autoparts -c "
-- Удалить поле progress если оно есть
ALTER TABLE core_parsingtask DROP COLUMN IF EXISTS progress;

-- Убедиться что поле log имеет правильное значение по умолчанию
ALTER TABLE core_parsingtask ALTER COLUMN log SET DEFAULT '';

-- Обновить существующие записи
UPDATE core_parsingtask SET log = '' WHERE log IS NULL;
"

# 6. Проверить структуру таблиц
echo "🔍 Проверка структуры таблиц..."
echo "=== core_pricelisttask ==="
docker compose exec db psql -U postgres -d autoparts -c "\d core_pricelisttask" | grep -E "(progress|found_items|not_found_items|log)"

echo "=== core_parsingtask ==="
docker compose exec db psql -U postgres -d autoparts -c "\d core_parsingtask" | grep -E "(progress|log)"

# 7. Запустить все контейнеры
echo "🚀 Запуск всех контейнеров..."
docker compose up -d

# 8. Подождать запуска
echo "⏳ Ожидание запуска сервисов..."
sleep 15

# 9. Проверить статус
echo "✅ Проверка статуса..."
docker compose ps

echo "🎉 Исправление завершено!"
echo "Теперь попробуйте загрузить файлы в оба модуля:"
echo "- Модуль 'Анализ прайс-листа'"
echo "- Модуль 'Парсинг брендов'"
