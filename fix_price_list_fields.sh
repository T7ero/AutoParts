#!/bin/bash

echo "Исправление полей PriceListTask..."

# Применяем миграцию 0014
echo "Применение миграции 0014..."
docker compose exec backend python manage.py migrate core 0014 --fake

# Проверяем статус миграций
echo "Проверка статуса миграций..."
docker compose exec backend python manage.py showmigrations core

# Перезапускаем backend
echo "Перезапуск backend..."
docker compose restart backend

echo "Исправление завершено!"

