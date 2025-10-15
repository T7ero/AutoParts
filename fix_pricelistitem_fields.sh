#!/bin/bash

echo "Исправление отсутствующих полей в таблице core_pricelistitem..."

# Проверяем статус контейнеров
echo "Проверка статуса контейнеров..."
docker compose ps

# Применяем миграцию 0015 для добавления недостающих полей в PriceListItem
echo "Применение миграции 0015..."
docker compose exec backend python manage.py migrate core 0015

# Если миграция не применилась, пробуем с --fake
if [ $? -ne 0 ]; then
    echo "Пробуем применить миграцию с --fake..."
    docker compose exec backend python manage.py migrate core 0015 --fake
fi

# Проверяем статус миграций
echo "Проверка статуса миграций..."
docker compose exec backend python manage.py showmigrations core

# Перезапускаем backend и celery
echo "Перезапуск backend и celery..."
docker compose restart backend celery

# Ждем запуска сервисов
echo "Ожидание запуска сервисов..."
sleep 10

# Проверяем логи backend
echo "Проверка логов backend..."
docker compose logs backend --tail=20

# Проверяем логи celery
echo "Проверка логов celery..."
docker compose logs celery --tail=20

echo "Исправление завершено!"
