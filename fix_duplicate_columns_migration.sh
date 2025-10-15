#!/bin/bash

echo "Исправление ошибки дублирования колонок в миграции 0016..."

# Проверяем статус контейнеров
echo "Проверка статуса контейнеров..."
docker compose ps

# Применяем миграцию 0016 с --fake, так как поля уже существуют
echo "Применение миграции 0016 с --fake..."
docker compose exec backend python manage.py migrate core 0016 --fake

# Проверяем статус миграций
echo "Проверка статуса миграций..."
docker compose exec backend python manage.py showmigrations core

# Перезапускаем backend и celery
echo "Перезапуск backend и celery..."
docker compose restart backend celery

# Ждем запуска сервисов
echo "Ожидание запуска сервисов..."
sleep 15

# Проверяем логи backend
echo "Проверка логов backend..."
docker compose logs backend --tail=20

# Проверяем логи celery
echo "Проверка логов celery..."
docker compose logs celery --tail=20

echo "Исправление завершено!"
