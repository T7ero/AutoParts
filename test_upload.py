#!/usr/bin/env python3
"""
Тестовый скрипт для проверки загрузки файлов в API
"""

import requests
import pandas as pd
import tempfile
import os

def create_test_file():
    """Создает тестовый Excel файл"""
    data = {
        'Бренд № 1': ['Toyota', 'Honda', 'Nissan'],
        'Артикул по Бренду № 1': ['12345', '67890', '11111'],
        'Наименование': ['Фильтр масляный', 'Тормозные колодки', 'Свечи зажигания']
    }
    
    df = pd.DataFrame(data)
    
    # Создаем временный файл
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
        df.to_excel(tmp.name, index=False)
        return tmp.name

def test_upload():
    """Тестирует загрузку файла"""
    # URL API
    base_url = "http://localhost"
    token_url = f"{base_url}/api/auth/token/"
    upload_url = f"{base_url}/api/parsing-tasks/"
    
    # Данные для авторизации
    auth_data = {
        'username': 'admin',
        'password': 'admin'
    }
    
    try:
        # Получаем токен
        print("🔐 Получаем токен авторизации...")
        response = requests.post(token_url, data=auth_data)
        
        if response.status_code != 200:
            print(f"❌ Ошибка авторизации: {response.status_code}")
            print(f"Ответ: {response.text}")
            return
        
        token = response.json()['token']
        print(f"✅ Токен получен: {token[:10]}...")
        
        # Создаем тестовый файл
        print("📄 Создаем тестовый файл...")
        test_file_path = create_test_file()
        
        # Загружаем файл
        print("📤 Загружаем файл...")
        headers = {
            'Authorization': f'Token {token}'
        }
        
        with open(test_file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(upload_url, headers=headers, files=files)
        
        # Удаляем временный файл
        os.unlink(test_file_path)
        
        print(f"📊 Статус ответа: {response.status_code}")
        print(f"📋 Ответ: {response.text}")
        
        if response.status_code == 201:
            print("✅ Файл успешно загружен!")
            task_data = response.json()
            print(f"🆔 ID задачи: {task_data.get('id')}")
            print(f"📊 Статус: {task_data.get('status')}")
        else:
            print("❌ Ошибка при загрузке файла")
            
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")

if __name__ == "__main__":
    test_upload() 