#!/usr/bin/env python3
"""
Скрипт для исправления проблемы с подключением к backend
"""
import os
import subprocess
import sys
import time

def run_command(cmd):
    """Выполнить команду и вернуть результат"""
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
    print("Исправление проблемы с подключением к backend...")
    
    # Команды для выполнения на сервере
    commands = [
        "cd ~/AutoParts",
        "docker compose stop backend celery",
        "docker compose exec backend python manage.py migrate core 0008 --fake",
        "docker compose exec backend python manage.py migrate core",
        "docker compose start backend celery",
        "sleep 10",
        "docker compose ps"
    ]
    
    for cmd in commands:
        if not run_command(cmd):
            print(f"Ошибка выполнения команды: {cmd}")
            return 1
    
    print("Исправление завершено успешно!")
    return 0

if __name__ == "__main__":
    exit(main())
