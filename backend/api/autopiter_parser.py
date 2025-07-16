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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
import logging

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT = 15
SELENIUM_TIMEOUT = 30  # Увеличим таймаут для Selenium

def log_debug(message):
    print(f"[DEBUG] {message}")

def make_request(url, proxies=None, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                proxies=proxies,
                timeout=TIMEOUT
            )
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                wait_time = (attempt + 1) * 5
                log_debug(f"Rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                log_debug(f"Request failed (attempt {attempt + 1}): HTTP {response.status_code}")
        except Exception as e:
            log_debug(f"Request error (attempt {attempt + 1}): {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(2)
    
    return None

def get_brands_by_artikul(artikul, proxies=None):
    """Парсер для Autopiter.ru"""
    url = f"https://autopiter.ru/goods/{artikul}"
    log_debug(f"Autopiter: запрос к {url}")
    
    response = make_request(url, proxies)
    if not response:
        log_debug("Autopiter: не удалось получить данные")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    brands = set()
    
    # Метод 1: Парсинг таблицы предложений
    for row in soup.select('tr[data-qa-id="offer-row"]'):
        brand_tag = row.select_one('span[data-qa-id="brand-name"]')
        if brand_tag:
            brand = brand_tag.get_text(strip=True)
            if brand and brand.lower() != 'показать все':
                brands.add(brand)
    
    # Метод 2: Парсинг JSON данных
    script_tag = soup.find('script', string=re.compile('window.__NUXT__'))
    if script_tag:
        try:
            script_text = script_tag.string
            json_str = re.search(r'window\.__NUXT__\s*=\s*(.*?});', script_text).group(1)
            data = json.loads(json_str)
            offers = data.get('data', [{}])[0].get('offers', {}).get('items', [])
            for offer in offers:
                brand_info = offer.get('brand', {})
                if brand_info:
                    brand = brand_info.get('name')
                    if brand:
                        brands.add(brand)
        except Exception as e:
            log_debug(f"Autopiter JSON error: {str(e)}")
    
    # Метод 3: Резервный метод
    if not brands:
        for tag in soup.select('span[title]'):
            txt = tag.get('title', '').strip()
            if txt and txt.lower() not in ['показать все', 'все']:
                brands.add(txt)
    
    return sorted(brands)

def get_brands_by_artikul_armtek(artikul, proxies=None):
    """Улучшенный парсер Armtek с комбинированным подходом"""
    # 1. Сначала пробуем API
    api_brands = parse_armtek_api(artikul, proxies)
    if api_brands:
        return api_brands
    
    # 2. Если API не сработало, используем Selenium с улучшенными селекторами
    return parse_armtek_api(artikul)

def parse_armtek_api(artikul, proxies=None):
    """Попытка получить данные через API"""
    url = f"https://armtek.ru/api/search?query={quote(artikul)}&limit=50"
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            },
            proxies=proxies,
            timeout=10
        )
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                try:
                    data = response.json()
                    if 'products' in data or 'items' in data:
                        return parse_api_response(data)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return None

def parse_api_response(data):
    """Анализ API ответа"""
    brands = set()
    items = data.get('products', data.get('items', []))
    
    for item in items:
        brand = None
        if isinstance(item, dict):
            # Разные варианты расположения бренда в ответе
            brand = item.get('brand') or item.get('manufacturer')
            if isinstance(brand, dict):
                brand = brand.get('name')
        
        if brand and isinstance(brand, str) and len(brand) > 2:
            brands.add(brand.strip())
    
    return sorted(brands) if brands else None

def extract_brands_from_api_data(data):
    """Извлечение брендов из API ответа Armtek"""
    brands = set()
    stopwords = {
        'Войти', 'Гараж', 'Показать еще', 'Показать все', 'Все', 'Главная', 
        'Корзина', 'Подбор', 'РФ', 'Каталог', 'Оформить заказ'
    }
    
    # Обрабатываем разные варианты структуры ответа
    items = data.get('products', []) or data.get('items', []) or []
    
    for item in items:
        brand = None
        if isinstance(item, dict):
            # Вариант 1: бренд в поле 'brand' как строка
            if 'brand' in item and isinstance(item['brand'], str):
                brand = item['brand']
            # Вариант 2: бренд в поле 'brand' как объект
            elif 'brand' in item and isinstance(item['brand'], dict):
                brand = item['brand'].get('name')
            # Вариант 3: бренд в поле 'manufacturer'
            elif 'manufacturer' in item:
                brand = item['manufacturer']
        
        if brand and brand not in stopwords and len(brand) > 2:
            brands.add(brand.strip())
    
    return sorted(brands)

def parse_armtek_selenium(artikul):
    """Парсинг через Selenium с улучшенными ожиданиями"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(f"https://armtek.ru/search?text={quote(artikul)}")
        
        # Улучшенное ожидание с несколькими вариантами селекторов
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".product-card, [data-testid='product-item'], .catalog-item")
                )
            )
        except Exception:
            pass  # Продолжаем даже если не дождались
        
        # Альтернативный поиск брендов
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Основные места расположения брендов
        brand_selectors = [
            'span.font__body2.brand--selecting',  # Основной бренд (синий)
            '.product-card .brand-name',          # Бренд в карточке
            '.product-card__brand',              # Альтернативный селектор
            '[itemprop="brand"]',                # Микроразметка
            '.catalog-item__brand'              # Еще один вариант
        ]
        
        brands = set()
        for selector in brand_selectors:
            for tag in soup.select(selector):
                brand = tag.get_text(strip=True)
                if brand and len(brand) > 2 and not brand.isdigit():
                    brands.add(brand)
        
        return sorted(brands) if brands else []
        
    except Exception as e:
        print(f"Selenium error: {str(e)}")
        return []
    finally:
        driver.quit()

def extract_brands_from_selenium_page(page_source):
    """Извлечение брендов из HTML страницы"""
    soup = BeautifulSoup(page_source, 'html.parser')
    brands = set()
    stopwords = {
        'Войти', 'Гараж', 'Показать еще', 'Показать все', 'Все', 'Главная',
        'Корзина', 'Подбор', 'РФ', 'Каталог', 'Оформить заказ'
    }
    
    # Основной бренд (синий)
    main_brand = soup.select_one('span.font__body2.brand--selecting')
    if main_brand:
        brand_text = main_brand.get_text(strip=True)
        if brand_text and brand_text not in stopwords:
            brands.add(brand_text)
    
    # Бренды из карточек товаров
    for card in soup.select("[data-testid='product-item'], .product-card"):
        brand_tag = card.select_one('span.font__body2, [class*="brand"]')
        if brand_tag:
            brand_text = brand_tag.get_text(strip=True)
            if brand_text and brand_text not in stopwords and len(brand_text) > 2:
                brands.add(brand_text)
    
    return sorted(brands)

def get_brands_by_artikul_armtek(artikul, proxies=None):
    """Главная функция с приоритетом API и кешированием"""
    # Пробуем API первым делом
    api_brands = parse_armtek_api(artikul, proxies)
    if api_brands:
        return api_brands
    
    # Если API не дало результатов, используем оптимизированный Selenium
    return parse_armtek_selenium(artikul)

def get_brands_by_artikul_emex(artikul, proxies=None):
    """Парсер для Emex с обработкой API"""
    encoded_artikul = quote(artikul)
    api_url = f"https://emex.ru/api/search/search?detailNum={encoded_artikul}&locationId=263"
    log_debug(f"Emex API: запрос к {api_url}")
    
    try:
        response = make_request(api_url, proxies)
        if not response or response.status_code != 200:
            return []

        data = response.json()
        brands = set()

        # Основные бренды
        for item in data.get("searchResult", {}).get("makes", {}).get("list", []):
            if brand := item.get("make"):
                brands.add(brand)

        # Альтернативные источники
        for item in data.get("searchResult", {}).get("details", []):
            if brand := item.get("make", {}).get("name"):
                brands.add(brand)

        return sorted(brands)
    except Exception as e:
        log_debug(f"Emex API error: {str(e)}")
        return []


def get_brands_by_artikul_emex(artikul, proxies=None):
    # Кодируем артикул для URL
    encoded_artikul = quote(artikul)
    manufacturer = quote("Hyundai / KIA")
    
    # Основной URL API
    api_url = f"https://emex.ru/api/search/search?detailNum={encoded_artikul}&locationId=263&showAll=false&isHeaderSearch=true"
    
    # Заголовки для имитации браузера
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://emex.ru/products/{encoded_artikul}/{manufacturer}",
        "x-requested-with": "XMLHttpRequest",
    }
    
    log_debug(f"[API] Emex: запрос к {api_url}")
    
    try:
        response = requests.get(api_url, headers=headers, proxies=proxies, timeout=15)
        if response.status_code != 200:
            log_debug(f"[API] Emex: HTTP ошибка {response.status_code}")
            return []
            
        data = response.json()
        brands = set()
        
        # Основной путь: извлекаем бренды из searchResult.makes.list
        try:
            makes_list = data.get("searchResult", {}).get("makes", {}).get("list", [])
            for item in makes_list:
                if "make" in item:
                    brand = item["make"]
                    if brand:
                        brands.add(brand)
        except Exception as e:
            log_debug(f"[API] Emex: ошибка обработки makes.list: {str(e)}")
        
        # Альтернативный путь: извлекаем бренды из searchResult.details
        if not brands:
            try:
                details_list = data.get("searchResult", {}).get("details", [])
                for item in details_list:
                    if "make" in item and "name" in item["make"]:
                        brand = item["make"]["name"]
                        if brand:
                            brands.add(brand)
            except Exception as e:
                log_debug(f"[API] Emex: ошибка обработки details: {str(e)}")
        
        # Дополнительный путь: извлекаем бренды из заголовков
        if not brands:
            try:
                if "searchResult" in data:
                    if "make" in data["searchResult"]:
                        brand = data["searchResult"]["make"]
                        if brand:
                            brands.add(brand)
                    if "makes" in data["searchResult"] and "header" in data["searchResult"]["makes"]:
                        # Парсим бренды из текста заголовка
                        header = data["searchResult"]["makes"]["header"]
                        # Пример: "Товары с этим номером 58220-45201 встречаются у 23 производителей"
                        # Извлекаем число и пропускаем этот метод, так как он ненадежен
                        pass
            except Exception as e:
                log_debug(f"[API] Emex: ошибка обработки заголовков: {str(e)}")
        
        return sorted(brands)
    
    except Exception as e:
        log_debug(f"[API] Emex: ошибка: {str(e)}")
        return []