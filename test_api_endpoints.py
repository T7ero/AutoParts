#!/usr/bin/env python3
"""
Тест API endpoints для проверки работы
"""

import requests
import json

# Настройки
BASE_URL = "http://87.228.101.164"  # Ваш IP адрес
API_TOKEN = "your_token_here"  # Замените на реальный токен

def test_api_endpoints():
    """Тестирует основные API endpoints"""
    
    print("🧪 Тестирование API endpoints")
    print("=" * 50)
    
    # 1. Тестовый endpoint
    print("1. Тестирование /api/test/...")
    try:
        response = requests.get(f"{BASE_URL}/api/test/")
        if response.status_code == 200:
            print("✅ /api/test/ работает")
            print(f"Ответ: {response.json()}")
        else:
            print(f"❌ /api/test/ не работает: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Ошибка при тестировании /api/test/: {str(e)}")
    
    print()
    
    # 2. Список задач
    print("2. Тестирование /api/parsing-tasks/...")
    try:
        response = requests.get(f"{BASE_URL}/api/parsing-tasks/")
        if response.status_code == 200:
            print("✅ /api/parsing-tasks/ работает")
            tasks = response.json()
            print(f"Найдено задач: {len(tasks)}")
            
            # Ищем завершенную задачу
            completed_task = None
            for task in tasks:
                if task.get('status') == 'completed' and task.get('result_files'):
                    completed_task = task
                    break
            
            if completed_task:
                print(f"Найдена завершенная задача: #{completed_task['id']}")
                print(f"Result files: {completed_task['result_files']}")
                
                # 3. Тестируем скачивание по сайтам
                print("\n3. Тестирование скачивания по сайтам...")
                for site in completed_task['result_files'].keys():
                    print(f"Тестируем {site}...")
                    try:
                        download_url = f"{BASE_URL}/api/parsing-tasks/{completed_task['id']}/download-site/{site}/"
                        print(f"URL: {download_url}")
                        
                        response = requests.get(download_url)
                        print(f"Статус: {response.status_code}")
                        
                        if response.status_code == 200:
                            print(f"✅ Скачивание {site} работает")
                        elif response.status_code == 404:
                            print(f"❌ 404 для {site}")
                        else:
                            print(f"⚠️ Неожиданный статус {response.status_code} для {site}")
                            print(f"Ответ: {response.text}")
                    except Exception as e:
                        print(f"❌ Ошибка при тестировании {site}: {str(e)}")
            else:
                print("⚠️ Нет завершенных задач с result_files для тестирования")
        else:
            print(f"❌ /api/parsing-tasks/ не работает: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Ошибка при тестировании /api/parsing-tasks/: {str(e)}")
    
    print("\n" + "=" * 50)
    print("Тестирование завершено!")

if __name__ == "__main__":
    test_api_endpoints()
