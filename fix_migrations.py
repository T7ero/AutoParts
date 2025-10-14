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
    print("Исправление миграций Django...")
    
    # Проверяем, что мы в правильной директории
    if not os.path.exists("backend/core/migrations"):
        print("Ошибка: директория backend/core/migrations не найдена")
        return 1
    
    # Удаляем проблемную миграцию 0006 если она существует
    migration_0006 = "backend/core/migrations/0006_merge_0004_add_price_list_and_alter_user.py"
    if os.path.exists(migration_0006):
        os.remove(migration_0006)
        print(f"Удалена проблемная миграция: {migration_0006}")
    
    # Проверяем миграции
    print("Проверка миграций...")
    returncode, stdout, stderr = run_command("python manage.py makemigrations core --dry-run")
    
    if returncode == 0:
        print("Миграции в порядке")
        return 0
    else:
        print(f"Ошибка в миграциях: {stderr}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
