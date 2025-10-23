#!/bin/bash

echo "🔍 Проверка полей progress на сервере..."

# Проверить структуру таблицы core_pricelisttask
echo "=== Структура core_pricelisttask ==="
sudo docker compose exec db psql -U postgres -d autoparts -c "\d core_pricelisttask" | grep -E "(progress|found_items|not_found_items|log)"

echo ""
echo "=== Структура core_parsingtask ==="
sudo docker compose exec db psql -U postgres -d autoparts -c "\d core_parsingtask" | grep -E "(progress|log)"

echo ""
echo "=== Последние ошибки в логах ==="
sudo docker compose logs db --tail=10 | grep -E "(ERROR|progress)" || echo "✅ Нет ошибок с progress"

echo ""
echo "=== Статус контейнеров ==="
sudo docker compose ps
