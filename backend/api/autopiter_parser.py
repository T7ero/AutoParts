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
from selenium.common.exceptions import TimeoutException

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
# Уменьшаем таймауты для ускорения работы
TIMEOUT = 10  # Уменьшаем с 15 до 10 секунд
SELENIUM_TIMEOUT = 15  # Уменьшаем с 20 до 15 секунд
PAGE_LOAD_TIMEOUT = 10  # Уменьшаем с 15 до 10 секунд

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

def make_request(url: str, proxy: Optional[str] = None, max_retries: int = 2) -> Optional[requests.Response]:
    """Выполняет HTTP запрос с поддержкой прокси и повторными попытками"""
    session = requests.Session()
    
    # Настройка прокси
    if proxy:
        try:
            if '@' in proxy:
                # Формат: ip:port@login:password
                proxy_parts = proxy.split('@')
                proxy_url = proxy_parts[0]
                auth_parts = proxy_parts[1].split(':')
                username = auth_parts[0]
                password = auth_parts[1]
                
                proxy_dict = {
                    'http': f'http://{username}:{password}@{proxy_url}',
                    'https': f'http://{username}:{password}@{proxy_url}'
                }
            else:
                # Формат: ip:port
                proxy_dict = {
                    'http': f'http://{proxy}',
                    'https': f'http://{proxy}'
                }
            
            session.proxies.update(proxy_dict)
            log_debug(f"Используется прокси: {proxy}")
        except Exception as e:
            log_debug(f"Ошибка настройки прокси {proxy}: {str(e)}")
    
    # Настройка заголовков
    session.headers.update(HEADERS)
    
    for attempt in range(max_retries):
        try:
            response = session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            return response
        except requests.exceptions.ProxyError as e:
            log_debug(f"Ошибка прокси {proxy}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            else:
                raise
        except requests.exceptions.RequestException as e:
            log_debug(f"Ошибка запроса (попытка {attempt + 1}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            else:
                raise
    
    return None

def get_brands_by_artikul(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """Получает бренды с Autopiter по артикулу"""
    try:
        url = f"https://autopiter.ru/goods/{artikul}"
        log_debug(f"Autopiter: запрос к {url}")
        
        # Сначала пробуем без прокси
        try:
            log_debug(f"Попытка 1 без прокси для {url}")
            response = make_request(url, None, max_retries=1)
            if response and response.status_code == 200:
                return parse_autopiter_response(response.text, artikul)
        except Exception as e:
            log_debug(f"Ошибка без прокси: {str(e)}")
        
        # Если не получилось, пробуем с прокси
        if proxy:
            try:
                log_debug(f"Попытка 2 с прокси для {url}")
                response = make_request(url, proxy, max_retries=1)
                if response and response.status_code == 200:
                    return parse_autopiter_response(response.text, artikul)
            except Exception as e:
                log_debug(f"Ошибка с прокси: {str(e)}")
        
        return []
        
    except Exception as e:
        log_debug(f"Ошибка Autopiter для {artikul}: {str(e)}")
        return []

def parse_autopiter_response(html_content: str, artikul: str) -> List[str]:
    """Парсит ответ от Autopiter и извлекает бренды"""
    soup = BeautifulSoup(html_content, "html.parser")
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
        'или выбрать другой удобный для\xa0вас способ', 'ка\x00талоги', 'оплата',
        # Новые исключения для Autopiter
        'ки\x00тай', 'к\x00итай', 'товары на autopiter market', 'переключатели подрулевые, в сборе',
        'переключатели подрулевые в сборе', 'переключатели подрулевые', 'подрулевые', 'в сборе',
        'рессорный палец', 'палец', 'рессорный', 'автокомпонент', 'россия', 'камаз', 'автокомпонент плюс',
        'автодеталь', 'четырнадцать', 'автокомпонент плюс', 'автодеталь', 'четырнадцать',
        'motul.', 'motul', 'faw', 'foton', 'hande axle', 'leo trade', 'onashi', 'prc', 'shaanxi/shacman',
        'sinotruk', 'sitrak', 'weichai', 'zg.link', 'автокомпонент', 'камаз', 'рессорный палец', 'россия',
        'ast', 'ast silver', 'ast smart', 'autotech', 'avto-tech', 'component', 'createk', 'howo',
        'kolbenschmidt', 'leo', 'peugeot-citroen', 'prc', 'shaanxi/shacman', 'sinotruk', 'sitrak',
        'автокомпонент', 'камаз', 'рессорный палец', 'россия', 'bosch', 'jac', 'автокомпонент', 'камаз',
        'переключатели подрулевые, в сборе', 'россия', 'autocomponent', 'component', 'howo', 'prc',
        'shaanxi', 'shacman', 'sinotruk', 'sitrak', 'автодеталь', 'автокомпонент плюс', 'камаз',
        'четырнадцать', 'autocomponent', 'component', 'createk', 'shacman', 'автодеталь', 'автокомпонент плюс',
        'четырнадцать', 'autocomponent', 'component', 'leo trade', 'prc', 'автодеталь', 'автокомпонент плюс',
        'четырнадцать', 'autocomponent', 'component', 'howo', 'prc', 'sinotruk', 'sitrak', 'автодеталь',
        'автокомпонент плюс', 'четырнадцать', 'autocomponent', 'component', 'howo', 'prc', 'sinotruk',
        'sitrak', 'автодеталь', 'автокомпонент плюс', 'четырнадцать', 'autocomponent', 'component', 'howo',
        'prc', 'sinotruk', 'sitrak', 'автодеталь', 'автокомпонент плюс', 'четырнадцать', 'jac', 'prc',
        'автокомпонент', 'камаз'
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
            not brand_lower.startswith('каталоги') and
            not brand_lower.startswith('ки\x00тай') and
            not brand_lower.startswith('к\x00итай') and
            not brand_lower.startswith('товары на') and
            not brand_lower.startswith('переключатели') and
            not brand_lower.startswith('подрулевые') and
            not brand_lower.startswith('в сборе') and
            not brand_lower.startswith('рессорный') and
            not brand_lower.startswith('палец') and
            not brand_lower.startswith('автокомпонент') and
            not brand_lower.startswith('россия') and
            not brand_lower.startswith('камаз') and
            not brand_lower.startswith('автодеталь') and
            not brand_lower.startswith('четырнадцать') and
            not brand_lower.startswith('motul') and
            not brand_lower.startswith('faw') and
            not brand_lower.startswith('foton') and
            not brand_lower.startswith('hande') and
            not brand_lower.startswith('leo') and
            not brand_lower.startswith('onashi') and
            not brand_lower.startswith('prc') and
            not brand_lower.startswith('shaanxi') and
            not brand_lower.startswith('sinotruk') and
            not brand_lower.startswith('sitrak') and
            not brand_lower.startswith('weichai') and
            not brand_lower.startswith('zg.') and
            not brand_lower.startswith('ast') and
            not brand_lower.startswith('autotech') and
            not brand_lower.startswith('avto-') and
            not brand_lower.startswith('component') and
            not brand_lower.startswith('createk') and
            not brand_lower.startswith('howo') and
            not brand_lower.startswith('kolbenschmidt') and
            not brand_lower.startswith('peugeot') and
            not brand_lower.startswith('bosch') and
            not brand_lower.startswith('jac') and
            not brand_lower.startswith('autocomponent')):
            filtered_brands.add(brand_clean)
    
    return sorted(filtered_brands) if filtered_brands else []

def split_combined_brands(brands: List[str]) -> List[str]:
    """Разделяет объединенные бренды на отдельные"""
    result = set()
    
    for brand in brands:
        brand_clean = brand.strip()
        if not brand_clean:
            continue
            
        # Разделяем по различным разделителям
        separators = [' / ', '/', ' & ', '&', ' + ', '+', ' - ', '-', ' | ', '|']
        
        # Проверяем, есть ли разделители
        has_separator = False
        for sep in separators:
            if sep in brand_clean:
                has_separator = True
                parts = brand_clean.split(sep)
                for part in parts:
                    part_clean = part.strip()
                    if part_clean and len(part_clean) > 2:
                        result.add(part_clean)
                break
        
        # Если нет разделителей, добавляем как есть
        if not has_separator:
            result.add(brand_clean)
    
    return sorted(list(result))

def get_brands_by_artikul_armtek(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """Получает бренды с Armtek по артикулу"""
    try:
        log_debug(f"Armtek: начало обработки артикула {artikul}")
        
        # Сначала пробуем API
        api_url = f"https://armtek.ru/api/search?query={artikul}&limit=50"
        log_debug(f"Armtek API: запрос к {api_url}")
        
        try:
            response = make_request(api_url, proxy, max_retries=1)
            if response and response.status_code == 200:
                try:
                    # Проверяем, что ответ действительно JSON
                    content_type = response.headers.get('content-type', '')
                    if 'application/json' in content_type or 'text/json' in content_type:
                        data = response.json()
                        if data and 'brands' in data:
                            brands = [brand.strip() for brand in data['brands'] if brand.strip()]
                            if brands:
                                log_debug(f"Armtek API: найдено {len(brands)} брендов")
                                return filter_armtek_brands(brands)
                    else:
                        log_debug(f"Armtek API: неверный content-type: {content_type}")
                except json.JSONDecodeError as e:
                    log_debug(f"Armtek API: ошибка декодирования JSON: {str(e)}")
                    log_debug(f"Armtek API: ответ: {response.text[:200]}...")
        except Exception as e:
            log_debug(f"Armtek API: ошибка {str(e)}")
        
        # Если API не работает, пробуем HTTP
        http_url = f"https://armtek.ru/search?text={artikul}"
        log_debug(f"Armtek HTTP: запрос к {http_url}")
        
        try:
            response = make_request(http_url, proxy, max_retries=1)
            if response and response.status_code == 200:
                brands = parse_armtek_http_response(response.text, artikul)
                if brands:
                    log_debug(f"Armtek HTTP: найдено {len(brands)} брендов")
                    return brands
        except Exception as e:
            log_debug(f"Armtek HTTP: ошибка {str(e)}")
        
        # Если HTTP не работает, используем Selenium
        log_debug(f"Armtek Selenium: запуск для артикула {artikul}")
        brands = parse_armtek_selenium(artikul, proxy)
        if brands:
            log_debug(f"Armtek Selenium: найдено {len(brands)} брендов")
        return brands
        
    except Exception as e:
        log_debug(f"Ошибка Armtek для {artikul}: {str(e)}")
        return []

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

def parse_armtek_selenium(artikul: str, proxy: Optional[str] = None) -> List[str]:
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
    
    # Настройка прокси для Selenium
    if proxy:
        options.add_argument(f'--proxy-server={proxy}')
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
            'срок отгрузкидней', 'ценаотдо', 'кислородный датчик, шт', 'оплата',
            # Новые исключения для Armtek
            'корпус межосевого дифференциала', 'нет в наличии', 'популярные категории',
            'строительство и ремонт', 'электрика и свет', 'палец sitrak', 'переключатели подрулевые в сборе',
            'палец рессорный', 'дизель', 'мтз', 'сад и огород', 'создание и ремонт',
            'электрика и свет', 'популярные категории', 'строительство и ремонт',
            'fmsi', 'fmsi-verband', 'fmsifmsi-verband', 'популярные категории',
            'ac delco', 'achim', 'achr', 'b-tech', 'beru', 'champion', 'chery', 'dragonzap',
            'ford', 'hot-parts', 'lucas', 'mobis', 'ngk', 'nissan', 'robiton', 'tesla',
            'trw', 'vag', 'valeo', 'популярные категории', 'строительство и ремонт', 'электрика и свет',
            'сад и огород', 'auto-comfort', 'autotech', 'createk', 'howo', 'kamaz', 'leo trade',
            'prc', 'shaanxi', 'shacman', 'sitrak', 'weichai', 'zg.link', 'нет в наличии',
            'палец sitrak', 'ast silver', 'createk', 'howo', 'prc', 'sitrak', 'нет в наличии',
            'ast', 'ast silver', 'ast smart', 'createk', 'createk палец', 'foton', 'howo',
            'htp', 'jmc', 'leo trade', 'prc', 'shaanxi', 'shacman', 'shaft-gear', 'sitrak',
            'wayteko', 'zevs', 'дизель', 'нет в наличии', 'палец рессорный', 'howo', 'prc',
            'shaanxi', 'sitrak', 'sitrak/howo', 'нет в наличии', 'howo', 'prc', 'shaanxi',
            'sitrak', 'sitrak/howo', 'нет в наличии', 'jac', 'kamaz', 'prc', 'нет в наличии',
            'переключатели подрулевые в сборе', 'faw', 'prc', 'нет в наличии',
            # Дополнительные исключения для объединенных брендов
            'gspartshinotoyota', 'gspartshino', 'toyota / lexus', 'toyota/lexus',
            'gspartshinotoyota / lexus', 'gspartshinotoyota/lexus'
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
                not brand_lower.startswith('оплата') and
                not brand_lower.startswith('корпус') and
                not brand_lower.startswith('межосевого') and
                not brand_lower.startswith('дифференциала') and
                not brand_lower.startswith('нет в') and
                not brand_lower.startswith('популярные') and
                not brand_lower.startswith('категории') and
                not brand_lower.startswith('строительство') and
                not brand_lower.startswith('ремонт') and
                not brand_lower.startswith('электрика') and
                not brand_lower.startswith('свет') and
                not brand_lower.startswith('палец') and
                not brand_lower.startswith('переключатели') and
                not brand_lower.startswith('подрулевые') and
                not brand_lower.startswith('рессорный') and
                not brand_lower.startswith('дизель') and
                not brand_lower.startswith('мтз') and
                not brand_lower.startswith('сад') and
                not brand_lower.startswith('огород') and
                not brand_lower.startswith('создание') and
                not brand_lower.startswith('fmsi') and
                not brand_lower.startswith('verband') and
                not brand_lower.startswith('ac ') and
                not brand_lower.startswith('achim') and
                not brand_lower.startswith('achr') and
                not brand_lower.startswith('b-tech') and
                not brand_lower.startswith('beru') and
                not brand_lower.startswith('champion') and
                not brand_lower.startswith('chery') and
                not brand_lower.startswith('dragonzap') and
                not brand_lower.startswith('ford') and
                not brand_lower.startswith('hot-') and
                not brand_lower.startswith('lucas') and
                not brand_lower.startswith('mobis') and
                not brand_lower.startswith('ngk') and
                not brand_lower.startswith('nissan') and
                not brand_lower.startswith('robiton') and
                not brand_lower.startswith('tesla') and
                not brand_lower.startswith('trw') and
                not brand_lower.startswith('vag') and
                not brand_lower.startswith('valeo') and
                not brand_lower.startswith('auto-') and
                not brand_lower.startswith('autotech') and
                not brand_lower.startswith('createk') and
                not brand_lower.startswith('howo') and
                not brand_lower.startswith('kamaz') and
                not brand_lower.startswith('leo ') and
                not brand_lower.startswith('prc') and
                not brand_lower.startswith('shaanxi') and
                not brand_lower.startswith('shacman') and
                not brand_lower.startswith('sitrak') and
                not brand_lower.startswith('weichai') and
                not brand_lower.startswith('zg.') and
                not brand_lower.startswith('ast ') and
                not brand_lower.startswith('foton') and
                not brand_lower.startswith('htp') and
                not brand_lower.startswith('jmc') and
                not brand_lower.startswith('shaft-') and
                not brand_lower.startswith('wayteko') and
                not brand_lower.startswith('zevs') and
                not brand_lower.startswith('jac') and
                not brand_lower.startswith('faw')):
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

def filter_armtek_brands(brands: List[str]) -> List[str]:
    """Фильтрует бренды Armtek, убирая мусор"""
    filtered = []
    exclude_words = {
        '...', 'автохимия и автокосметика', 'автоглушитель', 'аксессуары', 'акции',
        'возврат', 'возможные замены', 'войти', 'выбор armtek', 'гараж',
        'гарантийная политика', 'главная', 'дней', 'доставка', 'инструмент',
        'искомый товар', 'как сделать заказ', 'каталог', 'лучшее предложение',
        'магазины', 'мы в социальных сетях', 'кислородный датчик', 'кислородный датчик, шт',
        'датчик кислорода jac', 'запчасть', 'китай', 'рааз', 'или выбрать другой удобный для\xa0вас способ',
        'ка\x00талоги', 'оплата', 'ки\x00тай', 'к\x00итай', 'товары на autopiter market',
        'переключатели подрулевые, в сборе', 'переключатели подрулевые в сборе',
        'переключатели подрулевые', 'подрулевые', 'в сборе', 'рессорный палец',
        'палец', 'рессорный', 'автокомпонент', 'россия', 'камаз', 'автокомпонент плюс',
        'автодеталь', 'четырнадцать', 'motul.', 'motul', 'faw', 'foton', 'hande axle',
        'leo trade', 'onashi', 'prc', 'shaanxi/shacman', 'sinotruk', 'sitrak', 'weichai',
        'zg.link', 'ast', 'ast silver', 'ast smart', 'autotech', 'avto-tech', 'component',
        'createk', 'howo', 'kolbenschmidt', 'leo', 'peugeot-citroen', 'prc', 'shaanxi/shacman',
        'sinotruk', 'sitrak', 'bosch', 'jac', 'переключатели подрулевые, в сборе', 'россия',
        'autocomponent', 'component', 'howo', 'prc', 'shaanxi', 'shacman', 'sinotruk', 'sitrak',
        'автодеталь', 'автокомпонент плюс', 'камаз', 'наконечник правый', 'наконечник рулевой п',
        'наконечник рулевой тяги, rh', 'наконечник рулевой тяги, rh hino', 'pyчнoй тoпливoпoдкaчивaющий нacoc',
        'сезонные товары', 'шины и диски', 'колпачок маслосъемный', 'невский фильтр',
        'подушка дизеля боковая tk smx', 'сальник распредвала', 'сезонные товары', 'шины и диски'
    }
    
    for brand in brands:
        brand_clean = brand.strip()
        if (brand_clean and 
            len(brand_clean) > 2 and 
            brand_clean.lower() not in exclude_words and
            not any(char.isdigit() for char in brand_clean) and
            not brand_clean.startswith('...') and
            not brand_clean.endswith('...')):
            filtered.append(brand_clean)
    
    return filtered

def parse_armtek_http_response(html_content: str, artikul: str) -> List[str]:
    """Парсит HTTP ответ от Armtek и извлекает бренды"""
    soup = BeautifulSoup(html_content, "html.parser")
    brands = set()
    
    # Ищем бренды в различных элементах
    brand_selectors = [
        '.brand-name',
        '.product-brand',
        '.manufacturer-name',
        '.vendor-title',
        '.item-brand',
        '.brand__name'
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
    
    return filter_armtek_brands(list(brands))

def get_brands_by_artikul_emex(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """Получает бренды с Emex по артикулу"""
    try:
        encoded_artikul = quote(artikul)
        api_url = f"https://emex.ru/api/search/search?detailNum={encoded_artikul}&locationId=263&showAll=false&isHeaderSearch=true"
        
        headers = {
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://emex.ru/products/{encoded_artikul}",
            "x-requested-with": "XMLHttpRequest",
        }
        
        # Сначала пробуем без прокси
        try:
            log_debug(f"[API] Emex: попытка 1 для {artikul}")
            response = requests.get(
                api_url,
                headers=headers,
                timeout=10
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
        except Exception as e:
            log_debug(f"Emex API: ошибка без прокси: {str(e)}")
        
        # Если не получилось, пробуем с прокси
        if proxy:
            try:
                log_debug(f"[API] Emex: попытка 2 с прокси для {artikul}")
                
                # Настройка прокси для requests
                if '@' in proxy:
                    proxy_parts = proxy.split('@')
                    proxy_url = proxy_parts[0]
                    auth_parts = proxy_parts[1].split(':')
                    username = auth_parts[0]
                    password = auth_parts[1]
                    
                    proxy_dict = {
                        'http': f'http://{username}:{password}@{proxy_url}',
                        'https': f'http://{username}:{password}@{proxy_url}'
                    }
                else:
                    proxy_dict = {
                        'http': f'http://{proxy}',
                        'https': f'http://{proxy}'
                    }
                
                response = requests.get(
                    api_url,
                    headers=headers,
                    proxies=proxy_dict,
                    timeout=10
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
            except Exception as e:
                log_debug(f"Emex API: ошибка с прокси: {str(e)}")
        
        return []
        
    except Exception as e:
        log_debug(f"Ошибка Emex для {artikul}: {str(e)}")
        return []

# Инициализация прокси при импорте модуля
load_proxies_from_file()