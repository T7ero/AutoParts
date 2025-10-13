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
from .autopiter_parser import get_next_proxy, make_request, get_brands_by_artikul, get_brands_by_artikul_emex, get_brands_by_artikul_armtek

# Настройки для парсинга прайс-листа
TIMEOUT = 15  # Увеличиваем таймаут
SELENIUM_TIMEOUT = 20
PAGE_LOAD_TIMEOUT = 20
MAX_HTTP_RETRIES = 3  # Максимальное количество попыток HTTP-запросов

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

def _norm_brand(val: str) -> str:
    try:
        s = (val or '').strip().upper()
        return re.sub(r"[^0-9A-ZА-ЯЁ]+", "", s)
    except Exception:
        return ''

def parse_price_list_file(file_path: str) -> List[Dict]:
    """Парсит Excel файл прайс-листа и возвращает список позиций.
    Ищет строку заголовков в первых 20 строках (подходит под ваш шаблон с «шапкой»).
    """
    try:
        # Читаем без заголовков
        df_raw = pd.read_excel(file_path, header=None, dtype=str)

        def norm(val):
            try:
                return str(val).strip().lower()
            except Exception:
                return ''

        header_row = None
        man_idx = art_idx = None
        supp_idx = nom_idx = qty_idx = price_idx = None

        scan_rows = min(20, len(df_raw))
        for i in range(scan_rows):
            row_vals = [norm(v) for v in df_raw.iloc[i].tolist()]
            tmp_man = next((j for j, c in enumerate(row_vals) if 'производител' in c or 'бренд' in c), None)
            tmp_art = next((j for j, c in enumerate(row_vals) if 'артикул' in c), None)
            if tmp_man is not None and tmp_art is not None:
                header_row = i
                man_idx, art_idx = tmp_man, tmp_art
                supp_idx = next((j for j, c in enumerate(row_vals) if 'код поставщика' in c or ('поставщик' in c and 'код' in c)), None)
                nom_idx = next((j for j, c in enumerate(row_vals) if 'номенклатура' in c or 'наимен' in c), None)
                qty_idx = next((j for j, c in enumerate(row_vals) if 'колич' in c or 'в наличии' in c), None)
                price_idx = next((j for j, c in enumerate(row_vals) if 'цена' in c or 'оптов' in c), None)
                break

        if header_row is None:
            raise ValueError('Не найдены обязательные колонки: Производитель и Артикул')

        headers = df_raw.iloc[header_row].tolist()
        for k in range(len(headers)):
            if pd.isna(headers[k]) or str(headers[k]).strip() == '':
                headers[k] = headers[k-1] if k > 0 else f'col_{k}'

        df = df_raw.iloc[header_row + 1:].reset_index(drop=True)
        df.columns = headers

        supplier_col = df.columns[supp_idx] if supp_idx is not None and supp_idx < len(df.columns) else None
        manufacturer_col = df.columns[man_idx]
        article_col = df.columns[art_idx]
        nomenclature_col = df.columns[nom_idx] if nom_idx is not None and nom_idx < len(df.columns) else None
        quantity_col = df.columns[qty_idx] if qty_idx is not None and qty_idx < len(df.columns) else None
        price_col = df.columns[price_idx] if price_idx is not None and price_idx < len(df.columns) else None

        def to_int_safe(v):
            try:
                return int(float(str(v).replace(' ', '').replace('\xa0', '')))
            except Exception:
                return 0

        def to_float_safe(v):
            try:
                s = str(v).replace(' ', '').replace('\xa0', '').replace('₽', '').replace(',', '.')
                return float(s)
            except Exception:
                return None

        items: List[Dict] = []
        for index, row in df.iterrows():
            try:
                manufacturer = str(row[manufacturer_col]).strip() if pd.notna(row[manufacturer_col]) else ''
                article = str(row[article_col]).strip() if pd.notna(row[article_col]) else ''
                if not manufacturer or not article:
                    continue
                item = {
                    'supplier_code': (str(row[supplier_col]).strip() if supplier_col and pd.notna(row[supplier_col]) else ''),
                    'manufacturer': manufacturer,
                    'article': article,
                    'nomenclature': (str(row[nomenclature_col]).strip() if nomenclature_col and pd.notna(row[nomenclature_col]) else ''),
                    'quantity': (to_int_safe(row[quantity_col]) if quantity_col and pd.notna(row[quantity_col]) else 0),
                    'our_price': (to_float_safe(row[price_col]) if price_col and pd.notna(row[price_col]) else None),
                }
                items.append(item)
            except Exception as e:
                log_debug(f'Ошибка парсинга строки {index + 1}: {str(e)}')
                continue

        log_debug(f'Парсинг завершен. Найдено {len(items)} позиций')
        return items

    except Exception as e:
        log_debug(f'Ошибка парсинга файла: {str(e)}')
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
    
    # Определяем URL в начале функции
    product_url = f"https://autopiter.ru/goods/{quote(str(article))}"
    
    try:
        supplier_codes = SUPPLIER_CODES['autopiter']
        our_prices = []  # Будем собирать все наши цены
        competitor_prices = []  # Будем собирать все цены конкурентов
        
        # Значительно увеличенная задержка перед запросом, чтобы избежать rate limit
        time.sleep(random.uniform(5.0, 10.0))
        
        # Получаем прокси для запросов
        proxy_dict = get_next_proxy()
        proxy_str = None
        if proxy_dict:
            proxy_url = proxy_dict.get('http', '')
            if proxy_url.startswith('http://'):
                proxy_str = proxy_url[7:]  # Убираем 'http://'
        
        resp = make_request(product_url, proxy=proxy_str, timeout=TIMEOUT, max_retries=MAX_HTTP_RETRIES)
        if resp and resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Ищем ссылку на карточку товара
            card_link = soup.find('a', href=re.compile(r'/goods/.*/id\d+'))
            if card_link:
                card_url = 'https://autopiter.ru' + card_link['href']
                # Парсим карточку товара с тем же прокси
                card_resp = make_request(card_url, proxy=proxy_str, timeout=TIMEOUT, max_retries=MAX_HTTP_RETRIES)
                if card_resp and card_resp.status_code == 200:
                    card_soup = BeautifulSoup(card_resp.text, 'html.parser')
                    
                    print(f"[DEBUG] Карточка загружена: {card_url}")
                    
                    # Сохраняем HTML для отладки
                    with open('/tmp/autopiter_debug.html', 'w', encoding='utf-8') as f:
                        f.write(card_resp.text)
                    print(f"[DEBUG] HTML сохранен в /tmp/autopiter_debug.html")
                    
                    # Ищем минимальную цену конкурента из блока SelectedOffer
                    min_price_selectors = [
                        '.SelectedOffer__price___Xzg0ZD',
                        '.SelectedOffer__price___Xzg0ZD span',
                        'div.SelectedOffer__price___Xzg0ZD',
                        'div[class*="SelectedOffer__price"]',
                        'span[class*="SelectedOffer__price"]',
                        '.AppraiseBestItems__root___ZmRhZj .SelectedOffer__price___Xzg0ZD',
                        '.AppraiseCard__wrapper___ZmZjYm .SelectedOffer__price___Xzg0ZD',
                        '.AppraiseBestItems__root___ZmRhZj div[class*="SelectedOffer__price"]',
                        '.AppraiseCard__wrapper___ZmZjYm div[class*="SelectedOffer__price"]'
                    ]
                    
                    for selector in min_price_selectors:
                        min_price_el = card_soup.select_one(selector)
                        if min_price_el:
                            min_price_text = min_price_el.get_text(strip=True)
                            min_match = re.search(r'(\d[\d\s]*)', min_price_text.replace('\xa0', ' '))
                            if min_match:
                                competitor_min = float(min_match.group(1).replace(' ', ''))
                                print(f"[DEBUG] Найдена минимальная цена конкурента: {competitor_min}")
                                result['min_competitor_price'] = competitor_min
                                break
                    
                    # Ищем таблицу с предложениями
                    tables = card_soup.find_all('table')
                    print(f"[DEBUG] Найдено таблиц: {len(tables)}")
                    
                    for table_idx, table in enumerate(tables):
                        print(f"[DEBUG] Анализируем таблицу {table_idx + 1}")
                        
                        # Ищем все строки в таблице
                        rows = table.find_all('tr')
                        print(f"[DEBUG] В таблице {table_idx + 1} найдено строк: {len(rows)}")
                        
                        for row_idx, row in enumerate(rows):
                            try:
                                # Пропускаем заголовки
                                if row_idx == 0:
                                    continue
                                    
                                # Ищем все ячейки в строке
                                cells = row.find_all(['td', 'th'])
                                if len(cells) < 5:  # Минимум 5 колонок должно быть
                                    continue
                                
                                # Логируем содержимое строки для отладки
                                row_text = ' | '.join([cell.get_text(strip=True) for cell in cells])
                                print(f"[DEBUG] Строка {row_idx}: {row_text}")
                                
                                # Парсим данные из строки согласно структуре таблицы
                                # Регион | Поставщик | Производитель | Номер | Наименование | Наличие | Доставка | Цена | Заказ
                                if len(cells) >= 8:
                                    supplier_text = cells[1].get_text(strip=True)  # Колонка "Поставщик"
                                    
                                    # Ищем цену в правильной ячейке - пробуем несколько вариантов
                                    price_val = None
                                    
                                    print(f"[DEBUG] Ищем цену в строке {row_idx}, количество ячеек: {len(cells)}")
                                    
                                    # Сначала пробуем найти цену в правильной колонке (7-я колонка обычно содержит цену)
                                    if len(cells) > 7:
                                        price_cell = cells[7]
                                        price_text = price_cell.get_text(strip=True)
                                        print(f"[DEBUG] Проверяем колонку 7 (цена): '{price_text}'")
                                        
                                        # Ищем цену в div с классом NonRetailAppraiseTR__priceWrapper
                                        price_divs = price_cell.find_all(['div', 'span'], class_=re.compile(r'.*NonRetailAppraiseTR__priceWrapper.*'))
                                        for price_div in price_divs:
                                            div_text = price_div.get_text(strip=True)
                                            price_match = re.search(r'(\d[\d\s]*)', div_text.replace('\xa0', ' '))
                                            if price_match:
                                                price_val = float(price_match.group(1).replace(' ', ''))
                                                print(f"[DEBUG] Найдена цена {price_val} в div NonRetailAppraiseTR__priceWrapper")
                                                break
                                        
                                        # Если не нашли в div, ищем в тексте ячейки
                                        if price_val is None:
                                            price_match = re.search(r'(\d[\d\s]*)\s*₽', price_text)
                                            if price_match:
                                                price_val = float(price_match.group(1).replace(' ', ''))
                                                print(f"[DEBUG] Найдена цена {price_val} в тексте ячейки")
                                    
                                    # Если не нашли, пробуем другие ячейки с ценой
                                    if price_val is None:
                                        for cell_idx, cell in enumerate(cells):
                                            cell_class = str(cell.get('class', []))
                                            cell_text = cell.get_text(strip=True)
                                            
                                            # Пропускаем ячейки с кодом поставщика и региона
                                            if 'supplier' in cell_class.lower() or 'region' in cell_class.lower():
                                                continue
                                            
                                            # Ищем ячейки с классом price
                                            if 'price' in cell_class.lower():
                                                price_match = re.search(r'(\d[\d\s]*)\s*₽', cell_text)
                                                if price_match:
                                                    price_val = float(price_match.group(1).replace(' ', ''))
                                                    print(f"[DEBUG] Найдена цена {price_val} в ячейке с классом price")
                                                    break
                                    
                                    print(f"[DEBUG] Итоговая найденная цена: {price_val}")
                                    
                                    if price_val is not None:
                                        # Извлекаем цифры из кода поставщика
                                        sup_digits = re.sub(r'\D+', '', supplier_text)
                                        
                                        print(f"[DEBUG] Найден поставщик '{supplier_text}' ({sup_digits}) с ценой {price_val}")
                                        
                                        # Более точная проверка кода поставщика
                                        is_our_supplier = False
                                        if sup_digits:
                                            # Проверяем точное совпадение
                                            if sup_digits in supplier_codes:
                                                is_our_supplier = True
                                            else:
                                                # Проверяем, содержит ли код поставщика наши коды как подстроку
                                                for our_code in supplier_codes:
                                                    if our_code in sup_digits:
                                                        is_our_supplier = True
                                                        break
                                        
                                        if is_our_supplier:
                                            our_prices.append(price_val)
                                            print(f"[DEBUG] Добавлена наша цена {price_val} для поставщика {sup_digits}")
                                        else:
                                            competitor_prices.append(price_val)
                                            print(f"[DEBUG] Добавлена цена конкурента {price_val} для поставщика {sup_digits}")
                                            
                            except Exception as e:
                                print(f"[DEBUG] Ошибка парсинга строки {row_idx}: {str(e)}")
                                continue
                    
                    # Обрабатываем найденные цены
                    if our_prices:
                        # Берем минимальную цену среди наших поставщиков
                        result['marketplace_price'] = min(our_prices)
                        result['is_found'] = True
                        print(f"[DEBUG] Найдены наши цены: {our_prices}, минимальная: {result['marketplace_price']}")
                    else:
                        print(f"[DEBUG] Наши цены не найдены. Наши коды поставщиков: {supplier_codes}")
                    
                    # Если не нашли минимальную цену конкурента из SelectedOffer, используем минимальную из таблицы
                    if result['min_competitor_price'] is None and competitor_prices:
                        result['min_competitor_price'] = min(competitor_prices)
                        print(f"[DEBUG] Установлена минимальная цена конкурента из таблицы: {result['min_competitor_price']}")
                    
    except Exception as e:
        result['error_message'] = f'HTTP parsing failed: {str(e)}'
        print(f"[DEBUG] Ошибка HTTP парсинга: {str(e)}")
    
    # Если HTTP не нашел нужные элементы, пробуем Selenium с прокси
    if not result['is_found']:
        # Дополнительная задержка перед Selenium для снижения нагрузки
        time.sleep(random.uniform(3.0, 6.0))
        driver = None
        try:
            options = Options()
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-web-security')
            options.add_argument('--disable-features=VizDisplayCompositor')
            options.add_argument('--remote-debugging-port=9222')
            
            # Добавляем прокси для Selenium, если доступен
            proxy_dict = get_next_proxy()
            if proxy_dict:
                proxy_url = proxy_dict.get('http', '')
                if proxy_url.startswith('http://'):
                    proxy_host = proxy_url[7:]  # Убираем 'http://'
                    options.add_argument(f'--proxy-server=http://{proxy_host}')
            
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            driver.implicitly_wait(3)
            driver.get(product_url)
            
            # Переходим в первую карточку товара из списка
            try:
                link_el = WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/goods/"][href*="/id"]'))
                )
                href = link_el.get_attribute('href')
                if href:
                    driver.get(href)
            except Exception:
                pass
            
            # Ждем загрузки таблицы
            try:
                table = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )
                print(f"[DEBUG] Selenium: таблица найдена")
                
                # Ищем минимальную цену конкурента
                if result['min_competitor_price'] is None:
                    min_price_selectors = [
                        '.SelectedOffer__price___Xzg0ZD',
                        '.SelectedOffer__price___Xzg0ZD span',
                        'div.SelectedOffer__price___Xzg0ZD',
                        'div[class*="SelectedOffer__price"]',
                        'span[class*="SelectedOffer__price"]',
                        '.AppraiseBestItems__root___ZmRhZj .SelectedOffer__price___Xzg0ZD',
                        '.AppraiseCard__wrapper___ZmZjYm .SelectedOffer__price___Xzg0ZD',
                        '.AppraiseBestItems__root___ZmRhZj div[class*="SelectedOffer__price"]',
                        '.AppraiseCard__wrapper___ZmZjYm div[class*="SelectedOffer__price"]'
                    ]
                    
                    for selector in min_price_selectors:
                        try:
                            min_price_el = driver.find_element(By.CSS_SELECTOR, selector)
                            min_price_text = min_price_el.text.strip()
                            min_match = re.search(r'(\d[\d\s]*)', min_price_text.replace('\xa0', ' '))
                            if min_match:
                                result['min_competitor_price'] = float(min_match.group(1).replace(' ', ''))
                                print(f"[DEBUG] Selenium: найдена минимальная цена конкурента: {result['min_competitor_price']}")
                                break
                        except Exception as e:
                            print(f"[DEBUG] Selenium: не удалось найти минимальную цену по селектору {selector}: {str(e)}")
                            continue
                
                # Парсим таблицу с предложениями
                rows = table.find_elements(By.TAG_NAME, "tr")
                print(f"[DEBUG] Selenium: найдено строк в таблице: {len(rows)}")
                
                for row_idx, row in enumerate(rows):
                    try:
                        if row_idx == 0:  # Пропускаем заголовок
                            continue
                            
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if len(cells) < 8:
                            continue
                            
                        # Получаем текст из ячеек
                        supplier_text = cells[1].text.strip()  # Поставщик
                        
                        # Ищем цену в правильной ячейке - пробуем несколько вариантов
                        price_val = None
                        
                        print(f"[DEBUG] Selenium: ищем цену в строке {row_idx}, количество ячеек: {len(cells)}")
                        
                        # Сначала пробуем найти цену в правильной колонке (7-я колонка обычно содержит цену)
                        if len(cells) > 7:
                            price_cell = cells[7]
                            price_text = price_cell.text.strip()
                            print(f"[DEBUG] Selenium: проверяем колонку 7 (цена): '{price_text}'")
                            
                            # Ищем цену в div с классом NonRetailAppraiseTR__priceWrapper
                            try:
                                price_divs = price_cell.find_elements(By.CSS_SELECTOR, 'div[class*="NonRetailAppraiseTR__priceWrapper"], span[class*="NonRetailAppraiseTR__priceWrapper"]')
                                for price_div in price_divs:
                                    div_text = price_div.text.strip()
                                    price_match = re.search(r'(\d[\d\s]*)', div_text.replace('\xa0', ' '))
                                    if price_match:
                                        price_val = float(price_match.group(1).replace(' ', ''))
                                        print(f"[DEBUG] Selenium: найдена цена {price_val} в div NonRetailAppraiseTR__priceWrapper")
                                        break
                            except Exception:
                                pass
                            
                            # Если не нашли в div, ищем в тексте ячейки
                            if price_val is None:
                                price_match = re.search(r'(\d[\d\s]*)\s*₽', price_text)
                                if price_match:
                                    price_val = float(price_match.group(1).replace(' ', ''))
                                    print(f"[DEBUG] Selenium: найдена цена {price_val} в тексте ячейки")
                        
                        # Если не нашли, пробуем другие ячейки с ценой
                        if price_val is None:
                            for cell_idx, cell in enumerate(cells):
                                cell_class = cell.get_attribute('class') or ''
                                cell_text = cell.text.strip()
                                
                                # Пропускаем ячейки с кодом поставщика и региона
                                if 'supplier' in cell_class.lower() or 'region' in cell_class.lower():
                                    continue
                                
                                # Ищем ячейки с классом price
                                if 'price' in cell_class.lower():
                                    price_match = re.search(r'(\d[\d\s]*)\s*₽', cell_text)
                                    if price_match:
                                        price_val = float(price_match.group(1).replace(' ', ''))
                                        print(f"[DEBUG] Selenium: найдена цена {price_val} в ячейке с классом price")
                                        break
                        
                        print(f"[DEBUG] Selenium: итоговая найденная цена: {price_val}")
                        
                        if price_val is not None:
                            # Извлекаем цифры из кода поставщика
                            sup_digits = re.sub(r'\D+', '', supplier_text)
                            
                            print(f"[DEBUG] Selenium: найден поставщик '{supplier_text}' ({sup_digits}) с ценой {price_val}")
                            
                            # Более точная проверка кода поставщика
                            is_our_supplier = False
                            if sup_digits:
                                # Проверяем точное совпадение
                                if sup_digits in supplier_codes:
                                    is_our_supplier = True
                                else:
                                    # Проверяем, содержит ли код поставщика наши коды как подстроку
                                    for our_code in supplier_codes:
                                        if our_code in sup_digits:
                                            is_our_supplier = True
                                            break
                            
                            if is_our_supplier:
                                our_prices.append(price_val)
                            else:
                                competitor_prices.append(price_val)
                                
                    except Exception as e:
                        print(f"[DEBUG] Selenium: ошибка парсинга строки {row_idx}: {str(e)}")
                        continue
                
                # Обрабатываем найденные цены
                if our_prices:
                    result['marketplace_price'] = min(our_prices)
                    result['is_found'] = True
                    print(f"[DEBUG] Selenium: найдены наши цены: {our_prices}, минимальная: {result['marketplace_price']}")
                
                # Если не нашли минимальную цену конкурента, используем минимальную из таблицы
                if result['min_competitor_price'] is None and competitor_prices:
                    result['min_competitor_price'] = min(competitor_prices)
                    print(f"[DEBUG] Selenium: установлена минимальная цена конкурента из таблицы: {result['min_competitor_price']}")
                    
            except Exception as e:
                print(f"[DEBUG] Selenium: ошибка поиска таблицы: {str(e)}")
                
        except Exception as e:
            if not result['error_message']:
                result['error_message'] = f'Selenium failed: {str(e)}'
            print(f"[DEBUG] Ошибка Selenium: {str(e)}")
        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass
    
    print(f"[DEBUG] Итоговый результат: наш={result['marketplace_price']}, конкурент={result['min_competitor_price']}, найдено={result['is_found']}")
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
        # Проверяем наличие брендов через основной парсер
        man_ok = False
        try:
            brands = get_brands_by_artikul_emex(article) or []
            man_norm = _norm_brand(manufacturer)
            for b in brands:
                if _norm_brand(b) == man_norm:
                    man_ok = True
                    break
        except Exception:
            pass

        # Формируем поисковый запрос
        search_query = f"{manufacturer} {article}"
        if supplier_code and supplier_code in SUPPLIER_CODES['emex']:
            search_query = f"{supplier_code} {search_query}"
        
        url = f"https://emex.ru/search?q={quote(search_query)}"
        
        # Делаем запрос
        response = make_request(url, timeout=TIMEOUT, max_retries=MAX_HTTP_RETRIES)
        if not response:
            result['error_message'] = "Ошибка запроса к Емекс"
            return result
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Упрощенно ищем цену в выдаче
        txt = soup.get_text(' ', strip=True)
        m = re.search(r'от\s*(\d[\d\s]*)\s*₽', txt) or re.search(r'\b(\d[\d\s]{2,})\b\s*₽', txt)
        if m:
            try:
                result['marketplace_price'] = float(m.group(1).replace(' ', ''))
            except Exception:
                pass
        result['is_found'] = bool(result['marketplace_price'] is not None or man_ok)
        
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
    
    # Увеличенная задержка перед запросом, чтобы избежать rate limit
    time.sleep(random.uniform(5.0, 10.0))
    
    try:
        # Сначала проверяем бренды через основной Selenium-парсер
        man_ok = False
        try:
            brands = get_brands_by_artikul_armtek(article) or []
            man_norm = _norm_brand(manufacturer)
            for b in brands:
                if _norm_brand(b) == man_norm:
                    man_ok = True
                    result['competitor_brand'] = b
                    break
        except Exception as e:
            print(f"[DEBUG] Ошибка получения брендов Armtek: {str(e)}")
        
        # Если нашли бренды, переходим к поиску минимальной цены
        if man_ok:
            try:
                # Ищем минимальную цену через Selenium
                driver = None
                try:
                    options = Options()
                    options.add_argument('--headless=new')
                    options.add_argument('--no-sandbox')
                    options.add_argument('--disable-dev-shm-usage')
                    options.add_argument('--disable-gpu')
                    options.add_argument('--disable-extensions')
                    options.add_argument('--disable-logging')
                    options.add_argument('--log-level=3')
                    options.add_argument('--silent')
                    
                    # Добавляем прокси для Selenium, если доступен
                    proxy_dict = get_next_proxy()
                    if proxy_dict:
                        proxy_url = proxy_dict.get('http', '')
                        if proxy_url.startswith('http://'):
                            proxy_host = proxy_url[7:]  # Убираем 'http://'
                            options.add_argument(f'--proxy-server=http://{proxy_host}')
                    
                    driver = webdriver.Chrome(options=options)
                    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
                    driver.implicitly_wait(3)
                    
                    # Переходим на поисковую страницу
                    search_url = f"https://armtek.ru/search?text={quote(str(article))}"
                    driver.get(search_url)
                    
                    print(f"[DEBUG] Armtek: загружена поисковая страница для {article}")
                    
                    # Ищем первую ссылку на карточку товара
                    try:
                        # Ждем загрузки результатов поиска
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/product/"]'))
                        )
                        
                        # Находим первую ссылку на карточку товара
                        product_link = driver.find_element(By.CSS_SELECTOR, 'a[href*="/product/"]')
                        product_url = product_link.get_attribute('href')
                        
                        if product_url:
                            print(f"[DEBUG] Armtek: найдена ссылка на карточку: {product_url}")
                            
                            # Переходим в карточку товара
                            driver.get(product_url)
                            print(f"[DEBUG] Armtek: перешли в карточку товара")
                            
                            # Ждем загрузки страницы
                            time.sleep(3)
                            
                            # Ищем минимальную цену среди всех предложений
                            min_price = None
                            
                            # Селекторы для поиска цен
                            price_selectors = [
                                'span.font__headline6.no-wrap',
                                'span.font__headline6',
                                '.card__price span',
                                '[class*="price"] span',
                                '.font__headline6'
                            ]
                            
                            for selector in price_selectors:
                                try:
                                    price_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                    prices = []
                                    
                                    for element in price_elements:
                                        price_text = element.text.strip()
                                        if price_text and '₽' in price_text:
                                            # Извлекаем числовое значение цены
                                            price_match = re.search(r'(\d[\d\s]*)', price_text.replace('\xa0', ' '))
                                            if price_match:
                                                try:
                                                    price_value = float(price_match.group(1).replace(' ', ''))
                                                    prices.append(price_value)
                                                    print(f"[DEBUG] Armtek: найдена цена {price_value}₽")
                                                except ValueError:
                                                    continue
                                    
                                    if prices:
                                        min_price = min(prices)
                                        print(f"[DEBUG] Armtek: минимальная цена найдена: {min_price}₽")
                                        break
                                        
                                except Exception as e:
                                    print(f"[DEBUG] Armtek: ошибка поиска цен по селектору {selector}: {str(e)}")
                                    continue
                            
                            if min_price:
                                result['marketplace_price'] = min_price
                                result['min_competitor_price'] = min_price  # На Armtek это одно и то же
                                result['is_found'] = True
                                print(f"[DEBUG] Armtek: итоговый результат - найдено: {min_price}₽")
                            else:
                                print(f"[DEBUG] Armtek: цены не найдены")
                                
                    except Exception as e:
                        print(f"[DEBUG] Armtek: ошибка поиска карточки товара: {str(e)}")
                        
                except Exception as e:
                    print(f"[DEBUG] Armtek: ошибка Selenium: {str(e)}")
                    
                finally:
                    try:
                        if driver:
                            driver.quit()
                    except Exception:
                        pass
                        
            except Exception as e:
                print(f"[DEBUG] Armtek: ошибка поиска минимальной цены: {str(e)}")
        
        # Если Selenium не сработал, пробуем HTTP запрос
        if not result['is_found']:
            try:
                search_url = f"https://armtek.ru/search?text={quote(str(article))}"
                resp = make_request(search_url, timeout=TIMEOUT, max_retries=MAX_HTTP_RETRIES)
                if resp and resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    
                    # Ищем цены в HTML
                    price_patterns = [
                        r'(\d[\d\s]*)\s*₽',
                        r'от\s*(\d[\d\s]*)\s*₽'
                    ]
                    
                    text = soup.get_text(' ', strip=True)
                    prices = []
                    
                    for pattern in price_patterns:
                        matches = re.findall(pattern, text)
                        for match in matches:
                            try:
                                price_value = float(match.replace(' ', ''))
                                if 100 <= price_value <= 1000000:  # Разумный диапазон цен
                                    prices.append(price_value)
                            except ValueError:
                                continue
                    
                    if prices:
                        min_price = min(prices)
                        result['marketplace_price'] = min_price
                        result['min_competitor_price'] = min_price
                        result['is_found'] = True
                        print(f"[DEBUG] Armtek HTTP: найдена минимальная цена: {min_price}₽")
                        
            except Exception as e:
                print(f"[DEBUG] Armtek: ошибка HTTP парсинга: {str(e)}")
        
    except Exception as e:
        result['error_message'] = f"Ошибка парсинга Армтек: {str(e)}"
        print(f"[DEBUG] Armtek: общая ошибка: {str(e)}")
    
    print(f"[DEBUG] Armtek: итоговый результат - найдено: {result['is_found']}, цена: {result['marketplace_price']}₽")
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
