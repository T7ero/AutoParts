#!/bin/bash

echo "🔧 Исправление истории миграций..."

# 1. Остановить контейнеры
echo "⏹️ Остановка контейнеров..."
sudo docker compose down

# 2. Запустить только базу данных
echo "🗄️ Запуск базы данных..."
sudo docker compose up -d db

# 3. Подождать готовности БД
echo "⏳ Ожидание готовности базы данных..."
sleep 10

# 4. Проверить текущие миграции в БД
echo "🔍 Текущие миграции в БД:"
sudo docker compose exec db psql -U postgres -d autoparts -c "SELECT * FROM django_migrations WHERE app = 'core' ORDER BY id;"

# 5. Удалить проблемные записи миграций
echo "🗑️ Удаление проблемных записей миграций..."
sudo docker compose exec db psql -U postgres -d autoparts -c "
DELETE FROM django_migrations WHERE app = 'core' AND name = '0005_parsingtask_sources';
DELETE FROM django_migrations WHERE app = 'core' AND name = '0006_fake_existing_tables';
"

# 6. Добавить правильные записи миграций
echo "➕ Добавление правильных записей миграций..."
sudo docker compose exec db psql -U postgres -d autoparts -c "
INSERT INTO django_migrations (app, name, applied) VALUES 
('core', '0005_parsingtask_sources', NOW()),
('core', '0006_fake_existing_tables', NOW())
ON CONFLICT (app, name) DO NOTHING;
"

# 7. Проверить результат
echo "✅ Проверка результата:"
sudo docker compose exec db psql -U postgres -d autoparts -c "SELECT * FROM django_migrations WHERE app = 'core' ORDER BY id;"

# 8. Запустить все контейнеры
echo "🚀 Запуск всех контейнеров..."
sudo docker compose up -d

# 9. Подождать запуска
echo "⏳ Ожидание запуска сервисов..."
sleep 15

# 10. Проверить статус
echo "✅ Проверка статуса..."
sudo docker compose ps

echo "🎉 Исправление завершено!"

