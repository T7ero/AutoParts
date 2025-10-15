#!/bin/bash

echo "Быстрое исправление миграции 0016..."

# Останавливаем контейнеры
echo "Остановка контейнеров..."
docker compose down

# Запускаем только базу данных
echo "Запуск базы данных..."
docker compose up -d db

# Ждем запуска базы данных
echo "Ожидание запуска базы данных..."
sleep 10

# Запускаем backend и celery
echo "Запуск backend и celery..."
docker compose up -d backend celery

# Ждем запуска сервисов
echo "Ожидание запуска сервисов..."
sleep 15

# Применяем миграцию с --fake
echo "Применение миграции 0016 с --fake..."
docker compose exec backend python manage.py migrate core 0016 --fake

# Проверяем статус миграций
echo "Проверка статуса миграций..."
docker compose exec backend python manage.py showmigrations core

# Запускаем все сервисы
echo "Запуск всех сервисов..."
docker compose up -d

echo "Исправление завершено!"
