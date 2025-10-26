#!/bin/bash

echo "🔧 Исправление зависимостей миграций..."

# 1. Остановить контейнеры
echo "⏹️ Остановка контейнеров..."
sudo docker compose down

# 2. Проверить какие миграции существуют
echo "🔍 Проверка существующих миграций..."
ls -la backend/core/migrations/ | grep -E "00[0-9][0-9]_"

# 3. Исправить зависимость в миграции 0014
echo "🔧 Исправление зависимости в миграции 0014..."
if [ -f "backend/core/migrations/0014_add_missing_price_list_fields.py" ]; then
    # Заменить зависимость с 0013 на 0007 (последняя существующая)
    sed -i "s/('core', '0013_remove_pricelisttask_found_items_and_more')/('core', '0007_add_missing_fields')/g" backend/core/migrations/0014_add_missing_price_list_fields.py
    echo "✅ Зависимость в 0014 исправлена"
else
    echo "❌ Файл 0014_add_missing_price_list_fields.py не найден"
fi

# 4. Проверить другие миграции на неправильные зависимости
echo "🔍 Проверка других миграций..."
for file in backend/core/migrations/00*.py; do
    if grep -q "0013_remove_pricelisttask_found_items_and_more" "$file"; then
        echo "🔧 Исправление зависимости в $(basename $file)..."
        sed -i "s/('core', '0013_remove_pricelisttask_found_items_and_more')/('core', '0007_add_missing_fields')/g" "$file"
    fi
done

# 5. Запустить только базу данных
echo "🗄️ Запуск базы данных..."
sudo docker compose up -d db

# 6. Подождать готовности БД
echo "⏳ Ожидание готовности базы данных..."
sleep 10

# 7. Проверить миграции
echo "📋 Проверка миграций..."
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

