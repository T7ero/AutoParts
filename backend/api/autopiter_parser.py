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
            
            # Проверка на блокировку - только явные признаки
            if response.status_code == 403:
                log_debug(f"Запрос заблокирован (403) на {url}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                return None
            
            # Проверка на другие признаки блокировки - только явные
            blocking_indicators = [
                "access denied", "forbidden", "cloudflare", 
                "security check", "ddos protection", "blocked by"
            ]
            
            response_text_lower = response.text.lower()
            if any(indicator in response_text_lower for indicator in blocking_indicators):
                log_debug(f"Запрос заблокирован (индикаторы) на {url}")
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
                if response.status_code in [429, 503, 502]:
                    # Rate limiting или временная недоступность
                    wait_time = (attempt + 1) * 5
                    log_debug(f"Rate limiting, ждем {wait_time} секунд")
                    time.sleep(wait_time)
                    if attempt < max_retries - 1:
                        continue
                
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
    
    # Ищем бренды в различных элементах
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
        '.item .brand',
        '.product-info .brand',
        '.goods-info .brand'
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
    
    # Фильтрация брендов - убираем весь мусор
    filtered_brands = set()
    exclude_words = {
        'to content', 'zapros@autopiter.ru', 'автомасла', 'автопитер', 'ваз, газ, камаз', 
        'вакансии', 'возврат товара', 'восстановление пароля', 'все категории', 'вход', 
        'долгопрудный', 'доставка заказа', 'запчасти ваз, газ, камаз', 'запчасти для то', 
        'или выбрать другой удобный для вас способ', 'каталоги', 'каталоги запчастей', 
        'контакты', 'конфиденциальность', 'корзина', 'неоригинальные', 'неоригинальные запчасти', 
        'новости', 'о компании', 'оплата заказа', 'оплатить все товары можно', 'оптовикам', 
        'оптовым клиентам', 'оригинальные', 'оригинальные каталоги по vin', 'оферта', 
        'перейти в версию для смартфонов', 'помощь', 'помощь по сайту', 'поставщикам', 
        'производители:', 'реквизиты', 'рекомендуем', 'спецтехника', 'фильтры hebel kraft',
        'долгопрудныйвходкорзина', 'все категориикаталоги запчастей', 'офертаконфиденциальность',
        'производители:дизель', 'производители:jacjashisollersзапчастькитайрааз', 'jacjashisollersзапчастькитайрааз',
        'выбор armtekсортировать по:выбор armtek', 'мы используем cookies, чтобы сайт был лучше',
        'мы используем cookies, чтобы сайт был лучшехорошо', 'мы принимаем к оплате:', 'о компании',
        'оптовым покупателям', 'планировщик выгрузки', 'подбор', 'поиск по результату', 'покупателям',
        'правовая информация', 'программа лояльности', 'работа в компании', 'реклама на сайте',
        'сортировать по:выбор armtek', 'срок отгрузки', 'срок отгрузкидней', 'хорошо', 'цена',
        'ценаотдо', 'этна', 'отдо', 'заявку на подбор', 'vin или марке авто', 'аксессуары',
        'акции', 'в корзину', 'возврат', 'возможные замены', 'войти', 'выбор armtek', 'гараж',
        'гарантийная политика', 'главная', 'дней', 'доставка', 'инструмент', 'искомый товар',
        'как сделать заказ', 'каталог', 'лучшее предложение', 'магазины', 'мы в социальных сетях',
        'кислородный датчик', 'кислородный датчик, шт', 'датчик кислорода jac', 'запчасть', 'китай', 'рааз',
        'или выбрать другой удобный для\xa0вас способ', 'ка\x00талоги', 'оплата'
    }
    
    for brand in brands:
        brand_clean = brand.strip()
        brand_lower = brand_clean.lower()
        
        # Проверяем, что бренд не является "мусором"
        if (len(brand_clean) > 2 and len(brand_clean) < 50 and
            brand_lower not in exclude_words and
            not any(word in brand_lower for word in exclude_words) and
            not brand_lower.startswith('©') and
            not brand_lower.startswith('zapros') and
            not brand_lower.startswith('to content') and
            not brand_lower.startswith('автомасла') and
            not brand_lower.startswith('автопитер') and
            not brand_lower.startswith('ваз, газ, камаз') and
            not brand_lower.startswith('запчасти') and
            not brand_lower.startswith('каталоги') and
            not brand_lower.startswith('контакты') and
            not brand_lower.startswith('корзина') and
            not brand_lower.startswith('новости') and
            not brand_lower.startswith('о компании') and
            not brand_lower.startswith('оплата') and
            not brand_lower.startswith('помощь') and
            not brand_lower.startswith('производители:') and
            not brand_lower.startswith('реквизиты') and
            not brand_lower.startswith('спецтехника') and
            not brand_lower.startswith('фильтры') and
            not brand_lower.startswith('аксессуары') and
            not brand_lower.startswith('акции') and
            not brand_lower.startswith('в корзину') and
            not brand_lower.startswith('возврат') and
            not brand_lower.startswith('войти') and
            not brand_lower.startswith('выбор') and
            not brand_lower.startswith('гараж') and
            not brand_lower.startswith('главная') and
            not brand_lower.startswith('доставка') and
            not brand_lower.startswith('инструмент') and
            not brand_lower.startswith('как сделать') and
            not brand_lower.startswith('каталог') and
            not brand_lower.startswith('лучшее') and
            not brand_lower.startswith('магазины') and
            not brand_lower.startswith('мы в') and
            not brand_lower.startswith('мы используем') and
            not brand_lower.startswith('мы принимаем') and
            not brand_lower.startswith('оптовым') and
            not brand_lower.startswith('партнерам') and
            not brand_lower.startswith('планировщик') and
            not brand_lower.startswith('подбор') and
            not brand_lower.startswith('поиск') and
            not brand_lower.startswith('покупателям') and
            not brand_lower.startswith('правовая') and
            not brand_lower.startswith('программа') and
            not brand_lower.startswith('работа в') and
            not brand_lower.startswith('реклама') and
            not brand_lower.startswith('сортировать') and
            not brand_lower.startswith('срок') and
            not brand_lower.startswith('хорошо') and
            not brand_lower.startswith('цена') and
            not brand_lower.startswith('этна') and
            not brand_lower.startswith('отдо') and
            not brand_lower.startswith('заявку') and
            not brand_lower.startswith('vin или') and
            not brand_lower.startswith('искомый') and
            not brand_lower.startswith('кислородный') and
            not brand_lower.startswith('датчик') and
            not brand_lower.startswith('запчасть') and
            not brand_lower.startswith('китай') and
            not brand_lower.startswith('рааз') and
            not brand_lower.startswith('или выбрать') and
            not brand_lower.startswith('каталоги')):
            filtered_brands.add(brand_clean)
    
    return sorted(filtered_brands) if filtered_brands else []

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
        
        # Фильтрация брендов - убираем "мусор", но оставляем все бренды
        filtered_brands = set()
        exclude_words = {
            'telegram', 'whatsapp', 'аккумуляторы', 'масла', 'фильтры', 'тормозные колодки',
            'амортизаторы', 'подшипники', 'ремни', 'свечи', 'лампы', 'стеклоочистители',
            'дворники', 'зеркала', 'фары', 'фонари', 'сигналы', 'датчики', 'насосы',
            'компрессоры', 'радиаторы', 'вентиляторы', 'термостаты', 'терморегуляторы',
            'датчики температуры', 'датчики давления', 'датчики кислорода', 'датчики детонации',
            'датчики скорости', 'датчики положения', 'датчики уровня', 'датчики расхода',
            'датчики вибрации', 'датчики шума', 'вход', 'корзина', 'каталоги', 'контакты', 
            'новости', 'помощь', 'оптовикам', 'поставщикам', 'вакансии', 'все категории', 
            'долгопрудный', 'москва', 'россия', 'китай', 'запчасть', 'запчасти', 
            'оригинальные', 'неоригинальные', 'восстановление пароля', 'конфиденциальность', 
            'оферта', 'оплата заказа', 'доставка заказа', 'возврат товара', 'to content', 
            'zapros@autopiter.ru', '© ооо «автопитер»', 'ваз, газ, камаз', 
            'запчасти ваз, газ, камаз', 'запчасти для то', 'или выбрать другой удобный для вас способ',
            'каталоги запчастей', 'неоригинальные запчасти', 'оплатить все товары можно',
            'оптовым клиентам', 'оригинальные каталоги по vin', 'перейти в версию для смартфонов',
            'помощь по сайту', 'россия, москва, ул. скотопрогонная, 35 стр. 3', 'спецтехника',
            'фильтры hebel kraft', 'герметик силиконовый mannol', 'кнопка 2114-15, евро кнопка',
            'кнопка ваз-2115, евро кнопка', 'кольцо уплотнительное ступицы toyota',
            'лист сзап l1 1,2 задний', 'масло для компрессоров vdl 100 fubag',
            'мотор омывателя 24v', 'мотор омывателя камаз 24v', 'насос омывателя маз,камаз евро',
            'переключатель стеклоочистителя', 'профи-75 белак', 'ремкомплект гидроцилиндра',
            'рессора чмзап', 'русский мастер ps-10 рм', 'русский мастер рмм',
            'стопорное кольцо чмзап', 'показать все', 'все', 'автомасла', 'автопитер',
            'armtek', 'new', 'аксессуары', 'акции', 'в корзину', 'возврат', 'возможные замены',
            'войти', 'выбор armtek', 'гараж', 'гарантийная политика', 'главная', 'дней',
            'доставка', 'инструмент', 'искомый товар', 'как сделать заказ', 'каталог',
            'лучшее предложение', 'магазины', 'мы в социальных сетях', 'мы используем cookies',
            'мы принимаем к оплате:', 'о компании', 'оптовым покупателям', 'партнерам',
            'планировщик выгрузки', 'подбор', 'поиск по результату', 'покупателям',
            'правовая информация', 'программа лояльности', 'работа в компании', 'реклама на сайте',
            'сортировать по:выбор armtek', 'срок отгрузки', 'хорошо', 'цена', 'этна', 'отдо',
            'заявку на подбор', 'vin или марке авто', 'кислородный датчик', 'датчик кислорода jac',
            'запчасть', 'китай', 'рааз', 'jacjashisollersзапчастькитайрааз', 'производители:дизель',
            'производители:jacjashisollersзапчастькитайрааз', 'долгопрудныйвходкорзина',
            'все категориикаталоги запчастей', 'офертаконфиденциальность', 'выбор armtekсортировать по:выбор armtek',
            'мы используем cookies, чтобы сайт был лучше', 'мы используем cookies, чтобы сайт был лучшехорошо',
            'срок отгрузкидней', 'ценаотдо', 'кислородный датчик, шт', 'оплата'
        }
        
        for brand in brands:
            brand_clean = brand.strip()
            brand_lower = brand_clean.lower()
            
            # Проверяем, что бренд не является "мусором"
            if (len(brand_clean) > 2 and len(brand_clean) < 50 and
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
                not brand_lower.startswith('стопорное') and
                not brand_lower.startswith('armtek') and
                not brand_lower.startswith('new') and
                not brand_lower.startswith('аксессуары') and
                not brand_lower.startswith('акции') and
                not brand_lower.startswith('в корзину') and
                not brand_lower.startswith('возврат') and
                not brand_lower.startswith('возможные') and
                not brand_lower.startswith('войти') and
                not brand_lower.startswith('выбор') and
                not brand_lower.startswith('гараж') and
                not brand_lower.startswith('гарантийная') and
                not brand_lower.startswith('главная') and
                not brand_lower.startswith('дней') and
                not brand_lower.startswith('доставка') and
                not brand_lower.startswith('инструмент') and
                not brand_lower.startswith('искомый') and
                not brand_lower.startswith('как сделать') and
                not brand_lower.startswith('каталог') and
                not brand_lower.startswith('лучшее') and
                not brand_lower.startswith('магазины') and
                not brand_lower.startswith('мы в') and
                not brand_lower.startswith('мы используем') and
                not brand_lower.startswith('мы принимаем') and
                not brand_lower.startswith('оптовым') and
                not brand_lower.startswith('партнерам') and
                not brand_lower.startswith('планировщик') and
                not brand_lower.startswith('подбор') and
                not brand_lower.startswith('поиск') and
                not brand_lower.startswith('покупателям') and
                not brand_lower.startswith('правовая') and
                not brand_lower.startswith('программа') and
                not brand_lower.startswith('работа в') and
                not brand_lower.startswith('реклама') and
                not brand_lower.startswith('сортировать') and
                not brand_lower.startswith('срок') and
                not brand_lower.startswith('хорошо') and
                not brand_lower.startswith('цена') and
                not brand_lower.startswith('этна') and
                not brand_lower.startswith('отдо') and
                not brand_lower.startswith('заявку') and
                not brand_lower.startswith('vin или') and
                not brand_lower.startswith('кислородный') and
                not brand_lower.startswith('датчик') and
                not brand_lower.startswith('запчасть') and
                not brand_lower.startswith('китай') and
                not brand_lower.startswith('рааз') and
                not brand_lower.startswith('оплата')):
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