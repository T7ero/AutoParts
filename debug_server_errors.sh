#!/bin/bash

echo "=== Диагностика ошибок на сервере ==="

echo "1. Проверяем логи backend с деталями ошибок..."
sudo docker compose logs backend --tail=50 | grep -A 5 -B 5 "ERROR\|Exception\|Traceback"

echo ""
echo "2. Проверяем логи celery..."
sudo docker compose logs celery --tail=20

echo ""
echo "3. Проверяем статус контейнеров..."
sudo docker compose ps

echo ""
echo "4. Проверяем структуру таблицы core_pricelisttask..."
sudo docker compose exec db psql -U postgres -d autoparts -c "\d core_pricelisttask"

echo ""
echo "5. Проверяем структуру таблицы core_parsingtask..."
sudo docker compose exec db psql -U postgres -d autoparts -c "\d core_parsingtask"

echo ""
echo "6. Проверяем последние записи в core_pricelisttask..."
sudo docker compose exec db psql -U postgres -d autoparts -c "SELECT id, status, found_items, not_found_items, log FROM core_pricelisttask ORDER BY id DESC LIMIT 5;"

echo ""
echo "7. Проверяем последние записи в core_parsingtask..."
sudo docker compose exec db psql -U postgres -d autoparts -c "SELECT id, status, progress FROM core_parsingtask ORDER BY id DESC LIMIT 5;"
