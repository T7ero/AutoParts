#!/bin/bash

echo "🚀 Быстрое исправление миграций..."

# Остановить контейнеры
sudo docker compose down

# Исправить зависимость в миграции 0014
if [ -f "backend/core/migrations/0014_add_missing_price_list_fields.py" ]; then
    echo "🔧 Исправление зависимости в 0014..."
    sed -i "s/('core', '0013_remove_pricelisttask_found_items_and_more')/('core', '0007_add_missing_fields')/g" backend/core/migrations/0014_add_missing_price_list_fields.py
    echo "✅ Исправлено"
fi

# Исправить другие миграции
for file in backend/core/migrations/00*.py; do
    if grep -q "0013_remove_pricelisttask_found_items_and_more" "$file"; then
        echo "🔧 Исправление в $(basename $file)..."
        sed -i "s/('core', '0013_remove_pricelisttask_found_items_and_more')/('core', '0007_add_missing_fields')/g" "$file"
    fi
done

# Запустить контейнеры
sudo docker compose up -d

echo "✅ Исправление завершено!"

