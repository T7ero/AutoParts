#!/usr/bin/env python3
"""
Финальный тестовый скрипт для проверки всех исправлений Armtek парсера
"""

import sys
import os

# Добавляем путь к backend
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from api.autopiter_parser import get_brands_by_artikul_armtek, get_next_proxy, make_request
import requests
from bs4 import BeautifulSoup

def test_armtek_final():
    """Тестирует все исправления Armtek парсера"""
    
    artikul = "D-126177"
    print(f"Финальное тестирование Armtek парсера для артикула: {artikul}")
    print("=" * 70)
    
    # Получаем прокси для тестирования
    proxy_dict = get_next_proxy()
    if not proxy_dict:
        print("❌ Прокси не найден")
        return
    
    proxy_url = proxy_dict.get('http', '')
    print(f"Исходный прокси: {proxy_url}")
    
    # Извлекаем прокси для тестирования
    if proxy_url.startswith('http://'):
        proxy_url = proxy_url[7:]
    
    print(f"Используем прокси: {proxy_url}")
    print("-" * 50)
    
    # Тест 1: Прямой HTTP запрос с прокси
    print("\n1. Тест HTTP запроса с прокси:")
    try:
        url = f"https://armtek.ru/search?text={artikul}"
        print(f"URL: {url}")
        
        response = make_request(url, proxy_url, max_retries=1)
        if response and response.status_code == 200:
            print(f"✅ HTTP статус: {response.status_code}")
            print(f"Размер ответа: {len(response.text)} символов")
            
            # Парсим HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем бренды по новым селекторам
            brands_found = set()
            
            # Основные селекторы для Armtek
            selectors = [
                '.font__body2.brand--selecting',  # Основной селектор
                '.brand--selecting',              # Альтернативный
                '.font__body2',                   # Общий
                '.brand-name', '.product-brand', '.manufacturer-name',
                '.vendor-title', '.item-brand', '.brand__name'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    brand = element.get_text(strip=True)
                    if brand and len(brand) > 2 and not brand.isdigit():
                        brands_found.add(brand)
                        print(f"  ✅ Найден бренд '{brand}' по селектору '{selector}'")
            
            print(f"\nНайдено брендов по селекторам: {len(brands_found)}")
            if brands_found:
                for brand in brands_found:
                    print(f"  - {brand}")
            
            # Поиск по атрибутам data-brand
            data_brand_elements = soup.find_all(attrs={"data-brand": True})
            print(f"\nЭлементов с data-brand: {len(data_brand_elements)}")
            for element in data_brand_elements:
                brand = element.get("data-brand", "").strip()
                if brand:
                    print(f"  - data-brand: {brand}")
            
            # Поиск по Angular атрибутам
            import re
            ng_brand_matches = re.findall(r'_ngcontent[^>]*class="[^"]*brand[^"]*"[^>]*>([^<]+)</', response.text)
            print(f"\nНайдено Angular брендов: {len(ng_brand_matches)}")
            for match in ng_brand_matches:
                if match and len(match.strip()) > 2:
                    print(f"  - Angular: {match.strip()}")
            
        else:
            print(f"❌ HTTP ошибка: {response.status_code if response else 'No response'}")
            
    except Exception as e:
        print(f"❌ Ошибка HTTP запроса: {str(e)}")
    
    # Тест 2: Полный Armtek парсер
    print("\n2. Тест полного Armtek парсера:")
    try:
        brands = get_brands_by_artikul_armtek(artikul, proxy_url)
        if brands:
            print(f"✅ Найдено {len(brands)} брендов:")
            for i, brand in enumerate(brands, 1):
                print(f"   {i}. {brand}")
        else:
            print("❌ Бренды не найдены")
    except Exception as e:
        print(f"❌ Ошибка парсера: {str(e)}")
    
    print("\n" + "=" * 70)
    print("Финальное тестирование завершено")

if __name__ == "__main__":
    test_armtek_final()
