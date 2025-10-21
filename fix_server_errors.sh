#!/bin/bash

echo "=== Исправление ошибок на сервере заказчика ==="

# 1. Обновляем код
echo "1. Обновляем код..."
git pull

# 2. Перезапускаем сервисы
echo "2. Перезапускаем сервисы..."
sudo docker compose restart backend celery

# 3. Проверяем логи
echo "3. Проверяем логи backend..."
sudo docker compose logs backend --tail=20

echo "4. Проверяем статус контейнеров..."
sudo docker compose ps

echo "=== Готово! Теперь попробуйте загрузить файлы в модули ==="
