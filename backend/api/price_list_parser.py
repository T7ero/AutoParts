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
    
    try:
        product_url = f"https://autopiter.ru/goods/{quote(article)}"
        supplier_codes = SUPPLIER_CODES['autopiter']
        our_price = None
        competitor_min = None
        
        # Сначала пробуем HTTP-парсинг с прокси
        # Получаем прокси для запросов
        proxy_dict = get_next_proxy()
        proxy_str = None
        if proxy_dict:
            proxy_url = proxy_dict.get('http', '')
            if proxy_url.startswith('http://'):
                proxy_str = proxy_url[7:]  # Убираем 'http://'
        
        resp = make_request(product_url, proxy=proxy_str, timeout=TIMEOUT)
        if resp and resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Ищем ссылку на карточку товара
            card_link = soup.find('a', href=re.compile(r'/goods/.*/id\d+'))
            if card_link:
                card_url = 'https://autopiter.ru' + card_link['href']
                # Парсим карточку товара с тем же прокси
                card_resp = make_request(card_url, proxy=proxy_str, timeout=TIMEOUT)
                if card_resp and card_resp.status_code == 200:
                    card_soup = BeautifulSoup(card_resp.text, 'html.parser')
                    
                    # Ищем минимальную цену конкурента
                    min_price_el = card_soup.select_one('.SelectedOffer__price___Xzg0ZD')
                    if min_price_el:
                        min_price_text = min_price_el.get_text(strip=True)
                        min_match = re.search(r'(\d[\d\s]{2,})', min_price_text)
                        if min_match:
                            competitor_min = float(min_match.group(1).replace(' ', ''))
                    
                    # Ищем наши цены в таблице
                    supplier_cells = card_soup.find_all('td', class_=re.compile(r'.*supplierCell.*'))
                    for cell in supplier_cells:
                        cell_text = cell.get_text(strip=True)
                        sup_digits = re.sub(r'\D+', '', cell_text)
                        if sup_digits in supplier_codes:
                            # Ищем цену в той же строке
                            row = cell.find_parent('tr')
                            if row:
                                price_cell = row.find('td', class_=re.compile(r'.*priceCell.*'))
                                if price_cell:
                                    price_wrapper = price_cell.find('div', class_=re.compile(r'.*priceWrapper.*'))
                                    if price_wrapper:
                                        price_span = price_wrapper.find('span')
                                        if price_span:
                                            price_text = price_span.get_text(strip=True)
                                            price_match = re.search(r'(\d[\d\s]{2,})', price_text)
                                            if price_match:
                                                our_price = float(price_match.group(1).replace(' ', ''))
                                                break
    except Exception as e:
        result['error_message'] = f'HTTP parsing failed: {str(e)}'
        
        # Если HTTP не сработал, пробуем Selenium с прокси
        if our_price is None:
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
                
                # Ждем появления таблицы с поставщиками
                try:
                    WebDriverWait(driver, SELENIUM_TIMEOUT).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'td[class*="supplierCell"]'))
                    )
                    
                    # Ищем минимальную цену конкурента
                    if competitor_min is None:
                        try:
                            min_price_el = driver.find_element(By.CSS_SELECTOR, '.SelectedOffer__price___Xzg0ZD')
                            min_price_text = min_price_el.text.strip()
                            min_match = re.search(r'(\d[\d\s]{2,})', min_price_text)
                            if min_match:
                                competitor_min = float(min_match.group(1).replace(' ', ''))
                        except Exception:
                            pass
                    
                    # Ищем наши цены
                    supplier_cells = driver.find_elements(By.CSS_SELECTOR, 'td[class*="supplierCell"]')
                    for cell in supplier_cells:
                        try:
                            cell_text = cell.text.strip()
                            sup_digits = re.sub(r'\D+', '', cell_text)
                            if sup_digits in supplier_codes:
                                # Ищем цену в той же строке
                                row = cell.find_element(By.XPATH, './..')
                                price_cell = row.find_element(By.CSS_SELECTOR, 'td[class*="priceCell"]')
                                price_wrapper = price_cell.find_element(By.CSS_SELECTOR, 'div[class*="priceWrapper"]')
                                price_span = price_wrapper.find_element(By.CSS_SELECTOR, 'span')
                                price_text = price_span.text.strip()
                                price_match = re.search(r'(\d[\d\s]{2,})', price_text)
                                if price_match:
                                    our_price = float(price_match.group(1).replace(' ', ''))
                                    break
                        except Exception:
                            continue
                except Exception:
                    pass
            except Exception as e:
                if not result['error_message']:
                    result['error_message'] = f'Selenium failed: {str(e)}'
            finally:
                try:
                    if driver:
                        driver.quit()
                except Exception:
                    pass

        if our_price is not None:
            result['marketplace_price'] = our_price
            result['is_found'] = True
        else:
            result['is_found'] = False
        if competitor_min is not None:
            result['min_competitor_price'] = competitor_min
        
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
        response = make_request(url, timeout=TIMEOUT)
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
    
    try:
        # Проверка брендов через основной Selenium-парсер
        man_ok = False
        try:
            brands = get_brands_by_artikul_armtek(article) or []
            man_norm = _norm_brand(manufacturer)
            for b in brands:
                if _norm_brand(b) == man_norm:
                    man_ok = True
                    break
        except Exception:
            pass
        
        # Пытаемся достать цену из HTML поисковой страницы
        search_query = f"{manufacturer} {article}"
        url = f"https://armtek.ru/search?text={quote(search_query)}"
        resp = make_request(url, timeout=TIMEOUT)
        if resp and resp.status_code == 200:
            txt = BeautifulSoup(resp.text, 'html.parser').get_text(' ', strip=True)
            m = re.search(r'от\s*(\d[\d\s]*)\s*₽', txt) or re.search(r'\b(\d[\d\s]{2,})\b\s*₽', txt)
            if m:
                try:
                    result['marketplace_price'] = float(m.group(1).replace(' ', ''))
                except Exception:
                    pass
        result['is_found'] = bool(result['marketplace_price'] is not None or man_ok)
        
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
