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
import gc

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
# Оптимизированные таймауты для ускорения работы
TIMEOUT = 8  # Уменьшаем для ускорения
SELENIUM_TIMEOUT = 8  # Уменьшаем для ускорения
PAGE_LOAD_TIMEOUT = 8  # Уменьшаем для ускорения

# Кеширование
REQUEST_CACHE = {}
CACHE_EXPIRATION = 600
FAILED_REQUESTS_CACHE = {}

# Глобальная переменная для хранения прокси
PROXY_LIST = []
PROXY_INDEX = 0
# Набор проблемных прокси, которые следует временно исключать
BAD_PROXIES = set()

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
    """Возвращает следующий прокси из списка с улучшенной обработкой и исключением проблемных"""
    global PROXY_INDEX, PROXY_LIST, BAD_PROXIES

    if not PROXY_LIST:
        load_proxies_from_file()

    if not PROXY_LIST:
        return None

    # Перебираем список, пропуская известные проблемные
    attempts = 0
    while attempts < len(PROXY_LIST):
        proxy_str = PROXY_LIST[PROXY_INDEX % len(PROXY_LIST)]
        PROXY_INDEX += 1
        attempts += 1

        if proxy_str in BAD_PROXIES:
            continue

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

            log_debug(f"Используется прокси: {ip}:{port}")
            return proxy_dict
        except Exception as e:
            log_debug(f"Ошибка парсинга прокси {proxy_str}: {e}")
            BAD_PROXIES.add(proxy_str)
            continue

    log_debug("Нет доступных рабочих прокси (все помечены проблемными)")
    return None

def mark_proxy_bad(proxy_repr: str) -> None:
    """Помечает прокси как проблемный, чтобы временно его не использовать"""
    try:
        if proxy_repr.startswith('http://'):
            proxy_repr = proxy_repr[7:]
    except Exception:
        pass
    BAD_PROXIES.add(proxy_repr)
    log_debug(f"Прокси помечен как проблемный: {proxy_repr}")

def get_proxy_string() -> Optional[str]:
    """Возвращает строку прокси для использования в парсерах"""
    proxy_dict = get_next_proxy()
    if proxy_dict:
        # Извлекаем строку прокси из словаря
        proxy_url = proxy_dict.get('http', '')
        if proxy_url.startswith('http://'):
            return proxy_url[7:]  # Убираем 'http://'
    return None

def cleanup_chrome_processes():
    """Принудительно очищает процессы Chrome и временные директории"""
    try:
        # Убиваем все процессы Chrome более эффективно
        subprocess.run(['pkill', '-9', '-f', 'chrome'], 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        subprocess.run(['pkill', '-9', '-f', 'chromedriver'], 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        subprocess.run(['pkill', '-9', '-f', 'chromium'], 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        
        # Очищаем временные директории Chrome более эффективно
        temp_patterns = [
            '.com.google.Chrome*',
            '.org.chromium.Chromium*',
            'chrome_*',
            'chromium_*'
        ]
        
        for pattern in temp_patterns:
            try:
                # Более быстрая очистка с единой командой
                subprocess.run(['find', '/tmp', '-name', pattern, '-type', 'd', '-exec', 'rm', '-rf', '{}', '+'], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            except:
                pass
        
        # Дополнительная очистка через glob
        import glob
        for pattern in ['/tmp/chrome_*', '/tmp/chromium_*', '/tmp/.com.google.Chrome*', '/tmp/.org.chromium.Chromium*']:
            try:
                for path in glob.glob(pattern):
                    try:
                        subprocess.run(['rm', '-rf', path], 
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                    except:
                        pass
            except:
                pass
        
        time.sleep(1)  # Уменьшаем время ожидания после очистки для ускорения
        
    except Exception as e:
        log_debug(f"Ошибка очистки Chrome процессов: {str(e)}")

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
    session.headers.update(HEADERS)
    
    # Настройка прокси
    if proxy:
        try:
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
            session.proxies.update(proxy_dict)
        except Exception as e:
            log_debug(f"Ошибка настройки прокси: {str(e)}")
    
    for attempt in range(max_retries):
        try:
            # Увеличиваем таймауты для лучшей стабильности
            timeout_config = (TIMEOUT, TIMEOUT)  # (connect_timeout, read_timeout)
            response = session.get(url, timeout=timeout_config)
            
            if response.status_code == 200:
                return response
            else:
                log_debug(f"HTTP {response.status_code} для {url}")
                
        except requests.exceptions.Timeout:
            log_debug(f"Таймаут для {url} (попытка {attempt + 1})")
            if attempt < max_retries - 1:
                time.sleep(2)  # Увеличиваем время ожидания между попытками
        except requests.exceptions.RequestException as e:
            log_debug(f"Ошибка запроса для {url}: {str(e)} (попытка {attempt + 1})")
            if attempt < max_retries - 1:
                time.sleep(2)  # Увеличиваем время ожидания между попытками
        except Exception as e:
            log_debug(f"Неожиданная ошибка для {url}: {str(e)} (попытка {attempt + 1})")
            if attempt < max_retries - 1:
                time.sleep(2)  # Увеличиваем время ожидания между попытками
    
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
    """
    Парсит ответ Autopiter и извлекает бренды используя точный селектор
    """
    brands = set()
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Используем ТОЧНЫЙ селектор из DevTools пользователя
        # #main-content > div > div > div.Table__table____693a7dea7e60fe92 > div > div.IndividualTableRow__infoColumn___b7ecc9b28c9245b4 > span > span > span > span
        
        # Ищем main-content
        main_content = soup.select_one('#main-content')
        if not main_content:
            log_debug(f"Autopiter: не найден #main-content для {artikul}")
            return []
        
        # Ищем таблицу с классом, содержащим Table__table
        table = main_content.select_one('div[class*="Table__table"]')
        if not table:
            log_debug(f"Autopiter: не найдена таблица Table__table для {artikul}")
            return []
        
        # Ищем строки IndividualTableRow
        rows = table.select('div[class*="IndividualTableRow"]')
        if not rows:
            log_debug(f"Autopiter: не найдены строки IndividualTableRow для {artikul}")
            return []
        
        # Проходим по всем строкам и ищем infoColumn с точным селектором
        for row in rows:
            info_column = row.select_one('div[class*="IndividualTableRow__infoColumn"]')
            if info_column:
                # Используем точный селектор: span > span > span > span
                brand_spans = info_column.select('span > span > span > span')
                for span in brand_spans:
                    brand = span.get_text(strip=True)
                    if brand and len(brand) > 1 and not brand.isdigit():
                        # Дополнительная проверка - исключаем мусор и данные из "Часто ищут"
                        if (len(brand) < 50 and 
                            not any(exclude in brand.lower() for exclude in [
                                'сверла', 'свечи', 'автошина', 'заклепка', 'игла', 
                                'лейка', 'лента', 'помпа', 'поплавок', 'ремень', 
                                'фильтр', 'хомут', 'шина', 'щетка', 'кольцо',
                                'комплект', 'костюм', 'стартер', 'шайба', 'деталь',
                                'накладка', 'тормозная', 'задняя', 'комплект', 'колесо',
                                'производители', 'часто ищут', 'рекомендуем', 'сверла техмаш',
                                'тестовый', 'клиента', 'без артикула', 'оригинальная'
                            ]) and
                            not brand.lower().startswith('12643') and  # Исключаем артикулы
                            not brand.lower().startswith('d-') and
                            not any(char.isdigit() for char in brand[:3])  # Исключаем артикулы в начале
                        ):
                            brands.add(brand)
                            log_debug(f"Autopiter: найден бренд '{brand}' для {artikul}")
        
        # Если не нашли бренды через точный селектор, пробуем через title
        if not brands:
            for row in rows:
                info_column = row.select_one('div[class*="IndividualTableRow__infoColumn"]')
                if info_column:
                    brand_spans = info_column.select('span[title]')
                    for span in brand_spans:
                        brand = span.get('title')
                        if brand and len(brand) > 1 and not brand.isdigit():
                            if (len(brand) < 50 and 
                                not any(exclude in brand.lower() for exclude in [
                                    'сверла', 'свечи', 'автошина', 'заклепка', 'игла', 
                                    'лейка', 'лента', 'помпа', 'поплавок', 'ремень', 
                                    'фильтр', 'хомут', 'шина', 'щетка', 'кольцо',
                                    'комплект', 'костюм', 'стартер', 'шайба', 'деталь',
                                    'накладка', 'тормозная', 'задняя', 'комплект', 'колесо',
                                    'производители', 'часто ищут', 'рекомендуем', 'сверла техмаш',
                                    'тестовый', 'клиента', 'без артикула', 'оригинальная'
                                ]) and
                                not brand.lower().startswith('12643') and
                                not brand.lower().startswith('d-') and
                                not any(char.isdigit() for char in brand[:3])
                            ):
                                brands.add(brand)
                                log_debug(f"Autopiter: найден бренд через title '{brand}' для {artikul}")
        
        log_debug(f"Autopiter: итого найдено {len(brands)} брендов для {artikul}")
        
    except Exception as e:
        log_debug(f"Ошибка при парсинге брендов Autopiter для {artikul}: {e}")
    
    return sorted(list(brands))

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
                                # Применяем разделение объединенных брендов
                                split_brands = split_combined_brands(brands)
                                return filter_armtek_brands(split_brands)
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
                    # Применяем разделение объединенных брендов
                    split_brands = split_combined_brands(brands)
                    return filter_armtek_brands(split_brands)
        except Exception as e:
            log_debug(f"Armtek HTTP: ошибка {str(e)}")
        
        # Если HTTP не работает, используем Selenium
        log_debug(f"Armtek Selenium: запуск для артикула {artikul}")
        brands = parse_armtek_selenium(artikul, proxy)
        if brands:
            log_debug(f"Armtek Selenium: найдено {len(brands)} брендов")
            # Применяем разделение объединенных брендов
            split_brands = split_combined_brands(brands)
            return filter_armtek_brands(split_brands)
        return []
        
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
            # Проверяем content-type перед попыткой JSON декодирования
            content_type = response.headers.get('content-type', '').lower()
            if 'application/json' not in content_type and 'text/json' not in content_type:
                log_debug(f"Armtek API: неверный content-type: {content_type}")
                return []
            
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
                
                log_debug(f"Armtek API: найдено {len(brands)} брендов")
                return sorted(brands)
            except json.JSONDecodeError as e:
                log_debug(f"Armtek API: ошибка декодирования JSON: {str(e)}")
                # Логируем первые 200 символов ответа для отладки
                response_text = response.text[:200]
                log_debug(f"Armtek API: начало ответа: {response_text}")
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
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--disable-ipc-flooding-protection')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = None
    try:
        # Принудительная очистка перед запуском
        cleanup_chrome_processes()
        time.sleep(1)  # Уменьшаем время ожидания для ускорения
        
        # Пробуем несколько способов инициализации драйвера
        driver_init_methods = [
            lambda: webdriver.Chrome(options=options),
            lambda: webdriver.Chrome(service=Service('/usr/local/bin/chromedriver'), options=options),
            lambda: webdriver.Chrome(service=Service('/usr/bin/chromedriver'), options=options),
        ]
        
        driver = None
        for i, init_method in enumerate(driver_init_methods):
            try:
                log_debug(f"Armtek Selenium: попытка инициализации драйвера {i+1}")
                driver = init_method()
                log_debug(f"Armtek Selenium: драйвер успешно инициализирован методом {i+1}")
                break
            except Exception as e:
                log_debug(f"Armtek Selenium: ошибка инициализации драйвера {i+1}: {str(e)}")
                if i == len(driver_init_methods) - 1:  # Последняя попытка
                    # Пробуем без user-data-dir как последний вариант
                    log_debug("Armtek Selenium: пробуем без user-data-dir")
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
                    options.add_argument('--disable-background-timer-throttling')
                    options.add_argument('--disable-backgrounding-occluded-windows')
                    options.add_argument('--disable-renderer-backgrounding')
                    options.add_argument('--disable-features=VizDisplayCompositor')
                    options.add_argument('--disable-ipc-flooding-protection')
                    options.add_argument('--no-first-run')
                    options.add_argument('--no-default-browser-check')
                    options.add_argument('--disable-default-apps')
                    options.add_argument('--disable-blink-features=AutomationControlled')
                    options.add_experimental_option("excludeSwitches", ["enable-automation"])
                    options.add_experimental_option('useAutomationExtension', False)
                    try:
                        driver = webdriver.Chrome(options=options)
                        log_debug("Armtek Selenium: драйвер инициализирован без user-data-dir")
                    except Exception as e2:
                        log_debug(f"Armtek Selenium: финальная ошибка инициализации: {str(e2)}")
                        raise e2
                else:
                    time.sleep(1)  # Уменьшаем паузу между попытками для ускорения
        
        if driver is None:
            log_debug("Armtek Selenium: не удалось инициализировать драйвер")
            return []
        
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
            # Точный селектор из DevTools пользователя
            'body > app-root > div > mp-main > search-result > div > div > project-ui-search-result-with-filters > div > div.results.has-filter-on-desktop > project-ui-search-result > div > div > div.results-list__items.ng-star-inserted > div > div:nth-child(2) > project-ui-article-card > project-ui-article-card-with-suggestions > div > div.content > div.row.ng-star-inserted > div > div.item.item-mobile > span.font__body2.brand--selecting',
            # Альтернативные селекторы для Armtek
            'span.font__body2.brand--selecting',
            '.brand--selecting',
            '.font__body2.brand--selecting',
            # Общие селекторы
            '.product-card .brand-name',
            '.product-card__brand',
            '.catalog-item .brand',
            '.item .brand',
            '[data-testid="product-item"] .brand',
            '.product-name .brand',
            '.product .brand',
            '.brand-name',
            '.brand',
            '.make',
            '.manufacturer',
            '.vendor',
            '.producer',
            '.manufacturer-name',
            '.vendor-title',
            '.item-brand',
            '.brand__name'
        ]
        
        brands = set()
        for selector in brand_selectors:
            for tag in soup.select(selector):
                brand = tag.get_text(strip=True)
                if brand and len(brand) > 2 and not brand.isdigit():
                    brands.add(brand)
        
        # Поиск по тексту если не нашли бренды
        if not brands:
            brand_pattern = re.compile(r'(бренд|производитель|brand|manufacturer)', re.IGNORECASE)
            for tag in soup.find_all(['span', 'div', 'a', 'h3', 'h4', 'h5']):
                text = tag.get_text(strip=True)
                if text and len(text) > 2 and len(text) < 50:
                    if not brand_pattern.search(text) and not any(char.isdigit() for char in text):
                        brands.add(text)
        
        log_debug(f"Armtek Selenium: найдены бренды {list(brands)}")
        
        # Применяем разделение объединенных брендов
        split_brands = split_combined_brands(list(brands))
        return filter_armtek_brands(split_brands)
        
    except Exception as e:
        log_debug(f"Armtek Selenium error: {str(e)}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        # Очищаем временную директорию
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
    """Фильтрует бренды Armtek, оставляя только разрешенные бренды"""
    # Расширенный белый список разрешенных брендов
    allowed_brands = {
        'QUNZE', 'NIPPON', 'MOTORS MATTO', 'JMC', 'KOBELCO', 'PRC', 
        'HUANG LIN', 'ERISTIC', 'HINO', 'OOTOKO', 'MITSUBISHI', 'TOYOTA',
        'AUTOKAT', 'ZEVS', 'PITWORK', 'HITACHI', 'NISSAN', 'DETOOL', 'CHEMIPRO',
        'STELLOX', 'FURO', 'EDCON', 'REPARTS',
        # Добавлено из пожеланий: считать брендами
        'HTP', 'FVR', 'ISUZU', 'G-BRAKE', 'АККОР', 'ДИЗЕЛЬ',
        # Новые бренды из логов
        'EMEK', 'HOT-PARTS', 'CARMECH', 'JAPACO', 'AUTOCOMPONENT',
        # Дополнительные бренды, которые должны быть найдены
        'EMEK', 'HOT-PARTS', 'ISUZU', 'CARMECH', 'G-BRAKE',
        # Новые бренды из списка пользователя
        'QINYAN', 'AMZ', 'ERREVI', 'PETERS', 'EMMERRE', 'SIMPECO', 'BPW', 'FEBI', 
        'AUGER', 'BKAVTO', 'MANSONS', 'EXOVO', 'ALON', 'AMR', 'AOSS', 'KONNOR', 
        'SAMPA', 'WABCO', 'ТОНАР', 'SMB', 'SCHMITZ', 'INTERNATIONAL', 'НЕФАЗ', 
        'SEIWA', 'AIC', 'MARSHALL', 'FACET', 'DDA', 'PEORA', 'METALCAUCHO', 
        'SAF', 'MASUMA', 'VOLVO', 'NIGRIN', 'SPIDAN', 'RUVILLE', 'SITRAK', 
        'AVTOSHTAMP', 'IVECO', 'MATADOR', 'LMI', 'RHIAG', 'VIKA', 'TRICO', 
        'ROCK FORCE', 'HARLEY DAVIDSON', 'АДС', 'STEMOT', 'AYFAR', 
        'SIGAM', 'QUICK BRAKE', 'GATES', 'FRECCIA', 'VENDOR', 'GTOOL', 'SIDAT', 
        'BRECAV', 'РОСОМЗ', 'SPJ', 'DELTA'
    }
    
    filtered = []
    
    for brand in brands:
        brand_clean = brand.strip()
        if not brand_clean:
            continue
            
        # Проверяем, есть ли бренд в белом списке (регистронезависимо)
        brand_upper = brand_clean.upper()
        if brand_upper in allowed_brands:
            # Возвращаем оригинальное написание из белого списка
            for allowed_brand in allowed_brands:
                if allowed_brand.upper() == brand_upper:
                    filtered.append(allowed_brand)
                    break
        # Также добавляем бренды, которые содержат ключевые слова
        elif any(keyword in brand_upper for keyword in [
            'EMEK', 'HOT', 'PARTS', 'CARMECH', 'JAPACO', 'AUTO', 'COMPONENT', 'ISUZU', 'G-BRAKE',
            'QINYAN', 'AMZ', 'ERREVI', 'PETERS', 'EMMERRE', 'SIMPECO', 'BPW', 'FEBI', 
            'AUGER', 'BKAVTO', 'MANSONS', 'EXOVO', 'ALON', 'AMR', 'AOSS', 'KONNOR', 
            'SAMPA', 'WABCO', 'ТОНАР', 'SMB', 'SCHMITZ', 'INTERNATIONAL', 'НЕФАЗ', 
            'SEIWA', 'AIC', 'MARSHALL', 'FACET', 'DDA', 'PEORA', 'METALCAUCHO', 
            'SAF', 'MASUMA', 'VOLVO', 'NIGRIN', 'SPIDAN', 'RUVILLE', 'SITRAK', 
            'AVTOSHTAMP', 'IVECO', 'MATADOR', 'LMI', 'RHIAG', 'VIKA', 'TRICO', 
            'ROCK FORCE', 'HARLEY DAVIDSON', 'АДС', 'STEMOT', 'AYFAR', 
            'SIGAM', 'QUICK BRAKE', 'GATES', 'FRECCIA', 'VENDOR', 'GTOOL', 'SIDAT', 
            'BRECAV', 'РОСОМЗ', 'SPJ', 'DELTA'
        ]):
            filtered.append(brand_clean)
        # Специальная обработка для составных брендов
        elif 'HOT-PARTS' in brand_upper or 'HOT_PARTS' in brand_upper:
            filtered.append('HOT-PARTS')
        elif 'G-BRAKE' in brand_upper or 'GBRAKE' in brand_upper:
            filtered.append('G-BRAKE')
        elif 'QUICK BRAKE' in brand_upper or 'QUICKBRAKE' in brand_upper:
            filtered.append('QUICK BRAKE')
        elif 'HARLEY DAVIDSON' in brand_upper or 'HARLEYDAVIDSON' in brand_upper:
            filtered.append('HARLEY DAVIDSON')
        elif 'ROCK FORCE' in brand_upper or 'ROCKFORCE' in brand_upper:
            filtered.append('ROCK FORCE')
    
    return sorted(list(set(filtered)))  # Убираем дубликаты и сортируем

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
    """Получает бренды с Emex по артикулу с улучшенной обработкой блокировок"""
    try:
        encoded_artikul = quote(artikul)
        
        # Ротация User-Agent для обхода блокировок
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
        ]
        
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://emex.ru/search?detailNum={encoded_artikul}",
            "X-Requested-With": "XMLHttpRequest",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Origin": "https://emex.ru",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "DNT": "1",
            "Host": "emex.ru",
            "Sec-Ch-Ua": '"Chromium";v="139", "Not=A?Brand";v="99"',
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Content-Type": "application/json",
        }
        
        # Подготовим варианты записи артикула
        try:
            raw_num = artikul.strip()
            candidate_nums = list(dict.fromkeys([
                raw_num,
                raw_num.upper(),
                raw_num.replace('-', ''),
                raw_num.replace('-', '').upper(),
                raw_num.replace(' ', ''),
                raw_num.replace(' ', '').upper(),
            ]))
        except Exception:
            candidate_nums = [artikul]

        # Создаем сессию с прокси
        session = requests.Session()
        session.headers.update(headers)
        
        # Настройка прокси - принудительно используем прокси для Emex
        proxies = None
        if proxy:
            try:
                # Если proxy - это строка, преобразуем в словарь
                if isinstance(proxy, str):
                    if proxy.startswith('http://'):
                        proxy = proxy[7:]  # Убираем 'http://'
                    proxies = {
                        'http': f'http://{proxy}',
                        'https': f'http://{proxy}'
                    }
                else:
                    proxies = proxy
                session.proxies.update(proxies)
                log_debug(f"Emex: использование прокси {proxy}")
            except Exception as e:
                log_debug(f"Emex: ошибка настройки прокси {proxy}: {str(e)}")
        else:
            # Если прокси не передан, получаем его автоматически
            try:
                proxy_dict = get_next_proxy()
                if proxy_dict:
                    session.proxies.update(proxy_dict)
                    log_debug(f"Emex: автоматически получен прокси")
                else:
                    log_debug(f"Emex: прокси недоступен, пробуем без прокси")
            except Exception as e:
                log_debug(f"Emex: ошибка получения прокси: {str(e)}")
        
        # Устанавливаем куки
        try:
            session.cookies.set("regionId", "263", domain="emex.ru")
            session.cookies.set("locationId", "263", domain="emex.ru")
        except Exception:
            pass
        
        # Прогрев сессии (сокращенный)
        try:
            log_debug(f"Emex: прогрев сессии с прокси: {proxies is not None}")
            session.get("https://emex.ru/", timeout=5, proxies=proxies)
            time.sleep(0.5)  # Небольшая пауза между запросами
        except Exception as e:
            log_debug(f"Emex: ошибка прогрева сессии: {str(e)}")
            pass
        
        # Получаем XSRF токен
        xsrf_token = (
            session.cookies.get("XSRF-TOKEN")
            or session.cookies.get("xsrf-token")
            or session.cookies.get("X_XSRF_TOKEN")
            or session.cookies.get("csrf-token")
        )
        if xsrf_token:
            session.headers.update({"X-XSRF-TOKEN": xsrf_token})

        # Основные попытки с разными параметрами (сокращенный список)
        api_variants = [
            {"showAll": "false", "isHeaderSearch": "true"},
            {"showAll": "true", "isHeaderSearch": "true"},
        ]
        
        # Счетчик попыток для предотвращения бесконечных циклов
        total_attempts = 0
        max_total_attempts = 8  # Увеличиваем количество попыток для Emex
        
        for num in candidate_nums:
            num_enc = quote(num)
            
            for params in api_variants:
                if total_attempts >= max_total_attempts:
                    log_debug(f"Emex API: достигнут лимит попыток для {artikul}, пропускаем")
                    break
                    
                try:
                    api_url = (
                        f"https://emex.ru/api/search/search?detailNum={num_enc}"
                        f"&locationId=263&showAll={params['showAll']}&isHeaderSearch={params['isHeaderSearch']}"
                    )
                    
                    log_debug(f"Emex API: попытка {total_attempts + 1} для {artikul} с параметрами {params}")
                    
                    # Пробуем с разными заголовками сжатия (сокращенный список)
                    for compression_headers in [
                        {"Accept-Encoding": "gzip, deflate"},
                        {"Accept-Encoding": "identity"},
                    ]:
                        if total_attempts >= max_total_attempts:
                            break
                            
                        try:
                            current_headers = headers.copy()
                            current_headers.update(compression_headers)
                            
                            response = session.get(
                                api_url,
                                headers=current_headers,
                                timeout=10,  # Еще больше уменьшаем таймаут
                                proxies=proxies
                            )
                            
                            total_attempts += 1
                            
                            if response.status_code == 200:
                                content_type = response.headers.get('content-type', '').lower()
                                if 'application/json' in content_type:
                                    try:
                                        data = response.json()
                                        brands = set()
                                        
                                        # Обработка структуры ответа Emex
                                        search_result = data.get("searchResult", {})
                                        if search_result:
                                            # Проверяем makes - основной источник брендов
                                            makes = search_result.get("makes", {})
                                            if makes:
                                                makes_list = makes.get("list", [])
                                                for item in makes_list:
                                                    if isinstance(item, dict):
                                                        brand = item.get("make")
                                                        if brand and brand.strip():
                                                            brands.add(brand.strip())
                                                            log_debug(f"Emex API: добавлен бренд '{brand}' для {artikul}")
                                            
                                            # Дополнительно берем бренд из searchResult.make
                                            sr_make = search_result.get("make")
                                            if isinstance(sr_make, str) and sr_make.strip():
                                                brands.add(sr_make.strip())
                                                log_debug(f"Emex API: добавлен бренд из searchResult.make '{sr_make}' для {artikul}")
                                        
                                        if brands:
                                            log_debug(f"Emex API: найдено {len(brands)} брендов для {artikul}")
                                            return sorted(list(brands))
                                        
                                    except json.JSONDecodeError as e:
                                        log_debug(f"Emex API: ошибка JSON для {artikul}: {str(e)}")
                                        continue
                            
                            elif response.status_code == 429:  # Rate limit
                                log_debug(f"Emex API: Rate limit для {artikul}, пропускаем")
                                break  # Выходим из цикла при rate limit
                            elif response.status_code == 403:  # Forbidden
                                log_debug(f"Emex API: 403 Forbidden для {artikul}, помечаем прокси как проблемный и пробуем следующий")
                                try:
                                    # Помечаем текущий прокси как плохой
                                    current_http = session.proxies.get('http') or ''
                                    if current_http:
                                        mark_proxy_bad(current_http)
                                except Exception:
                                    pass
                                # Меняем прокси
                                new_proxy = get_next_proxy()
                                if new_proxy:
                                    session.proxies.update(new_proxy)
                                break  # Переходим к следующей конфигурации
                            
                        except requests.exceptions.Timeout:
                            log_debug(f"Emex API: таймаут для {artikul} (попытка {total_attempts})")
                            if total_attempts >= max_total_attempts:
                                log_debug(f"Emex API: слишком много таймаутов для {artikul}, пропускаем")
                                break
                            # При таймауте пробуем сменить прокси
                            if not proxy:
                                try:
                                    new_proxy_dict = get_next_proxy()
                                    if new_proxy_dict:
                                        session.proxies.update(new_proxy_dict)
                                        log_debug(f"Emex API: смена прокси после таймаута")
                                except Exception:
                                    pass
                            continue
                        except requests.exceptions.RequestException as e:
                            log_debug(f"Emex API: ошибка запроса для {artikul}: {str(e)}")
                            # При ошибке запроса тоже пробуем сменить прокси
                            if not proxy:
                                try:
                                    # Если это ProxyError или 502, помечаем текущий прокси как проблемный
                                    try:
                                        from requests.exceptions import ProxyError as _ProxyError
                                        if isinstance(e, _ProxyError) or '502 Bad Gateway' in str(e):
                                            current_http = session.proxies.get('http') or ''
                                            if current_http:
                                                mark_proxy_bad(current_http)
                                    except Exception:
                                        pass
                                    new_proxy_dict = get_next_proxy()
                                    if new_proxy_dict:
                                        session.proxies.update(new_proxy_dict)
                                        log_debug(f"Emex API: смена прокси после ошибки")
                                except Exception:
                                    pass
                            continue
                        
                        # Уменьшенная пауза между попытками
                        time.sleep(0.2)  # Увеличиваем паузу для стабильности
                
                except Exception as e:
                    log_debug(f"Emex API: ошибка для {artikul}: {str(e)}")
                    total_attempts += 1
                    continue

        # Если все попытки не удались, пробуем SeleniumFallback (ограниченный)
        log_debug(f"Emex API: не удалось получить бренды для {artikul}, пробуем Selenium fallback")
        try:
            # Легкий парсинг страницы поиска: бренды часто присутствуют в блоке фильтров/подсказок
            from selenium.webdriver.common.by import By as _By
            brands = set()
            opts = Options()
            opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--blink-settings=imagesEnabled=false')
            tmp_dir = tempfile.mkdtemp(prefix=f"chrome_emex_{uuid.uuid4().hex[:8]}_")
            opts.add_argument(f'--user-data-dir={tmp_dir}')
            drv = webdriver.Chrome(options=opts)
            drv.set_page_load_timeout(15)
            try:
                search_url = f"https://emex.ru/search?detailNum={quote(artikul)}"
                drv.get(search_url)
                WebDriverWait(drv, 10).until(lambda d: d.execute_script('return document.readyState') == 'complete')
                # Ищем бренды в фильтрах или в блоке makes
                possible_selectors = [
                    'div.makes-list span',
                    '[data-qa="makes-filter"] span',
                    'div[data-qa="brand-name"]',
                ]
                for sel in possible_selectors:
                    try:
                        elems = drv.find_elements(_By.CSS_SELECTOR, sel)
                        for el in elems:
                            txt = el.text.strip()
                            if txt and len(txt) > 1 and not txt.isdigit():
                                brands.add(txt)
                    except Exception:
                        continue
            finally:
                try:
                    drv.quit()
                except Exception:
                    pass
                try:
                    import shutil
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass
            if brands:
                log_debug(f"Emex Selenium fallback: найдено {len(brands)} брендов для {artikul}")
                return sorted(list(brands))
        except Exception as _e:
            log_debug(f"Emex Selenium fallback ошибка: {str(_e)}")
        return []
        
    except Exception as e:
        log_debug(f"Ошибка Emex для {artikul}: {str(e)}")
        return []

# Инициализация прокси при импорте модуля
load_proxies_from_file()