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
import random
from typing import List, Dict, Optional, Tuple

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}
TIMEOUT = 20
SELENIUM_TIMEOUT = 30

# Кеширование
REQUEST_CACHE = {}
CACHE_EXPIRATION = 600
FAILED_REQUESTS_CACHE = {}

# Глобальная переменная для хранения прокси
PROXY_LIST = []
PROXY_INDEX = 0

def log_debug(message):
    print(f"[DEBUG] {message}")

def load_proxies_from_file(file_path: str = "proxies.txt") -> List[str]:
    """Загружает список прокси из файла"""
    global PROXY_LIST
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                PROXY_LIST = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            log_debug(f"Загружено {len(PROXY_LIST)} прокси")
        else:
            log_debug(f"Файл прокси {file_path} не найден")
    except Exception as e:
        log_debug(f"Ошибка загрузки прокси: {e}")
    return PROXY_LIST

def get_next_proxy() -> Optional[Dict[str, str]]:
    """Возвращает следующий прокси из списка"""
    global PROXY_INDEX, PROXY_LIST
    
    if not PROXY_LIST:
        load_proxies_from_file()
    
    if not PROXY_LIST:
        return None
    
    proxy_str = PROXY_LIST[PROXY_INDEX % len(PROXY_LIST)]
    PROXY_INDEX += 1
    
    try:
        # Формат: ip:port@login:password
        if '@' in proxy_str:
            auth_part, proxy_part = proxy_str.split('@')
            login, password = auth_part.split(':')
            ip, port = proxy_part.split(':')
            
            proxy_dict = {
                'http': f'http://{login}:{password}@{ip}:{port}',
                'https': f'http://{login}:{password}@{ip}:{port}'
            }
        else:
            # Формат: ip:port
            ip, port = proxy_str.split(':')
            proxy_dict = {
                'http': f'http://{ip}:{port}',
                'https': f'http://{ip}:{port}'
            }
        
        return proxy_dict
    except Exception as e:
        log_debug(f"Ошибка парсинга прокси {proxy_str}: {e}")
        return None

def cleanup_chrome_processes():
    """Принудительно завершает зависшие процессы Chrome"""
    try:
        kill_commands = [
            ['pkill', '-9', '-f', 'chrome'],
            ['pkill', '-9', '-f', 'chromedriver'],
            ['pkill', '-9', '-f', 'google-chrome'],
            ['pkill', '-9', '-f', 'chromium'],
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
        
        time.sleep(1)
    except Exception as e:
        log_debug(f"Error cleaning up Chrome processes: {e}")

def is_site_available(url: str, proxies: Optional[Dict] = None) -> bool:
    """Проверяет доступность сайта"""
    try:
        response = requests.head(url, timeout=10, proxies=proxies, headers=HEADERS)
        return response.status_code < 500
    except:
        return False

def make_request(url: str, proxies: Optional[Dict] = None, max_retries: int = 3, cache_key: Optional[str] = None) -> Optional[requests.Response]:
    """Улучшенный запрос с кешированием и прокси"""
    # Проверка кеша ошибок
    if url in FAILED_REQUESTS_CACHE and FAILED_REQUESTS_CACHE[url] > time.time() - 3600:
        log_debug(f"Запрос к {url} пропущен из-за предыдущих ошибок")
        return None
        
    # Проверка кеша успешных запросов
    if cache_key and cache_key in REQUEST_CACHE:
        cached_time, response = REQUEST_CACHE[cache_key]
        if time.time() - cached_time < CACHE_EXPIRATION:
            return response
    
    for attempt in range(max_retries):
        try:
            # Упрощенная логика: сначала без прокси, потом с прокси только если есть
            if attempt == 0:
                current_proxies = None
                log_debug(f"Попытка {attempt+1} без прокси для {url}")
            else:
                current_proxies = proxies
                log_debug(f"Попытка {attempt+1} с прокси для {url}")
            
            response = requests.get(
                url,
                headers=HEADERS,
                proxies=current_proxies,
                timeout=TIMEOUT
            )
            
            # Проверка на CAPTCHA
            if "captcha" in response.text.lower():
                log_debug(f"Обнаружена CAPTCHA на {url}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return None
            
            # Проверка на блокировку
            if response.status_code == 403 or "blocked" in response.text.lower():
                log_debug(f"Запрос заблокирован на {url}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                return None
            
            if response.status_code == 200:
                # Кешируем успешный ответ
                if cache_key:
                    REQUEST_CACHE[cache_key] = (time.time(), response)
                return response
            else:
                log_debug(f"HTTP {response.status_code} для {url}")
                
        except requests.exceptions.Timeout:
            log_debug(f"Таймаут для {url} (попытка {attempt+1})")
        except requests.exceptions.ProxyError:
            log_debug(f"Ошибка прокси для {url} (попытка {attempt+1})")
        except Exception as e:
            log_debug(f"Ошибка запроса к {url}: {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(2)
    
    FAILED_REQUESTS_CACHE[url] = time.time()
    return None

def get_brands_by_artikul(artikul: str, proxies: Optional[Dict] = None) -> List[str]:
    """Улучшенный парсер для Autopiter.ru с правильным извлечением брендов"""
    url = f"https://autopiter.ru/goods/{artikul}"
    log_debug(f"Autopiter: запрос к {url}")
    
    # Увеличиваем количество попыток для Autopiter
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = make_request(url, proxies, cache_key=f"autopiter_{artikul}")
            if response:
                break
            else:
                log_debug(f"Autopiter: попытка {attempt+1} не удалась")
                if attempt < max_retries - 1:
                    time.sleep(2)
        except Exception as e:
            log_debug(f"Autopiter: ошибка попытки {attempt+1}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    if not response:
        log_debug("Autopiter: не удалось получить данные после всех попыток")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    brands = set()
    
    # Попытка 1: Парсинг таблицы с товарами
    for row in soup.select('tr[data-qa-id="offer-row"]'):
        brand_tag = row.select_one('span[data-qa-id="brand-name"]')
        if brand_tag:
            brand = brand_tag.get_text(strip=True)
            if brand and brand.lower() not in ['показать все', 'все', 'автомасла', 'автопитер']:
                brands.add(brand)
    
    # Попытка 2: Парсинг JSON в скрипте
    if not brands:
        script_tags = soup.find_all('script')
        for script in script_tags:
            if script.string and 'window.__NUXT__' in script.string:
                try:
                    script_text = script.string
                    json_match = re.search(r'window\.__NUXT__\s*=\s*(.*?});', script_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                        data = json.loads(json_str)
                        
                        # Ищем бренды в структуре данных
                        if 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
                            offers = data['data'][0].get('offers', {}).get('items', [])
                            for offer in offers:
                                if isinstance(offer, dict):
                                    brand_info = offer.get('brand', {})
                                    if isinstance(brand_info, dict):
                                        brand = brand_info.get('name')
                                        if brand and brand.lower() not in ['показать все', 'все']:
                                            brands.add(brand)
                except Exception as e:
                    log_debug(f"Autopiter JSON error: {str(e)}")
    
    # Попытка 3: Парсинг атрибутов title и data-атрибутов
    if not brands:
        for tag in soup.select('span[title], div[title], a[title]'):
            txt = tag.get('title', '').strip()
            if txt and txt.lower() not in ['показать все', 'все', 'автомасла', 'автопитер']:
                brands.add(txt)
    
    # Попытка 4: Поиск по data-атрибутам
    if not brands:
        for tag in soup.select('[data-brand], [data-vendor], [data-manufacturer]'):
            brand = tag.get('data-brand') or tag.get('data-vendor') or tag.get('data-manufacturer')
            if brand and brand.lower() not in ['показать все', 'все']:
                brands.add(brand)
    
    # Попытка 5: Поиск по классам, содержащим "brand"
    if not brands:
        for tag in soup.select('.brand, .vendor, .manufacturer, [class*="brand"], [class*="vendor"]'):
            text = tag.get_text(strip=True)
            if text and len(text) > 2 and len(text) < 50:
                if text.lower() not in ['показать все', 'все', 'автомасла', 'автопитер', 'вход', 'корзина']:
                    brands.add(text)
    
    # Фильтрация результатов - убираем нерелевантные бренды
    filtered_brands = set()
    exclude_words = {
        'автомасла', 'автопитер', 'вход', 'корзина', 'каталоги', 'контакты', 
        'новости', 'помощь', 'оптовикам', 'поставщикам', 'вакансии',
        'все категории', 'долгопрудный', 'москва', 'россия', 'китай',
        'запчасть', 'запчасти', 'оригинальные', 'неоригинальные',
        'восстановление пароля', 'конфиденциальность', 'оферта',
        'оплата заказа', 'доставка заказа', 'возврат товара',
        'to content', 'zapros@autopiter.ru', '© ооо «автопитер»',
        'ваз, газ, камаз', 'запчасти ваз, газ, камаз', 'запчасти для то',
        'или выбрать другой удобный для вас способ', 'каталоги запчастей',
        'неоригинальные запчасти', 'оплатить все товары можно',
        'оптовым клиентам', 'оригинальные каталоги по vin',
        'перейти в версию для смартфонов', 'помощь по сайту',
        'россия, москва, ул. скотопрогонная, 35 стр. 3', 'спецтехника',
        'фильтры hebel kraft', 'герметик силиконовый mannol',
        'кнопка 2114-15, евро кнопка', 'кнопка ваз-2115, евро кнопка',
        'кольцо уплотнительное ступицы toyota', 'лист сзап l1 1,2 задний',
        'масло для компрессоров vdl 100 fubag', 'мотор омывателя 24v',
        'мотор омывателя камаз 24v', 'насос омывателя маз,камаз евро',
        'переключатель стеклоочистителя', 'профи-75 белак',
        'ремкомплект гидроцилиндра', 'рессора чмзап',
        'русский мастер ps-10 рм', 'русский мастер рмм',
        'стопорное кольцо чмзап'
    }
    
    for brand in brands:
        brand_lower = brand.lower()
        if (len(brand) > 2 and len(brand) < 50 and 
            brand_lower not in exclude_words and
            not any(word in brand_lower for word in exclude_words) and
            not brand_lower.startswith('99') and  # Исключаем артикулы
            not brand_lower.startswith('zapros') and
            not brand_lower.startswith('©') and
            not brand_lower.startswith('mannol') and
            not brand_lower.startswith('герметик') and
            not brand_lower.startswith('кнопка') and
            not brand_lower.startswith('кольцо') and
            not brand_lower.startswith('лист') and
            not brand_lower.startswith('масло') and
            not brand_lower.startswith('мотор') and
            not brand_lower.startswith('насос') and
            not brand_lower.startswith('переключатель') and
            not brand_lower.startswith('профи') and
            not brand_lower.startswith('ремкомплект') and
            not brand_lower.startswith('рессора') and
            not brand_lower.startswith('русский мастер') and
            not brand_lower.startswith('стопорное')):
            filtered_brands.add(brand)
    
    return sorted(filtered_brands)

def get_brands_by_artikul_armtek(artikul: str, proxies: Optional[Dict] = None) -> List[str]:
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

def parse_armtek_api(artikul: str, proxies: Optional[Dict] = None) -> List[str]:
    """Попытка получить данные через API Armtek"""
    url = f"https://armtek.ru/api/search?query={quote(artikul)}&limit=50"
    log_debug(f"Armtek API: запрос к {url}")
    
    try:
        current_proxies = proxies or get_next_proxy()
        response = requests.get(
            url,
            headers={
                "User-Agent": HEADERS["User-Agent"],
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest"
            },
            proxies=current_proxies,
            timeout=15
        )
        
        if response.status_code == 200:
            try:
                data = response.json()
                brands = set()
                
                # Обработка различных форматов ответа
                if isinstance(data, dict):
                    items = data.get('items', []) or data.get('products', []) or data.get('results', [])
                    for item in items:
                        if isinstance(item, dict):
                            brand = item.get('brand') or item.get('manufacturer') or item.get('vendor')
                            if isinstance(brand, dict):
                                brand = brand.get('name')
                            if brand and isinstance(brand, str):
                                brands.add(brand)
                
                return sorted(brands)
            except json.JSONDecodeError:
                log_debug("Armtek API: ошибка декодирования JSON")
        else:
            log_debug(f"Armtek API: HTTP {response.status_code}")
            
    except Exception as e:
        log_debug(f"Armtek API: ошибка {str(e)}")
    
    return []

def parse_armtek_selenium(artikul: str) -> List[str]:
    """Парсинг Armtek через Selenium с уникальными user-data-dir"""
    log_debug(f"Armtek Selenium: запуск для артикула {artikul}")
    
    # Создаем уникальную временную директорию для каждого запуска
    temp_dir = tempfile.mkdtemp(prefix=f"chrome_armtek_{uuid.uuid4().hex[:8]}_")
    
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
    options.add_argument(f'--user-data-dir={temp_dir}')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--disable-ipc-flooding-protection')
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
        
        url = f"https://armtek.ru/search?text={quote(artikul)}"
        log_debug(f"Armtek Selenium: загрузка страницы {url}")
        driver.get(url)
        
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".product-card, .catalog-item, [data-testid='product-item'], .item")
                )
            )
            time.sleep(2)
        except Exception as e:
            log_debug(f"Armtek Selenium: не дождались результатов: {str(e)}")
        
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
            '.vendor-title',
            '.product-item .brand',
            '.item .brand'
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
        
        # Фильтрация брендов - только разрешенные бренды
        allowed_brands = {'PAZ', 'PRC', 'РФ'}
        filtered_brands = set()
        
        for brand in brands:
            brand_clean = brand.strip()
            if brand_clean in allowed_brands:
                filtered_brands.add(brand_clean)
        
        return sorted(filtered_brands) if filtered_brands else []
        
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
        time.sleep(1)
        
        # Удаляем временную директорию
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass

def parse_armtek_http(artikul: str, proxies: Optional[Dict] = None) -> List[str]:
    """Парсинг Armtek через HTTP запрос с улучшенной обработкой"""
    url = f"https://armtek.ru/search?text={quote(artikul)}"
    log_debug(f"Armtek HTTP: запрос к {url}")
    
    response = make_request(url, proxies, cache_key=f"armtek_http_{artikul}")
    if not response:
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    brands = set()
    
    # Поиск брендов в структурированных данных
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
    
    # Поиск по CSS селекторам
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
    
    for selector in brand_selectors:
        for tag in soup.select(selector):
            brand = tag.get_text(strip=True)
            if brand and len(brand) > 2 and not brand.isdigit():
                brands.add(brand)
    
    # Поиск по тексту
    if not brands:
        brand_pattern = re.compile(r'(бренд|производитель|brand|manufacturer)', re.IGNORECASE)
        for tag in soup.find_all(['span', 'div', 'a', 'h3']):
            text = tag.get_text(strip=True)
            if text and len(text) > 2 and len(text) < 50:
                if not brand_pattern.search(text) and not any(char.isdigit() for char in text):
                    brands.add(text)
    
    return sorted(brands) if brands else []

def get_brands_by_artikul_emex(artikul: str, proxies: Optional[Dict] = None) -> List[str]:
    """Улучшенный парсер для Emex с обработкой таймаутов и прокси"""
    encoded_artikul = quote(artikul)
    api_url = f"https://emex.ru/api/search/search?detailNum={encoded_artikul}&locationId=263&showAll=false&isHeaderSearch=true"
    
    headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://emex.ru/products/{encoded_artikul}",
        "x-requested-with": "XMLHttpRequest",
    }
    
    max_retries = 3  # Уменьшаем количество попыток
    for attempt in range(max_retries):
        log_debug(f"[API] Emex: попытка {attempt+1} для {artikul}")
        try:
            # Упрощенная логика прокси
            current_proxies = None if attempt == 0 else proxies
            
            response = requests.get(
                api_url,
                headers=headers,
                proxies=current_proxies,
                timeout=15  # Уменьшаем таймаут
            )
            
            if response.status_code == 200:
                try:
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
                except json.JSONDecodeError:
                    log_debug("Emex API: ошибка декодирования JSON")
            elif response.status_code == 429:
                wait_time = (attempt + 1) * 5
                log_debug(f"Emex rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                log_debug(f"[API] Emex: HTTP ошибка {response.status_code}")
        except requests.exceptions.Timeout:
            log_debug(f"[API] Emex: таймаут подключения (попытка {attempt+1})")
        except requests.exceptions.ProxyError:
            log_debug(f"[API] Emex: ошибка прокси (попытка {attempt+1})")
        except Exception as e:
            log_debug(f"[API] Emex: ошибка: {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(2)
    
    log_debug(f"Emex: все попытки для {artikul} завершились ошибкой")
    return []

# Инициализация прокси при импорте модуля
load_proxies_from_file()