import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import logging
import subprocess
import os
import shutil
import tempfile
import uuid
import random
from typing import List, Dict, Optional, Tuple, Set
from selenium.common.exceptions import TimeoutException
import gc
from decimal import Decimal
from .autopiter_parser import get_next_proxy, make_request

# Настройки для парсинга прайс-листа
TIMEOUT = 10
SELENIUM_TIMEOUT = 15
PAGE_LOAD_TIMEOUT = 15

# Коды поставщиков для каждой площадки
SUPPLIER_CODES = {
    'autopiter': ['30399', '36364', '32994', '22771', '33305', '40251', '39479', '40112'],
    'emex': ['QFRD', 'QFRG'],
    'armtek': []  # Нет кода поставщика
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

def log_debug(message):
    print(f"[DEBUG] {message}")

def parse_price_list_file(file_path: str) -> List[Dict]:
    """Парсит Excel файл прайс-листа и возвращает список позиций"""
    try:
        # Читаем Excel файл
        df = pd.read_excel(file_path)
        
        # Определяем колонки по заголовкам
        columns = df.columns.tolist()
        
        # Ищем нужные колонки
        supplier_col = None
        manufacturer_col = None
        article_col = None
        nomenclature_col = None
        quantity_col = None
        price_col = None
        
        for col in columns:
            col_lower = str(col).lower()
            if 'код поставщика' in col_lower or 'поставщик' in col_lower:
                supplier_col = col
            elif 'производитель' in col_lower or 'бренд' in col_lower:
                manufacturer_col = col
            elif 'артикул' in col_lower:
                article_col = col
            elif 'номенклатура' in col_lower or 'наименование' in col_lower:
                nomenclature_col = col
            elif 'количество' in col_lower or 'в наличии' in col_lower:
                quantity_col = col
            elif 'цена' in col_lower or 'оптовые' in col_lower:
                price_col = col
        
        if not manufacturer_col or not article_col:
            raise ValueError("Не найдены обязательные колонки: Производитель и Артикул")
        
        items = []
        for index, row in df.iterrows():
            try:
                item = {
                    'supplier_code': str(row[supplier_col]) if supplier_col and pd.notna(row[supplier_col]) else '',
                    'manufacturer': str(row[manufacturer_col]).strip() if pd.notna(row[manufacturer_col]) else '',
                    'article': str(row[article_col]).strip() if pd.notna(row[article_col]) else '',
                    'nomenclature': str(row[nomenclature_col]) if nomenclature_col and pd.notna(row[nomenclature_col]) else '',
                    'quantity': int(row[quantity_col]) if quantity_col and pd.notna(row[quantity_col]) else 0,
                    'our_price': float(row[price_col]) if price_col and pd.notna(row[price_col]) else None,
                }
                
                # Проверяем обязательные поля
                if item['manufacturer'] and item['article']:
                    items.append(item)
                    
            except Exception as e:
                log_debug(f"Ошибка парсинга строки {index + 1}: {str(e)}")
                continue
        
        log_debug(f"Парсинг завершен. Найдено {len(items)} позиций")
        return items
        
    except Exception as e:
        log_debug(f"Ошибка парсинга файла: {str(e)}")
        return []

def check_autopiter_item(supplier_code: str, manufacturer: str, article: str, competitor_brand_filter: str = None) -> Dict:
    """Проверяет наличие позиции на АвтоПитере и анализирует цены"""
    result = {
        'is_found': False,
        'marketplace_price': None,
        'min_competitor_price': None,
        'competitor_brand': None,
        'error_message': ''
    }
    
    try:
        # Формируем поисковый запрос
        search_query = f"{manufacturer} {article}"
        if supplier_code and supplier_code in SUPPLIER_CODES['autopiter']:
            search_query = f"{supplier_code} {search_query}"
        
        url = f"https://autopiter.ru/search?q={quote(search_query)}"
        
        # Делаем запрос
        response = make_request(url, timeout=TIMEOUT)
        if not response:
            result['error_message'] = "Ошибка запроса к АвтоПитер"
            return result
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем наши товары
        our_items = []
        competitor_items = []
        
        # Парсим результаты поиска
        items = soup.find_all('div', class_='search-item') or soup.find_all('div', class_='product-item')
        
        for item in items:
            try:
                # Извлекаем информацию о товаре
                title_elem = item.find('h3') or item.find('a', class_='title') or item.find('div', class_='title')
                price_elem = item.find('span', class_='price') or item.find('div', class_='price')
                supplier_elem = item.find('span', class_='supplier') or item.find('div', class_='supplier')
                
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                price_text = price_elem.get_text(strip=True) if price_elem else ''
                supplier_text = supplier_elem.get_text(strip=True) if supplier_elem else ''
                
                # Извлекаем цену
                price_match = re.search(r'(\d+(?:\s*\d+)*)', price_text.replace(' ', ''))
                price = float(price_match.group(1).replace(' ', '')) if price_match else None
                
                # Проверяем, наш ли это товар
                is_our_item = False
                if supplier_code and supplier_code in SUPPLIER_CODES['autopiter']:
                    is_our_item = supplier_code in supplier_text
                else:
                    # Проверяем по артикулу и производителю
                    is_our_item = (article.lower() in title.lower() and 
                                 manufacturer.lower() in title.lower())
                
                if is_our_item:
                    our_items.append({
                        'title': title,
                        'price': price,
                        'supplier': supplier_text
                    })
                else:
                    # Проверяем фильтр бренда конкурента
                    if not competitor_brand_filter or competitor_brand_filter.lower() in title.lower():
                        competitor_items.append({
                            'title': title,
                            'price': price,
                            'supplier': supplier_text
                        })
                        
            except Exception as e:
                continue
        
        # Анализируем результаты
        if our_items:
            result['is_found'] = True
            # Берем минимальную цену среди наших товаров
            our_prices = [item['price'] for item in our_items if item['price']]
            if our_prices:
                result['marketplace_price'] = min(our_prices)
        
        # Анализируем цены конкурентов
        if competitor_items:
            competitor_prices = [item['price'] for item in competitor_items if item['price']]
            if competitor_prices:
                min_price = min(competitor_prices)
                result['min_competitor_price'] = min_price
                
                # Находим бренд с минимальной ценой
                for item in competitor_items:
                    if item['price'] == min_price:
                        result['competitor_brand'] = item['supplier']
                        break
        
    except Exception as e:
        result['error_message'] = f"Ошибка парсинга АвтоПитер: {str(e)}"
    
    return result

def check_emex_item(supplier_code: str, manufacturer: str, article: str, competitor_brand_filter: str = None) -> Dict:
    """Проверяет наличие позиции на Емекс и анализирует цены"""
    result = {
        'is_found': False,
        'marketplace_price': None,
        'min_competitor_price': None,
        'competitor_brand': None,
        'error_message': ''
    }
    
    try:
        # Формируем поисковый запрос
        search_query = f"{manufacturer} {article}"
        if supplier_code and supplier_code in SUPPLIER_CODES['emex']:
            search_query = f"{supplier_code} {search_query}"
        
        url = f"https://emex.ru/search?q={quote(search_query)}"
        
        # Делаем запрос
        response = make_request(url, timeout=TIMEOUT)
        if not response:
            result['error_message'] = "Ошибка запроса к Емекс"
            return result
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Парсим результаты поиска (аналогично АвтоПитер)
        # ... код парсинга Емекс ...
        
    except Exception as e:
        result['error_message'] = f"Ошибка парсинга Емекс: {str(e)}"
    
    return result

def check_armtek_item(supplier_code: str, manufacturer: str, article: str, competitor_brand_filter: str = None) -> Dict:
    """Проверяет наличие позиции на Армтек и анализирует цены"""
    result = {
        'is_found': False,
        'marketplace_price': None,
        'min_competitor_price': None,
        'competitor_brand': None,
        'error_message': ''
    }
    
    try:
        # Для Армтек используем только артикул и производителя
        search_query = f"{manufacturer} {article}"
        url = f"https://armtek.ru/search?text={quote(search_query)}"
        
        # Используем Selenium для Армтек
        driver = None
        try:
            options = Options()
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-images')
            options.add_argument('--disable-javascript')
            
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            driver.implicitly_wait(5)
            
            driver.get(url)
            time.sleep(3)
            
            # Парсим результаты
            # ... код парсинга Армтек с Selenium ...
            
        finally:
            if driver:
                driver.quit()
        
    except Exception as e:
        result['error_message'] = f"Ошибка парсинга Армтек: {str(e)}"
    
    return result

def create_result_excel(items: List[Dict], output_path: str) -> bool:
    """Создает Excel файл с результатами анализа"""
    try:
        # Подготавливаем данные для Excel
        excel_data = []
        
        for i, item in enumerate(items, 1):
            row = {
                '№': i,
                'Бренд': item['manufacturer'],
                'Артикул по Бренду': item['article'],
                'Наименование': item['nomenclature'],
                'наличие': 'выгружено' if item['is_found'] else 'НЕТ',
                'источник': item.get('platform', ''),
                'Цена Наша': f"{item['marketplace_price']:.0f} ₽" if item['marketplace_price'] else '',
                'Минимальная цена конкурента': f"{item['min_competitor_price']:.0f} ₽" if item['min_competitor_price'] else ''
            }
            excel_data.append(row)
        
        # Создаем DataFrame и сохраняем в Excel
        df = pd.DataFrame(excel_data)
        
        # Настраиваем стили для Excel
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Результаты', index=False)
            
            # Получаем рабочий лист для стилизации
            worksheet = writer.sheets['Результаты']
            
            # Применяем стили
            from openpyxl.styles import PatternFill, Font
            
            # Зеленый фон для "выгружено"
            green_fill = PatternFill(start_color='90EE90', end_color='90EE90', fill_type='solid')
            red_fill = PatternFill(start_color='FFB6C1', end_color='FFB6C1', fill_type='solid')
            
            for row in range(2, len(excel_data) + 2):  # Начинаем с 2 (после заголовка)
                # Проверяем статус наличия
                status_cell = worksheet[f'E{row}']  # Колонка E - наличие
                if status_cell.value == 'выгружено':
                    status_cell.fill = green_fill
                elif status_cell.value == 'НЕТ':
                    status_cell.fill = red_fill
        
        log_debug(f"Файл результата создан: {output_path}")
        return True
        
    except Exception as e:
        log_debug(f"Ошибка создания файла результата: {str(e)}")
        return False
