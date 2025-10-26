#!/bin/bash

echo "🚀 Быстрое исправление истории миграций..."

# Остановить контейнеры
sudo docker compose down

# Запустить только БД
sudo docker compose up -d db

# Подождать
sleep 10

# Исправить историю миграций
echo "🔧 Исправление истории миграций..."
sudo docker compose exec db psql -U postgres -d autoparts -c "
DELETE FROM django_migrations WHERE app = 'core' AND name = '0005_parsingtask_sources';
DELETE FROM django_migrations WHERE app = 'core' AND name = '0006_fake_existing_tables';
INSERT INTO django_migrations (app, name, applied) VALUES 
('core', '0005_parsingtask_sources', NOW()),
('core', '0006_fake_existing_tables', NOW())
ON CONFLICT (app, name) DO NOTHING;
"

# Запустить все контейнеры
sudo docker compose up -d

echo "✅ Исправление завершено!"

