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
from webdriver_manager.chrome import ChromeDriverManager
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
TIMEOUT = 30  # Увеличенный таймаут
SELENIUM_TIMEOUT = 40  # Увеличенный таймаут для Selenium

# Кеширование
REQUEST_CACHE = {}
CACHE_EXPIRATION = 600  # 10 минут
FAILED_REQUESTS_CACHE = {}  # Для хранения неудачных запросов

def log_debug(message):
    print(f"[DEBUG] {message}")

def cleanup_chrome_processes():
    """Принудительно завершает зависшие процессы Chrome"""
    try:
        subprocess.run(['pkill', '-9', '-f', 'chrome'], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL)
        subprocess.run(['pkill', '-9', '-f', 'chromedriver'],
                      stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL)
        time.sleep(2)
    except:
        pass

def is_site_available(url):
    """Проверяет доступность сайта"""
    try:
        response = requests.head(url, timeout=10, headers=HEADERS)
        return response.status_code < 500
    except:
        return False

def make_request(url, proxies=None, max_retries=3, cache_key=None):
    """Улучшенный запрос с кешированием, проверкой доступности и обработкой ошибок"""
    # Проверка кеша ошибок
    if url in FAILED_REQUESTS_CACHE and FAILED_REQUESTS_CACHE[url] > time.time() - 3600:
        log_debug(f"Запрос к {url} пропущен из-за предыдущих ошибок")
        return None
        
    # Проверка кеша успешных запросов
    if cache_key and cache_key in REQUEST_CACHE:
        cached_time, response = REQUEST_CACHE[cache_key]
        if time.time() - cached_time < CACHE_EXPIRATION:
            return response
    
    # Проверка доступности сайта
    if not is_site_available(url):
        log_debug(f"Сайт {url} недоступен")
        FAILED_REQUESTS_CACHE[url] = time.time()
        return None
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                proxies=proxies,
                timeout=TIMEOUT
            )
            
            # Проверка на CAPTCHA
            if "captcha" in response.text.lower():
                log_debug(f"Обнаружена CAPTCHA на {url}")
                FAILED_REQUESTS_CACHE[url] = time.time()
                return None
                
            if response.status_code == 200:
                # Сохраняем в кеш
                if cache_key:
                    REQUEST_CACHE[cache_key] = (time.time(), response)
                return response
            elif response.status_code == 429:
                wait_time = (attempt + 1) * 10  # Увеличенное время ожидания
                log_debug(f"Rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                log_debug(f"Request failed (attempt {attempt + 1}): HTTP {response.status_code}")
                FAILED_REQUESTS_CACHE[url] = time.time()
        except Exception as e:
            log_debug(f"Request error (attempt {attempt + 1}): {str(e)}")
            FAILED_REQUESTS_CACHE[url] = time.time()
        
        if attempt < max_retries - 1:
            time.sleep(5)  # Увеличенное время между попытками
    
    return None

def get_brands_by_artikul(artikul, proxies=None):
    """Парсер для Autopiter.ru с улучшенной обработкой ошибок"""
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
    
    return sorted(brands) if brands else []

def get_brands_by_artikul_armtek(artikul, proxies=None):
    """Улучшенный парсер Armtek с полным логированием"""
    log_debug(f"Armtek: начало обработки артикула {artikul}")
    
    # 1. Пробуем API
    api_brands = parse_armtek_api(artikul, proxies)
    if api_brands:
        log_debug(f"Armtek API: найдены бренды {api_brands}")
        return api_brands
    
    # 2. Пробуем HTTP запрос
    http_brands = parse_armtek_http(artikul, proxies)
    if http_brands:
        log_debug(f"Armtek HTTP: найдены бренды {http_brands}")
        return http_brands
    
    # 3. Если API и HTTP не сработали, используем Selenium
    selenium_brands = parse_armtek_selenium(artikul)
    log_debug(f"Armtek Selenium: найдены бренды {selenium_brands}")
    return selenium_brands

def parse_armtek_api(artikul, proxies=None):
    """Попытка получить данные через API Armtek"""
    url = f"https://armtek.ru/api/search?query={quote(artikul)}&limit=50"
    log_debug(f"Armtek API: запрос к {url}")
    
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": HEADERS["User-Agent"],
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest"
            },
            proxies=proxies,
            timeout=20
        )
        
        if response.status_code == 200:
            try:
                # Проверка на валидный JSON
                if not response.text.strip():
                    log_debug("Armtek API: пустой ответ")
                    return None
                    
                data = response.json()
                brands = set()
                
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
            except json.JSONDecodeError as e:
                log_debug(f"Armtek API: ошибка декодирования JSON: {str(e)}")
                log_debug(f"Response text: {response.text[:200]}...")
                return None
        else:
            log_debug(f"Armtek API: HTTP ошибка {response.status_code}")
            return None
    except Exception as e:
        log_debug(f"Armtek API error: {str(e)}")
        return None

def parse_armtek_selenium(artikul):
    """Парсинг Armtek через Selenium с улучшенной обработкой ошибок"""
    log_debug(f"Armtek Selenium: запуск для артикула {artikul}")
    
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
    
    # Уникальный user-data-dir для каждой сессии
    user_data_dir = os.path.join(tempfile.gettempdir(), f"chrome_{uuid.uuid4().hex}")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = None
    try:
        cleanup_chrome_processes()
        time.sleep(2)
        
        try:
            # Используем webdriver-manager для автоматического управления драйвером
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            log_debug(f"Chrome driver init error: {str(e)}")
            try:
                driver = webdriver.Chrome(options=options)
            except Exception as e:
                log_debug(f"Fallback Chrome init error: {str(e)}")
                return []
        
        driver.set_page_load_timeout(SELENIUM_TIMEOUT)
        driver.set_script_timeout(SELENIUM_TIMEOUT)
        driver.implicitly_wait(10)
        
        url = f"https://armtek.ru/search?text={quote(artikul)}"
        log_debug(f"Armtek Selenium: загрузка страницы {url}")
        driver.get(url)
        
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".product-card, .catalog-item, [data-testid='product-item']")
                )
            )
            time.sleep(3)  # Дополнительное время для стабилизации
        except Exception as e:
            log_debug(f"Armtek Selenium: не дождались результатов: {str(e)}")
            # Пробуем продолжить даже если не дождались элементов
        
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
        
        return sorted(brands) if brands else []
        
    except Exception as e:
        log_debug(f"Armtek Selenium error: {str(e)}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        cleanup_chrome_processes()
        time.sleep(2)
        # Удаляем временный user-data-dir
        try:
            if os.path.exists(user_data_dir):
                os.system(f"rm -rf {user_data_dir}")
        except:
            pass

def parse_armtek_http(artikul, proxies=None):
    """Парсинг Armtek через HTTP запрос с улучшенной обработкой"""
    url = f"https://armtek.ru/search?text={quote(artikul)}"
    log_debug(f"Armtek HTTP: запрос к {url}")
    
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
    
    return sorted(brands) if brands else []

def get_brands_by_artikul_emex(artikul, proxies=None):
    """Улучшенный парсер для Emex с обработкой таймаутов и прокси"""
    if not is_site_available("https://emex.ru"):
        log_debug("Emex недоступен, пропускаем")
        return []
    
    encoded_artikul = quote(artikul)
    api_url = f"https://emex.ru/api/search/search?detailNum={encoded_artikul}&locationId=263&showAll=false&isHeaderSearch=true"
    
    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://emex.ru/products/{encoded_artikul}",
        "x-requested-with": "XMLHttpRequest",
    }
    
    max_retries = 2  # Уменьшено количество попыток
    for attempt in range(max_retries):
        log_debug(f"[API] Emex: попытка {attempt+1} для {artikul}")
        try:
            response = requests.get(
                api_url,
                headers=headers,
                proxies=proxies,
                timeout=20
            )
            
            if response.status_code == 200:
                try:
                    # Проверка на валидный JSON
                    if not response.text.strip():
                        log_debug("Emex API: пустой ответ")
                        return []
                        
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
                    
                    return sorted(brands) if brands else []
                except json.JSONDecodeError as e:
                    log_debug(f"Emex API: ошибка декодирования JSON: {str(e)}")
                    log_debug(f"Response text: {response.text[:200]}...")
                    return []
            elif response.status_code == 429:
                log_debug("Emex API: Rate limited, пропускаем")
                return []
            else:
                log_debug(f"[API] Emex: HTTP ошибка {response.status_code}")
                return []
        except requests.exceptions.Timeout:
            log_debug(f"[API] Emex: таймаут подключения (попытка {attempt+1})")
        except Exception as e:
            log_debug(f"[API] Emex: ошибка: {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(5)
    
    log_debug(f"Emex: все попытки для {artikul} завершились ошибкой")
    return []