#!/usr/bin/env python
"""
Простой скрипт для создания пользователя
Использование: python create_user.py
"""

import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User

def create_user():
    print("=== Создание нового пользователя ===")
    
    # Запрос данных пользователя
    username = input("Введите имя пользователя: ").strip()
    if not username:
        print("❌ Имя пользователя не может быть пустым")
        return
    
    email = input("Введите email: ").strip()
    if not email:
        print("❌ Email не может быть пустым")
        return
    
    password = input("Введите пароль: ").strip()
    if not password:
        print("❌ Пароль не может быть пустым")
        return
    
    confirm_password = input("Подтвердите пароль: ").strip()
    if password != confirm_password:
        print("❌ Пароли не совпадают")
        return
    
    # Проверка существования пользователя
    if User.objects.filter(username=username).exists():
        print(f"❌ Пользователь '{username}' уже существует")
        return
    
    if User.objects.filter(email=email).exists():
        print(f"❌ Email '{email}' уже используется")
        return
    
    try:
        # Создание пользователя
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_staff=False,
            is_superuser=False
        )
        
        print(f"\n✅ Пользователь успешно создан!")
        print(f"   Имя пользователя: {username}")
        print(f"   Email: {email}")
        print(f"   ID: {user.id}")
        print(f"\nТеперь вы можете войти в систему с этими учетными данными.")
        
    except Exception as e:
        print(f"❌ Ошибка при создании пользователя: {e}")

if __name__ == '__main__':
    try:
        create_user()
    except KeyboardInterrupt:
        print("\n\n❌ Операция отменена пользователем")
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
