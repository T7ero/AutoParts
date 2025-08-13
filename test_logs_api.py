#!/usr/bin/env python3
"""
Тест API для получения логов задач
"""

import requests
import json

# Настройки
BASE_URL = "http://localhost:8000"
API_TOKEN = "your_token_here"  # Замените на реальный токен

def test_task_logs():
    """Тестирует получение логов задачи"""
    
    # 1. Получаем список задач
    print("1. Получение списка задач...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/parsing-tasks/",
            headers={'Authorization': f'Token {API_TOKEN}'}
        )
        
        if response.status_code == 200:
            tasks = response.json()
            print(f"✅ Найдено задач: {len(tasks)}")
            
            if tasks:
                # Берем первую задачу для тестирования
                first_task = tasks[0]
                task_id = first_task['id']
                print(f"Тестируем задачу #{task_id}")
                
                # 2. Получаем логи для этой задачи
                print(f"\n2. Получение логов для задачи #{task_id}...")
                logs_response = requests.get(
                    f"{BASE_URL}/api/parsing-tasks/{task_id}/logs/",
                    headers={'Authorization': f'Token {API_TOKEN}'}
                )
                
                if logs_response.status_code == 200:
                    logs_data = logs_response.json()
                    print("✅ Логи получены успешно!")
                    print(f"Статус задачи: {logs_data['status']}")
                    print(f"Прогресс: {logs_data['progress']}%")
                    print(f"Количество записей логов: {len(logs_data['logs'])}")
                    
                    # Показываем первые несколько логов
                    print("\nПервые логи:")
                    for i, log in enumerate(logs_data['logs'][:5]):
                        print(f"  {i+1}. [{log['timestamp']}] {log['message']}")
                        
                else:
                    print(f"❌ Ошибка получения логов: {logs_response.status_code}")
                    print(logs_response.text)
            else:
                print("⚠️ Нет задач для тестирования")
                
        else:
            print(f"❌ Ошибка получения задач: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("❌ Не удается подключиться к серверу. Убедитесь, что Django запущен на порту 8000")
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")

def test_without_auth():
    """Тестирует API без аутентификации"""
    print("\n3. Тест без аутентификации...")
    
    try:
        response = requests.get(f"{BASE_URL}/api/parsing-tasks/1/logs/")
        if response.status_code == 401:
            print("✅ Правильно требует аутентификацию")
        else:
            print(f"⚠️ Неожиданный статус: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")

if __name__ == "__main__":
    print("🧪 Тестирование API логов задач")
    print("=" * 50)
    
    test_task_logs()
    test_without_auth()
    
    print("\n" + "=" * 50)
    print("Тестирование завершено!")
    
    print("\n📝 Инструкции по использованию:")
    print("1. Убедитесь, что Django сервер запущен: python manage.py runserver")
    print("2. Получите токен аутентификации через /api/auth/token/")
    print("3. Обновите API_TOKEN в этом файле")
    print("4. Запустите тест снова: python test_logs_api.py")
