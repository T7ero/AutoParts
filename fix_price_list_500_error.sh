#!/bin/bash

echo "Исправление ошибки 500 в API анализа прайс-листов..."

# Проверяем статус контейнеров
echo "Проверка статуса контейнеров..."
docker compose ps

# Применяем миграцию 0014 для добавления недостающих полей
echo "Применение миграции 0014..."
docker compose exec backend python manage.py migrate core 0014

# Если миграция не применилась, пробуем с --fake
if [ $? -ne 0 ]; then
    echo "Пробуем применить миграцию с --fake..."
    docker compose exec backend python manage.py migrate core 0014 --fake
fi

# Проверяем статус миграций
echo "Проверка статуса миграций..."
docker compose exec backend python manage.py showmigrations core

# Перезапускаем backend
echo "Перезапуск backend..."
docker compose restart backend

# Проверяем логи backend
echo "Проверка логов backend..."
docker compose logs backend --tail=20

echo "Исправление завершено!"
