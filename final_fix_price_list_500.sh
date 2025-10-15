#!/bin/bash

echo "Финальное исправление ошибки 500 в API анализа прайс-листов..."

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

# Ждем запуска backend
echo "Ожидание запуска backend..."
sleep 10

# Проверяем логи backend
echo "Проверка логов backend..."
docker compose logs backend --tail=20

# Проверяем доступность API
echo "Проверка доступности API..."
curl -s -o /dev/null -w "%{http_code}" http://localhost/api/price-list-tasks/ || echo "API недоступен"

echo "Исправление завершено!"
