#!/usr/bin/env python3
"""
Тестовый скрипт для проверки конкретного артикула D-126177 на Armtek
"""

import sys
import os

# Добавляем путь к backend
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from api.autopiter_parser import get_brands_by_artikul_armtek, get_next_proxy, make_request
import requests
from bs4 import BeautifulSoup

def test_armtek_d126177():
    """Тестирует Armtek парсер на конкретном артикуле D-126177"""
    
    artikul = "D-126177"
    print(f"Тестирование Armtek парсера для артикула: {artikul}")
    print("=" * 60)
    
    # Получаем прокси для тестирования
    proxy_dict = get_next_proxy()
    proxy = None
    if proxy_dict:
        proxy_url = proxy_dict.get('http', '')
        if proxy_url.startswith('http://'):
            proxy_url = proxy_url[7:]
        if '@' in proxy_url:
            proxy = proxy_url.split('@')[1]
        else:
            proxy = proxy_url
        print(f"Используем прокси: {proxy}")
    else:
        print("Прокси не найден, тестируем без прокси")
    
    print("-" * 40)
    
    # Тест 1: Прямой HTTP запрос
    print("\n1. Тест прямого HTTP запроса:")
    try:
        url = f"https://armtek.ru/search?text={artikul}"
        print(f"URL: {url}")
        
        response = make_request(url, proxy, max_retries=1)
        if response and response.status_code == 200:
            print(f"✅ HTTP статус: {response.status_code}")
            print(f"Размер ответа: {len(response.text)} символов")
            
            # Парсим HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем бренды
            brands_found = set()
            
            # Поиск по различным селекторам
            selectors = [
                '.brand-name', '.product-brand', '.manufacturer-name',
                '.vendor-title', '.item-brand', '.brand__name',
                '[data-brand]', '.brand--selecting'
            ]
            
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    brand = element.get_text(strip=True)
                    if brand and len(brand) > 2 and not brand.isdigit():
                        brands_found.add(brand)
            
            print(f"Найдено брендов по селекторам: {len(brands_found)}")
            if brands_found:
                for brand in brands_found:
                    print(f"  - {brand}")
            
            # Поиск по атрибутам data-brand
            data_brand_elements = soup.find_all(attrs={"data-brand": True})
            print(f"Элементов с data-brand: {len(data_brand_elements)}")
            for element in data_brand_elements:
                brand = element.get("data-brand", "").strip()
                if brand:
                    print(f"  - data-brand: {brand}")
            
            # Поиск по тексту страницы
            text_content = soup.get_text()
            import re
            words = re.findall(r'\b[A-Z][a-zA-Z0-9-]+\b', text_content)
            potential_brands = [word for word in words if len(word) > 2 and len(word) < 20 and not word.isdigit()]
            print(f"Потенциальных брендов в тексте: {len(potential_brands)}")
            if potential_brands[:10]:  # Показываем первые 10
                for brand in potential_brands[:10]:
                    print(f"  - {brand}")
            
        else:
            print(f"❌ HTTP ошибка: {response.status_code if response else 'No response'}")
            
    except Exception as e:
        print(f"❌ Ошибка HTTP запроса: {str(e)}")
    
    # Тест 2: Полный парсер
    print("\n2. Тест полного Armtek парсера:")
    try:
        brands = get_brands_by_artikul_armtek(artikul, proxy)
        if brands:
            print(f"✅ Найдено {len(brands)} брендов:")
            for i, brand in enumerate(brands, 1):
                print(f"   {i}. {brand}")
        else:
            print("❌ Бренды не найдены")
    except Exception as e:
        print(f"❌ Ошибка парсера: {str(e)}")
    
    print("\n" + "=" * 60)
    print("Тестирование завершено")

if __name__ == "__main__":
    test_armtek_d126177()
