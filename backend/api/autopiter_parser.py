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
import subprocess
import signal
import os
import tempfile
import uuid

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT = 8  # Уменьшаем таймаут
SELENIUM_TIMEOUT = 15  # Уменьшаем таймаут для Selenium

def log_debug(message):
    print(f"[DEBUG] {message}")

def cleanup_chrome_processes():
    """Принудительно завершает зависшие процессы Chrome"""
    try:
        # Завершаем процессы chrome с разными вариантами имен
        subprocess.run(['pkill', '-f', 'chrome'], capture_output=True)
        subprocess.run(['pkill', '-f', 'chromedriver'], capture_output=True)
        subprocess.run(['pkill', '-f', 'google-chrome'], capture_output=True)
        subprocess.run(['pkill', '-f', 'chromium'], capture_output=True)
        
        # Дополнительная очистка через ps и kill
        try:
            ps_output = subprocess.check_output(['ps', 'aux'], text=True)
            for line in ps_output.split('\n'):
                if 'chrome' in line.lower() or 'chromedriver' in line.lower():
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        try:
                            subprocess.run(['kill', '-9', pid], capture_output=True)
                        except:
                            pass
        except:
            pass
        
        time.sleep(1)  # Уменьшаем время ожидания
    except Exception as e:
        log_debug(f"Error cleaning up Chrome processes: {e}")

def make_request(url, proxies=None, max_retries=2):  # Уменьшаем количество попыток
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
                wait_time = (attempt + 1) * 2  # Уменьшаем время ожидания
                log_debug(f"Rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                log_debug(f"Request failed (attempt {attempt + 1}): HTTP {response.status_code}")
        except Exception as e:
            log_debug(f"Request error (attempt {attempt + 1}): {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(0.5)  # Уменьшаем задержку
    
    return None

def get_brands_by_artikul(artikul, proxies=None):
    """Парсер для Autopiter.ru с оптимизацией"""
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
    
    # Метод 2: Парсинг JSON данных (только если первый метод не дал результатов)
    if not brands:
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
    
    # Метод 3: Резервный метод (только если предыдущие не дали результатов)
    if not brands:
        for tag in soup.select('span[title]'):
            txt = tag.get('title', '').strip()
            if txt and txt.lower() not in ['показать все', 'все']:
                brands.add(txt)
    
    return sorted(brands)

def get_brands_by_artikul_armtek(artikul, proxies=None):
    """Улучшенный парсер Armtek с оптимизацией ресурсов"""
    # 1. Сначала пробуем API
    api_brands = parse_armtek_api(artikul, proxies)
    if api_brands:
        return api_brands
    
    # 2. Пробуем простой HTTP запрос
    http_brands = parse_armtek_http(artikul, proxies)
    if http_brands:
        return http_brands
    
    # 3. Если API и HTTP не сработали, используем Selenium с улучшенными селекторами
    return parse_armtek_selenium(artikul)

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
            timeout=6  # Уменьшаем таймаут
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

def parse_armtek_selenium(artikul):
    """Парсинг через Selenium с оптимизацией ресурсов"""
    # Создаем уникальную временную директорию для каждого запроса
    temp_dir = tempfile.mkdtemp(prefix=f'chrome_{uuid.uuid4().hex[:8]}_')
    
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--user-data-dir=' + temp_dir)  # Уникальная директория
    options.add_argument('--window-size=1280,720')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-images')
    options.add_argument('--disable-javascript')
    options.add_argument('--remote-debugging-port=0')
    options.add_argument('--disable-web-security')
    options.add_argument('--allow-running-insecure-content')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-application-cache')
    options.add_argument('--disable-offline-load-stale-cache')
    options.add_argument('--disk-cache-size=0')
    options.add_argument('--media-cache-size=0')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-sync')
    options.add_argument('--disable-translate')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-component-extensions-with-background-pages')
    options.add_argument('--disable-background-mode')
    options.add_argument('--disable-client-side-phishing-detection')
    options.add_argument('--disable-hang-monitor')
    options.add_argument('--disable-prompt-on-repost')
    options.add_argument('--disable-domain-reliability')
    options.add_argument('--disable-ipc-flooding-protection')
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--disable-features=BlinkGenPropertyTrees')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-shared-memory')
    options.add_argument('--disable-software-rasterizer')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = None
    try:
        # Очищаем зависшие процессы перед запуском
        cleanup_chrome_processes()
        
        # Используем ChromeDriver из /usr/local/bin/ или системный
        try:
            service = Service('/usr/local/bin/chromedriver')
            driver = webdriver.Chrome(service=service, options=options)
        except:
            # Если не найден в /usr/local/bin/, используем системный
            driver = webdriver.Chrome(options=options)
        
        driver.set_page_load_timeout(SELENIUM_TIMEOUT)
        driver.implicitly_wait(3)  # Уменьшаем неявное ожидание
        
        driver.get(f"https://armtek.ru/search?text={quote(artikul)}")
        
        # Улучшенное ожидание с несколькими вариантами селекторов
        try:
            WebDriverWait(driver, 6).until(
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
            'span.font__body2.brand--selecting',
            '.product-card .brand-name',
            '.product-card__brand',
            '[itemprop="brand"]',
            '.catalog-item__brand'
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
        if driver:
            try:
                driver.quit()
            except:
                pass
        # Очищаем зависшие процессы после завершения
        cleanup_chrome_processes()
        # Удаляем временную директорию
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass

def parse_armtek_http(artikul, proxies=None):
    """Парсинг Armtek через простой HTTP запрос"""
    url = f"https://armtek.ru/search?text={quote(artikul)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            brands = set()
            
            # Ищем бренды в различных селекторах
            selectors = [
                'span.font__body2.brand--selecting',
                '.product-card .brand-name',
                '.product-card__brand',
                '[itemprop="brand"]',
                '.catalog-item__brand',
                '.brand-name',
                '.product-brand',
                'span[data-brand]',
                '.item-brand'
            ]
            
            for selector in selectors:
                for tag in soup.select(selector):
                    brand = tag.get_text(strip=True)
                    if brand and len(brand) > 2 and not brand.isdigit():
                        brands.add(brand)
            
            # Дополнительный поиск по тексту
            for tag in soup.find_all(['span', 'div', 'a']):
                text = tag.get_text(strip=True)
                if text and len(text) > 2 and len(text) < 50:
                    # Проверяем, не является ли текст брендом
                    if any(keyword in text.lower() for keyword in ['brand', 'бренд', 'производитель']):
                        continue
                    if text.isupper() or (text[0].isupper() and text[1:].islower()):
                        brands.add(text)
            
            return sorted(brands) if brands else []
            
    except Exception as e:
        log_debug(f"HTTP parsing error: {str(e)}")
        return []

def get_brands_by_artikul_emex(artikul, proxies=None):
    """Парсер для Emex с оптимизацией"""
    encoded_artikul = quote(artikul)
    api_url = f"https://emex.ru/api/search/search?detailNum={encoded_artikul}&locationId=263&showAll=false&isHeaderSearch=true"
    
    # Заголовки для имитации браузера
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://emex.ru/products/{encoded_artikul}/Hyundai%20%2F%20KIA",
        "x-requested-with": "XMLHttpRequest",
    }
    
    log_debug(f"[API] Emex: запрос к {api_url}")
    
    try:
        response = requests.get(api_url, headers=headers, proxies=proxies, timeout=6)  # Уменьшаем таймаут
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
        
        return sorted(brands)
    
    except Exception as e:
        log_debug(f"[API] Emex: ошибка: {str(e)}")
        return []