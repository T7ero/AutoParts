#!/usr/bin/env python3
import os
import subprocess
import sys

def run_command(cmd):
    """Выполнить команду и вернуть результат"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)

def main():
    print("Исправление миграций на сервере...")
    
    # Удаляем проблемную миграцию 0006
    migration_0006 = "backend/core/migrations/0006_competitor_part_article_pricelisttask_progress_and_more.py"
    if os.path.exists(migration_0006):
        os.remove(migration_0006)
        print(f"Удалена проблемная миграция: {migration_0006}")
    
    # Создаем фиктивную миграцию 0006
    fake_migration = """# Generated manually to mark existing tables as migrated

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_parsingtask_sources'),
    ]

    operations = [
        # This is a fake migration to mark existing tables as migrated
        migrations.RunSQL(
            "SELECT 1;",  # No-op SQL
            reverse_sql="SELECT 1;"
        ),
    ]
"""
    
    with open("backend/core/migrations/0006_fake_existing_tables.py", "w") as f:
        f.write(fake_migration)
    print("Создана фиктивная миграция 0006")
    
    # Создаем миграцию для недостающих полей
    missing_fields_migration = """# Generated manually to add missing fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_fake_existing_tables'),
    ]

    operations = [
        # Add missing fields to existing models
        migrations.AddField(
            model_name='part',
            name='article',
            field=models.CharField(max_length=100, verbose_name='Артикул', blank=True, default=''),
        ),
        migrations.AddField(
            model_name='pricelisttask',
            name='progress',
            field=models.IntegerField(default=0, verbose_name='Прогресс (%)'),
        ),
    ]
"""
    
    with open("backend/core/migrations/0007_add_missing_fields.py", "w") as f:
        f.write(missing_fields_migration)
    print("Создана миграция для недостающих полей 0007")
    
    # Применяем миграции
    print("Применение миграций...")
    returncode, stdout, stderr = run_command("python manage.py migrate core --fake 0006")
    
    if returncode == 0:
        print("Фиктивная миграция 0006 применена")
    else:
        print(f"Ошибка применения фиктивной миграции: {stderr}")
        return 1
    
    # Применяем миграцию для недостающих полей
    returncode, stdout, stderr = run_command("python manage.py migrate core")
    
    if returncode == 0:
        print("Миграции успешно применены")
        return 0
    else:
        print(f"Ошибка применения миграций: {stderr}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
