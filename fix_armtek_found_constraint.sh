#!/bin/bash

echo "Исправление ошибки NOT NULL constraint для поля armtek_found..."

# Проверяем статус контейнеров
echo "Проверка статуса контейнеров..."
docker compose ps

# Применяем миграцию 0016 для добавления полей platform_found
echo "Применение миграции 0016..."
docker compose exec backend python manage.py migrate core 0016

# Если миграция не применилась, пробуем с --fake
if [ $? -ne 0 ]; then
    echo "Пробуем применить миграцию с --fake..."
    docker compose exec backend python manage.py migrate core 0016 --fake
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
