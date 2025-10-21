#!/bin/bash

echo "=== Исправление ошибок на сервере заказчика ==="

# 1. Обновляем код
echo "1. Обновляем код..."
git pull

# 2. Применяем миграции
echo "2. Применяем миграции..."
sudo docker compose exec backend python manage.py migrate core

# 3. Перезапускаем сервисы
echo "3. Перезапускаем сервисы..."
sudo docker compose restart backend celery

# 4. Проверяем логи
echo "4. Проверяем логи backend..."
sudo docker compose logs backend --tail=20

echo "5. Проверяем статус контейнеров..."
sudo docker compose ps

echo "=== Готово! Теперь попробуйте загрузить файлы в модули ==="
