#!/usr/bin/env python3
"""
Скрипт для исправления несоответствия схемы базы данных
"""
import os
import django
from django.conf import settings
from django.core.management import execute_from_command_line

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.db import connection

def main():
    print("Исправление схемы базы данных...")
    
    with connection.cursor() as cursor:
        # Проверяем, какие таблицы существуют
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'core_%'
            ORDER BY table_name;
        """)
        
        existing_tables = [row[0] for row in cursor.fetchall()]
        print(f"Существующие таблицы core: {existing_tables}")
        
        # Проверяем, какие миграции применены
        cursor.execute("""
            SELECT name 
            FROM django_migrations 
            WHERE app = 'core'
            ORDER BY name;
        """)
        
        applied_migrations = [row[0] for row in cursor.fetchall()]
        print(f"Применённые миграции core: {applied_migrations}")
        
        # Если таблицы существуют, но миграции не применены, отмечаем их как применённые
        if 'core_competitor' in existing_tables and '0006_competitor_part_article_pricelisttask_progress_and_more' not in applied_migrations:
            print("Отмечаем существующие таблицы как применённые...")
            
            # Добавляем запись о фиктивной миграции
            cursor.execute("""
                INSERT INTO django_migrations (app, name, applied)
                VALUES ('core', '0006_fake_existing_tables', NOW())
                ON CONFLICT (app, name) DO NOTHING;
            """)
            
            print("Фиктивная миграция добавлена в django_migrations")
        
        # Проверяем, есть ли недостающие поля
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'core_parsingtask' 
            AND column_name = 'progress';
        """)
        
        if not cursor.fetchone():
            print("Добавляем недостающее поле progress в core_parsingtask...")
            cursor.execute("""
                ALTER TABLE core_parsingtask 
                ADD COLUMN progress integer DEFAULT 0;
            """)
            print("Поле progress добавлено")
        
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'core_part' 
            AND column_name = 'article';
        """)
        
        if not cursor.fetchone():
            print("Добавляем недостающее поле article в core_part...")
            cursor.execute("""
                ALTER TABLE core_part 
                ADD COLUMN article varchar(100) DEFAULT '';
            """)
            print("Поле article добавлено")
        
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'core_pricelisttask' 
            AND column_name = 'progress';
        """)
        
        if not cursor.fetchone():
            print("Добавляем недостающее поле progress в core_pricelisttask...")
            cursor.execute("""
                ALTER TABLE core_pricelisttask 
                ADD COLUMN progress integer DEFAULT 0;
            """)
            print("Поле progress добавлено")
    
    print("Схема базы данных исправлена!")
    return 0

if __name__ == "__main__":
    main()
