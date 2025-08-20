#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений прокси
"""

import sys
import os

# Добавляем путь к backend
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from api.autopiter_parser import make_request, get_next_proxy

def test_proxy_fix():
    """Тестирует исправления прокси"""
    
    print("Тестирование исправлений прокси")
    print("=" * 50)
    
    # Получаем прокси для тестирования
    proxy_dict = get_next_proxy()
    if not proxy_dict:
        print("❌ Прокси не найден")
        return
    
    proxy_url = proxy_dict.get('http', '')
    print(f"Исходный прокси: {proxy_url}")
    
    # Извлекаем IP:port
    if proxy_url.startswith('http://'):
        proxy_url = proxy_url[7:]
    
    if '@' in proxy_url:
        auth_part, proxy_part = proxy_url.split('@', 1)
        print(f"Аутентификация: {auth_part}")
        print(f"IP:Port: {proxy_part}")
        
        if ':' in auth_part:
            username, password = auth_part.split(':', 1)
            print(f"Логин: {username}")
            print(f"Пароль: {password}")
    else:
        print(f"IP:Port: {proxy_url}")
    
    print("-" * 30)
    
    # Тест 1: Простой HTTP запрос
    print("\n1. Тест HTTP запроса:")
    try:
        url = "https://httpbin.org/ip"
        print(f"URL: {url}")
        
        response = make_request(url, proxy_part if '@' in proxy_url else proxy_url, max_retries=1)
        if response and response.status_code == 200:
            print(f"✅ HTTP статус: {response.status_code}")
            print(f"Ответ: {response.text[:200]}...")
        else:
            print(f"❌ HTTP ошибка: {response.status_code if response else 'No response'}")
            
    except Exception as e:
        print(f"❌ Ошибка HTTP запроса: {str(e)}")
    
    # Тест 2: Запрос к Armtek
    print("\n2. Тест запроса к Armtek:")
    try:
        url = "https://armtek.ru/search?text=D-126177"
        print(f"URL: {url}")
        
        response = make_request(url, proxy_part if '@' in proxy_url else proxy_url, max_retries=1)
        if response and response.status_code == 200:
            print(f"✅ HTTP статус: {response.status_code}")
            print(f"Размер ответа: {len(response.text)} символов")
            
            # Проверяем, что это действительно страница Armtek
            if 'armtek' in response.text.lower():
                print("✅ Получена страница Armtek")
            else:
                print("⚠️ Возможно, получена не страница Armtek")
                
        else:
            print(f"❌ HTTP ошибка: {response.status_code if response else 'No response'}")
            
    except Exception as e:
        print(f"❌ Ошибка HTTP запроса: {str(e)}")
    
    print("\n" + "=" * 50)
    print("Тестирование завершено")

if __name__ == "__main__":
    test_proxy_fix()
