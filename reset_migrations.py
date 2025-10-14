#!/usr/bin/env python3
"""
Скрипт для сброса и пересоздания миграций Django
"""
import os
import subprocess
import sys

def run_command(cmd, cwd=None):
    """Выполнить команду и вернуть результат"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)

def main():
    print("Сброс и пересоздание миграций Django...")
    
    # Проверяем, что мы в правильной директории
    if not os.path.exists("backend"):
        print("Ошибка: директория backend не найдена")
        return 1
    
    # Удаляем все файлы миграций кроме __init__.py
    migrations_dir = "backend/core/migrations"
    if os.path.exists(migrations_dir):
        for file in os.listdir(migrations_dir):
            if file.endswith('.py') and file != '__init__.py':
                file_path = os.path.join(migrations_dir, file)
                os.remove(file_path)
                print(f"Удален файл миграции: {file}")
    
    # Создаем новую начальную миграцию
    print("Создание новой начальной миграции...")
    returncode, stdout, stderr = run_command("python manage.py makemigrations core --empty --name initial")
    
    if returncode != 0:
        print(f"Ошибка создания миграции: {stderr}")
        return 1
    
    # Применяем миграцию как фиктивную
    print("Применение миграции как фиктивной...")
    returncode, stdout, stderr = run_command("python manage.py migrate core --fake-initial")
    
    if returncode == 0:
        print("Миграции успешно сброшены и пересозданы")
        return 0
    else:
        print(f"Ошибка применения миграций: {stderr}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
