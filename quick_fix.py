#!/usr/bin/env python3
"""
Быстрое исправление проблемы с миграциями
"""
import os
import subprocess

def run_command(cmd):
    """Выполнить команду"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"Команда: {cmd}")
        print(f"Код возврата: {result.returncode}")
        if result.stdout:
            print(f"Вывод: {result.stdout}")
        if result.stderr:
            print(f"Ошибки: {result.stderr}")
        return result.returncode == 0
    except Exception as e:
        print(f"Ошибка выполнения команды: {e}")
        return False

def main():
    print("Быстрое исправление миграций...")
    
    # Команды для выполнения на сервере
    commands = [
        "cd ~/AutoParts",
        "git pull",
        "rm -f backend/core/migrations/0006_competitor_part_article_pricelisttask_progress_and_more.py",
        "docker compose exec backend python manage.py migrate core 0005 --fake",
        "docker compose exec backend python manage.py makemigrations core",
        "docker compose exec backend python manage.py migrate core",
        "docker compose restart backend celery"
    ]
    
    for cmd in commands:
        if not run_command(cmd):
            print(f"Ошибка выполнения команды: {cmd}")
            return 1
    
    print("Исправление завершено успешно!")
    return 0

if __name__ == "__main__":
    exit(main())
