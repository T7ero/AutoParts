#!/bin/bash

echo "Применяем миграцию для добавления полей количества товара..."

cd backend

# Применяем миграцию
python manage.py migrate core 0019_add_quantity_fields

echo "Миграция применена успешно!"
echo "Теперь поля quantity_in_stock и competitor_quantity будут сохраняться в Excel файл."
