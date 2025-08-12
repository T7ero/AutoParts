#!/usr/bin/env python
"""
Скрипт для управления пользователями системы парсинга
Использование:
    python manage_users.py create <username> <email> <password>
    python manage_users.py list
    python manage_users.py delete <username>
    python manage_users.py change_password <username> <new_password>
"""

import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password

def create_user(username, email, password):
    """Создает нового пользователя"""
    try:
        if User.objects.filter(username=username).exists():
            print(f"Ошибка: Пользователь '{username}' уже существует")
            return False
        
        if User.objects.filter(email=email).exists():
            print(f"Ошибка: Email '{email}' уже используется")
            return False
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_staff=False,
            is_superuser=False
        )
        
        print(f"✅ Пользователь '{username}' успешно создан")
        print(f"   Email: {email}")
        print(f"   ID: {user.id}")
        return True
        
    except Exception as e:
        print(f"Ошибка при создании пользователя: {e}")
        return False

def list_users():
    """Выводит список всех пользователей"""
    users = User.objects.all().order_by('id')
    
    if not users:
        print("Пользователи не найдены")
        return
    
    print(f"{'ID':<5} {'Имя пользователя':<20} {'Email':<30} {'Дата регистрации':<20}")
    print("-" * 80)
    
    for user in users:
        print(f"{user.id:<5} {user.username:<20} {user.email:<30} {user.date_joined.strftime('%Y-%m-%d %H:%M'):<20}")

def delete_user(username):
    """Удаляет пользователя"""
    try:
        user = User.objects.get(username=username)
        user.delete()
        print(f"✅ Пользователь '{username}' успешно удален")
        return True
    except User.DoesNotExist:
        print(f"Ошибка: Пользователь '{username}' не найден")
        return False
    except Exception as e:
        print(f"Ошибка при удалении пользователя: {e}")
        return False

def change_password(username, new_password):
    """Изменяет пароль пользователя"""
    try:
        user = User.objects.get(username=username)
        user.password = make_password(new_password)
        user.save()
        print(f"✅ Пароль для пользователя '{username}' успешно изменен")
        return True
    except User.DoesNotExist:
        print(f"Ошибка: Пользователь '{username}' не найден")
        return False
    except Exception as e:
        print(f"Ошибка при изменении пароля: {e}")
        return False

def show_help():
    """Показывает справку по использованию"""
    print("""
Скрипт для управления пользователями системы парсинга

Использование:
    python manage_users.py create <username> <email> <password>
        Создает нового пользователя
    
    python manage_users.py list
        Показывает список всех пользователей
    
    python manage_users.py delete <username>
        Удаляет пользователя
    
    python manage_users.py change_password <username> <new_password>
        Изменяет пароль пользователя
    
    python manage_users.py help
        Показывает эту справку

Примеры:
    python manage_users.py create john john@example.com mypassword123
    python manage_users.py list
    python manage_users.py delete john
    python manage_users.py change_password john newpassword123
    """)

def main():
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'create':
        if len(sys.argv) != 5:
            print("Ошибка: Для создания пользователя нужно указать username, email и password")
            print("Пример: python manage_users.py create john john@example.com mypassword123")
            return
        create_user(sys.argv[2], sys.argv[3], sys.argv[4])
    
    elif command == 'list':
        list_users()
    
    elif command == 'delete':
        if len(sys.argv) != 3:
            print("Ошибка: Для удаления пользователя нужно указать username")
            print("Пример: python manage_users.py delete john")
            return
        delete_user(sys.argv[2])
    
    elif command == 'change_password':
        if len(sys.argv) != 4:
            print("Ошибка: Для изменения пароля нужно указать username и новый пароль")
            print("Пример: python manage_users.py change_password john newpassword123")
            return
        change_password(sys.argv[2], sys.argv[3])
    
    elif command == 'help':
        show_help()
    
    else:
        print(f"Неизвестная команда: {command}")
        show_help()

if __name__ == '__main__':
    main()
