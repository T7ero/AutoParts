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
import tempfile
import uuid

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}
TIMEOUT = 15  # Увеличили общий таймаут
SELENIUM_TIMEOUT = 25  # Увеличили таймаут для Selenium

# Кеш для хранения результатов запросов
REQUEST_CACHE = {}
CACHE_EXPIRATION = 600  # 10 минут

def log_debug(message):
    print(f"[DEBUG] {message}")

def cleanup_chrome_processes():
    """Принудительно завершает зависшие процессы Chrome"""
    try:
        kill_commands = [
            ['pkill', '-f', 'chrome'],
            ['pkill', '-f', 'chromedriver'],
            ['pkill', '-f', 'google-chrome'],
            ['pkill', '-f', 'chromium'],
            ['killall', '-9', 'chrome'],
            ['killall', '-9', 'chromedriver']
        ]
        
        for cmd in kill_commands:
            try:
                subprocess.run(cmd, 
                              stdout=subprocess.DEVNULL, 
                              stderr=subprocess.DEVNULL,
                              timeout=2)
            except:
                pass
        
        try:
            ps_output = subprocess.check_output(['ps', 'aux'], text=True, timeout=3)
            for line in ps_output.split('\n'):
                if 'chrome' in line.lower() or 'chromedriver' in line.lower():
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        try:
                            subprocess.run(['kill', '-9', pid], 
                                          stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL,
                                          timeout=1)
                        except:
                            pass
            time.sleep(0.5)
        except:
            pass
    except Exception as e:
        log_debug(f"Error cleaning up Chrome processes: {e}")

def make_request(url, proxies=None, max_retries=3, cache_key=None):
    """Улучшенный запрос с кешированием и повторными попытками"""
    # Проверка кеша
    if cache_key and cache_key in REQUEST_CACHE:
        cached_time, response = REQUEST_CACHE[cache_key]
        if time.time() - cached_time < CACHE_EXPIRATION:
            return response
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                proxies=proxies,
                timeout=TIMEOUT
            )
            if response.status_code == 200:
                # Сохраняем в кеш
                if cache_key:
                    REQUEST_CACHE[cache_key] = (time.time(), response)
                return response
            elif response.status_code == 429:
                wait_time = (attempt + 1) * 3
                log_debug(f"Rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                log_debug(f"Request failed (attempt {attempt + 1}): HTTP {response.status_code}")
        except Exception as e:
            log_debug(f"Request error (attempt {attempt + 1}): {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(1)
    
    return None

def get_brands_by_artikul(artikul, proxies=None):
    """Парсер для Autopiter.ru"""
    url = f"https://autopiter.ru/goods/{artikul}"
    log_debug(f"Autopiter: запрос к {url}")
    
    response = make_request(url, proxies, cache_key=f"autopiter_{artikul}")
    if not response:
        log_debug("Autopiter: не удалось получить данные")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    brands = set()
    
    # Попытка 1: Парсинг таблицы
    for row in soup.select('tr[data-qa-id="offer-row"]'):
        brand_tag = row.select_one('span[data-qa-id="brand-name"]')
        if brand_tag:
            brand = brand_tag.get_text(strip=True)
            if brand and brand.lower() not in ['показать все', 'все']:
                brands.add(brand)
    
    # Попытка 2: Парсинг JSON в скрипте
    if not brands:
        script_tag = soup.find('script', string=re.compile('window.__NUXT__'))
        if script_tag:
            try:
                script_text = script_tag.string
                json_match = re.search(r'window\.__NUXT__\s*=\s*(.*?});', script_text)
                if json_match:
                    json_str = json_match.group(1)
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
    
    # Попытка 3: Парсинг атрибутов title
    if not brands:
        for tag in soup.select('span[title]'):
            txt = tag.get('title', '').strip()
            if txt and txt.lower() not in ['показать все', 'все']:
                brands.add(txt)
    
    # Попытка 4: Поиск по тексту
    if not brands:
        brand_pattern = re.compile(r'(бренд|производитель|brand|manufacturer)', re.IGNORECASE)
        for tag in soup.find_all(['span', 'div', 'a']):
            text = tag.get_text(strip=True)
            if text and len(text) > 2 and len(text) < 50:
                if not brand_pattern.search(text):
                    brands.add(text)
    
    return sorted(brands)

def get_brands_by_artikul_armtek(artikul, proxies=None):
    """Улучшенный парсер Armtek"""
    # 1. Пробуем API
    api_brands = parse_armtek_api(artikul, proxies)
    if api_brands:
        return api_brands
    
    # 2. Пробуем HTTP запрос
    http_brands = parse_armtek_http(artikul, proxies)
    if http_brands:
        return http_brands
    
    # 3. Если API и HTTP не сработали, используем Selenium
    return parse_armtek_selenium(artikul)

def parse_armtek_api(artikul, proxies=None):
    """Попытка получить данные через API"""
    url = f"https://armtek.ru/api/search?query={quote(artikul)}&limit=50"
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": HEADERS["User-Agent"],
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest"
            },
            proxies=proxies,
            timeout=8
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                brands = set()
                
                # Обработка различных форматов ответа
                items = data.get('products', []) or data.get('items', []) or data.get('results', [])
                
                for item in items:
                    brand = None
                    if isinstance(item, dict):
                        brand = item.get('brand') or item.get('manufacturer') or item.get('vendor')
                        if isinstance(brand, dict):
                            brand = brand.get('name')
                    
                    if brand and isinstance(brand, str) and len(brand) > 2:
                        brands.add(brand.strip())
                
                return sorted(brands) if brands else None
            except json.JSONDecodeError:
                pass
    except Exception as e:
        log_debug(f"Armtek API error: {str(e)}")
    return None

def parse_armtek_selenium(artikul):
    """Парсинг через Selenium с оптимизацией"""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--blink-settings=imagesEnabled=false')
    options.add_argument('--remote-debugging-port=0')
    options.add_argument('--disable-web-security')
    options.add_argument('--single-process')
    options.add_argument('--disable-logging')
    options.add_argument('--log-level=3')
    options.add_argument('--user-agent=' + HEADERS["User-Agent"])
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = None
    try:
        cleanup_chrome_processes()
        time.sleep(1)
        
        try:
            service = Service('/usr/local/bin/chromedriver')
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            log_debug(f"Chrome driver init error: {str(e)}")
            driver = webdriver.Chrome(options=options)
        
        driver.set_page_load_timeout(SELENIUM_TIMEOUT)
        driver.set_script_timeout(SELENIUM_TIMEOUT)
        driver.implicitly_wait(5)
        
        driver.get(f"https://armtek.ru/search?text={quote(artikul)}")
        
        try:
            # Ожидаем появления результатов
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".product-card, .catalog-item, [data-testid='product-item']")
                )
            )
            time.sleep(1)  # Дополнительное время для стабилизации
        except Exception:
            pass
        
        # Извлекаем бренды из HTML
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        brand_selectors = [
            '.product-card .brand-name',
            '.product-card__brand',
            '[itemprop="brand"]',
            '.catalog-item__brand',
            '.brand-name',
            '.product-brand',
            'span[data-brand]',
            '.item-brand',
            '.brand__name',
            '.manufacturer-name',
            '.vendor-title'
        ]
        
        brands = set()
        for selector in brand_selectors:
            for tag in soup.select(selector):
                brand = tag.get_text(strip=True)
                if brand and len(brand) > 2 and not brand.isdigit():
                    brands.add(brand)
        
        # Дополнительный поиск по тексту
        if not brands:
            brand_pattern = re.compile(r'(бренд|производитель|brand|manufacturer)', re.IGNORECASE)
            for tag in soup.find_all(['span', 'div', 'a', 'h3']):
                text = tag.get_text(strip=True)
                if text and len(text) > 2 and len(text) < 50:
                    if not brand_pattern.search(text) and not any(char.isdigit() for char in text):
                        brands.add(text)
        
        return sorted(brands) if brands else []
        
    except Exception as e:
        log_debug(f"Selenium error: {str(e)}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        cleanup_chrome_processes()
        time.sleep(0.5)

def parse_armtek_http(artikul, proxies=None):
    """Парсинг Armtek через HTTP запрос"""
    url = f"https://armtek.ru/search?text={quote(artikul)}"
    
    response = make_request(url, proxies, cache_key=f"armtek_{artikul}")
    if not response:
        log_debug("Armtek HTTP: не удалось получить данные")
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    brands = set()
    
    selectors = [
        '.product-card .brand-name',
        '.product-card__brand',
        '[itemprop="brand"]',
        '.catalog-item__brand',
        '.brand-name',
        '.product-brand',
        'span[data-brand]',
        '.item-brand',
        '.brand__name',
        '.manufacturer-name',
        '.vendor-title'
    ]
    
    for selector in selectors:
        for tag in soup.select(selector):
            brand = tag.get_text(strip=True)
            if brand and len(brand) > 2 and not brand.isdigit():
                brands.add(brand)
    
    # Поиск в JSON данных
    script_tags = soup.find_all('script', type='application/ld+json')
    for script in script_tags:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") == "Product":
                        brand = item.get("brand", {}).get("name")
                        if brand:
                            brands.add(brand)
            elif isinstance(data, dict) and data.get("@type") == "Product":
                brand = data.get("brand", {}).get("name")
                if brand:
                    brands.add(brand)
        except:
            pass
    
    # Поиск по тексту
    if not brands:
        brand_pattern = re.compile(r'(бренд|производитель|brand|manufacturer)', re.IGNORECASE)
        for tag in soup.find_all(['span', 'div', 'a', 'h3']):
            text = tag.get_text(strip=True)
            if text and len(text) > 2 and len(text) < 50:
                if not brand_pattern.search(text) and not any(char.isdigit() for char in text):
                    brands.add(text)
    
    return sorted(brands) if brands else []

def get_brands_by_artikul_emex(artikul, proxies=None):
    """Улучшенный парсер для Emex с повторными попытками"""
    encoded_artikul = quote(artikul)
    api_url = f"https://emex.ru/api/search/search?detailNum={encoded_artikul}&locationId=263&showAll=false&isHeaderSearch=true"
    
    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://emex.ru/products/{encoded_artikul}",
        "x-requested-with": "XMLHttpRequest",
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        log_debug(f"[API] Emex: попытка {attempt+1} для {artikul}")
        try:
            response = requests.get(
                api_url,
                headers=headers,
                proxies=proxies,
                timeout=10  # Увеличили таймаут
            )
            
            if response.status_code == 200:
                data = response.json()
                brands = set()
                
                # Обработка различных форматов ответа
                makes_list = data.get("searchResult", {}).get("makes", {}).get("list", [])
                for item in makes_list:
                    if "make" in item:
                        brand = item["make"]
                        if brand:
                            brands.add(brand)
                
                if not brands:
                    details_list = data.get("searchResult", {}).get("details", [])
                    for item in details_list:
                        if "make" in item and "name" in item["make"]:
                            brand = item["make"]["name"]
                            if brand:
                                brands.add(brand)
                
                if not brands:
                    brands_list = data.get("brands", [])
                    for brand in brands_list:
                        if isinstance(brand, str):
                            brands.add(brand)
                
                return sorted(brands)
            
            elif response.status_code == 429:
                wait_time = (attempt + 1) * 3
                log_debug(f"Emex rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                log_debug(f"[API] Emex: HTTP ошибка {response.status_code}")
        
        except Exception as e:
            log_debug(f"[API] Emex: ошибка: {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(2)
    
    return []  # Возвращаем пустой список после всех попыток