#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы исправленного Armtek парсера
"""

import sys
import os

# Добавляем путь к backend
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from api.autopiter_parser import get_brands_by_artikul_armtek, get_next_proxy

def test_armtek_parser():
    """Тестирует Armtek парсер на нескольких артикулах"""
    
    test_artikuls = [
        "1-88310-773-0",
        "1883107730", 
        "D-126177",
        "MD126177"
    ]
    
    print("Тестирование исправленного Armtek парсера...")
    print("=" * 50)
    
    # Получаем прокси для тестирования
    proxy_dict = get_next_proxy()
    proxy = None
    if proxy_dict:
        proxy = proxy_dict.get('http', '').replace('http://', '')
        print(f"Используем прокси: {proxy}")
    else:
        print("Прокси не найден, тестируем без прокси")
    
    print("-" * 30)
    
    for artikul in test_artikuls:
        print(f"\nТестируем артикул: {artikul}")
        print("-" * 30)
        
        try:
            brands = get_brands_by_artikul_armtek(artikul, proxy)
            if brands:
                print(f"✅ Найдено {len(brands)} брендов:")
                for i, brand in enumerate(brands, 1):
                    print(f"   {i}. {brand}")
            else:
                print("❌ Бренды не найдены")
        except Exception as e:
            print(f"❌ Ошибка: {str(e)}")
    
    print("\n" + "=" * 50)
    print("Тестирование завершено")

if __name__ == "__main__":
    test_armtek_parser()
