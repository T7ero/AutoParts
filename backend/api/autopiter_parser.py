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
import threading
from typing import List, Dict, Optional, Tuple, Set, Union
from selenium.common.exceptions import TimeoutException
from concurrent.futures import ThreadPoolExecutor
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
TIMEOUT = 5  # Увеличиваем для стабильности
SELENIUM_TIMEOUT = 8  # Оптимизированное время для ускорения
PAGE_LOAD_TIMEOUT = 12  # Увеличиваем для стабильности

# Настройки для пула драйверов
DRIVER_POOL_SIZE = 3
DRIVER_CREATION_RETRIES = 3
DRIVER_TIMEOUT_RETRIES = 3  # Увеличиваем количество попыток

# Кеширование
REQUEST_CACHE = {}
CACHE_EXPIRATION = 600
FAILED_REQUESTS_CACHE = {}

# Глобальная переменная для хранения прокси
PROXY_LIST = []
PROXY_INDEX = 0
# Набор проблемных прокси, которые следует временно исключать
BAD_PROXIES = set()

# Пул драйверов для Armtek
DRIVER_POOL = []
DRIVER_POOL_LOCK = threading.Lock()
DRIVER_LAST_USED = {}

def log_debug(message):
    print(f"[DEBUG] {message}")

def get_driver_from_pool() -> Optional[webdriver.Chrome]:
    """Получает драйвер из пула или создает новый"""
    global DRIVER_POOL, DRIVER_POOL_LOCK
    
    with DRIVER_POOL_LOCK:
        if DRIVER_POOL:
            driver = DRIVER_POOL.pop()
            DRIVER_LAST_USED[id(driver)] = time.time()
            return driver
    
    # Создаем новый драйвер
    temp_dir = tempfile.mkdtemp(prefix=f"chrome_pool_{uuid.uuid4().hex[:8]}_")
    for attempt in range(DRIVER_CREATION_RETRIES):
        try:
            driver = _create_chrome_driver_robust(temp_dir)
            if driver:
                DRIVER_LAST_USED[id(driver)] = time.time()
                return driver
            time.sleep(1)
        except Exception as e:
            log_debug(f"Попытка {attempt + 1} создания драйвера: {str(e)}")
            time.sleep(2)
    
    return None

def return_driver_to_pool(driver: webdriver.Chrome):
    """Возвращает драйвер в пул или закрывает его"""
    global DRIVER_POOL, DRIVER_POOL_LOCK
    
    if driver is None:
        return
    
    try:
        # Проверяем, не слишком ли старый драйвер
        driver_id = id(driver)
        if driver_id in DRIVER_LAST_USED:
            age = time.time() - DRIVER_LAST_USED[driver_id]
            if age > 300:  # 5 минут
                driver.quit()
                if driver_id in DRIVER_LAST_USED:
                    del DRIVER_LAST_USED[driver_id]
                return
        
        with DRIVER_POOL_LOCK:
            if len(DRIVER_POOL) < DRIVER_POOL_SIZE:
                DRIVER_POOL.append(driver)
            else:
                driver.quit()
                if driver_id in DRIVER_LAST_USED:
                    del DRIVER_LAST_USED[driver_id]
    except Exception as e:
        log_debug(f"Ошибка возврата драйвера в пул: {str(e)}")
        try:
            driver.quit()
        except:
            pass

def cleanup_driver_pool():
    """Очищает пул драйверов"""
    global DRIVER_POOL, DRIVER_POOL_LOCK, DRIVER_LAST_USED
    
    with DRIVER_POOL_LOCK:
        for driver in DRIVER_POOL:
            try:
                driver.quit()
            except:
                pass
        DRIVER_POOL.clear()
        DRIVER_LAST_USED.clear()

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
        # Проверяем, есть ли процессы Chrome перед очисткой
        chrome_processes = []
        
        # Убиваем все процессы Chrome более эффективно
        for process_name in ['chrome', 'chromedriver', 'chromium']:
            try:
                # Проверяем, есть ли процессы
                result = subprocess.run(['pgrep', '-f', process_name], 
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    chrome_processes.extend(result.stdout.strip().split('\n'))
            except:
                pass
        
        if chrome_processes:
            log_debug(f"Найдено {len(chrome_processes)} процессов Chrome для очистки")
            
            # Убиваем процессы
            for process_name in ['chrome', 'chromedriver', 'chromium']:
                try:
                    subprocess.run(['pkill', '-9', '-f', process_name], 
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                except:
                    pass
        
        # Очищаем временные директории Chrome более эффективно
        temp_patterns = [
            '.com.google.Chrome*',
            '.org.chromium.Chromium*',
            'chrome_*',
            'chromium_*'
        ]
        
        # Очищаем /tmp
        for pattern in temp_patterns:
            try:
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
        
        # Очищаем временные директории в текущем рабочем каталоге
        try:
            current_dir = os.getcwd()
            for pattern in ['chrome_*', 'chromium_*']:
                for path in glob.glob(os.path.join(current_dir, pattern)):
                    try:
                        if os.path.isdir(path):
                            subprocess.run(['rm', '-rf', path], 
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                    except:
                        pass
        except:
            pass
        
        time.sleep(0.5)  # Уменьшаем время ожидания после очистки для ускорения
        
    except Exception as e:
        log_debug(f"Ошибка очистки Chrome процессов: {str(e)}")

def is_site_available(url: str, proxies: Optional[Dict] = None) -> bool:
    """Проверяет доступность сайта"""
    try:
        response = requests.head(url, timeout=10, proxies=proxies, headers=HEADERS)
        return response.status_code < 500
    except:
        return False

def make_request(
    url: str,
    proxy: Optional[Union[str, Dict[str, str]]] = None,
    max_retries: int = 2,
    timeout: int = 10,
    cache_key: Optional[str] = None,
) -> Optional[requests.Response]:
    """Выполняет HTTP-запрос с поддержкой прокси и повторными попытками.
    Параметр cache_key зарезервирован для возможного кеширования (пока не используется).
    """

    # Настройка сессии
    session = requests.Session()
    
    # Настройка прокси
    if proxy:
        if isinstance(proxy, dict):
            session.proxies.update(proxy)
            log_debug("Используется словарь прокси")
        else:
            # Проверяем формат прокси-строки
            if '@' in proxy:
                # Формат: login:password@ip:port
                auth_part, proxy_part = proxy.split('@', 1)
                if ':' in auth_part:
                    username, password = auth_part.split(':', 1)
                    proxy_dict = {
                        'http': f'http://{username}:{password}@{proxy_part}',
                        'https': f'http://{username}:{password}@{proxy_part}'
                    }
                    log_debug(f"Используется прокси с аутентификацией: {username}:***@{proxy_part}")
                else:
                    proxy_dict = {
                        'http': f'http://{proxy}',
                        'https': f'http://{proxy}'
                    }
                    log_debug(f"Используется прокси без аутентификации: {proxy}")
            else:
                proxy_dict = {
                    'http': f'http://{proxy}',
                    'https': f'http://{proxy}'
                }
                log_debug(f"Используется прокси: {proxy}")
            session.proxies.update(proxy_dict)
    
    # Настройка заголовков — используем «современные» заголовки из HEADERS
    session.headers.update(HEADERS)
    
    # Выполнение запроса с повторными попытками
    for attempt in range(1, max_retries + 1):
        try:
            log_debug(f"Попытка {attempt} {'с прокси' if proxy else 'без прокси'} для {url}")
            
            response = session.get(url, timeout=timeout, allow_redirects=True)
            
            # Проверяем статус ответа
            if response.status_code == 200:
                return response
            elif response.status_code == 403:
                log_debug(f"403 Forbidden для {url} (попытка {attempt})")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)  # Экспоненциальная задержка
                    continue
            elif response.status_code == 429:
                log_debug(f"429 Rate Limit для {url} (попытка {attempt})")
                if attempt < max_retries:
                    wait_time = 30 * (2 ** attempt)  # Еще более агрессивная задержка: 30, 60, 120 секунд
                    log_debug(f"Ждем {wait_time} секунд перед повторной попыткой")
                    time.sleep(wait_time)
                    continue
                else:
                    log_debug(f"Все попытки исчерпаны для {url}")
                    return None
            else:
                log_debug(f"HTTP {response.status_code} для {url}")
                return response
                
        except requests.exceptions.ProxyError as e:
            log_debug(f"Ошибка прокси для {url}: {str(e)} (попытка {attempt})")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
        except requests.exceptions.Timeout as e:
            log_debug(f"Таймаут для {url}: {str(e)} (попытка {attempt})")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
        except requests.exceptions.RequestException as e:
            log_debug(f"Ошибка запроса для {url}: {str(e)} (попытка {attempt})")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
    
    log_debug(f"Все попытки исчерпаны для {url}")
    return None
def parse_autopiter_selenium(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """Selenium-парсинг АвтоПитер с полной загрузкой страницы"""
    driver = None
    temp_dir = tempfile.mkdtemp(prefix=f"chrome_autopiter_")
    
    try:
        # Используем драйвер из пула или создаем новый
        driver = get_driver_from_pool()
        if not driver:
            driver = _create_chrome_driver_robust(temp_dir, proxy)
        
        # Очищаем cookies перед загрузкой для предотвращения проблем с кэшем
        try:
            driver.delete_all_cookies()
        except Exception as e:
            log_debug(f"Не удалось очистить cookies: {str(e)}")
        
        url = f"https://autopiter.ru/goods/{quote(artikul)}"
        driver.get(url)
        
        # Ждем полной загрузки страницы
        wait = WebDriverWait(driver, SELENIUM_TIMEOUT)
        try:
            # Ждем появления основного контента
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#main-content")))
        except TimeoutException:
            log_debug(f"АвтоПитер: таймаут ожидания #main-content для {artikul}")
        
        # Дополнительное ожидание для полной загрузки
        time.sleep(2)
        
        # Прокручиваем страницу для подгрузки ВСЕХ данных
        last_height = driver.execute_script("return document.body.scrollHeight")
        last_row_count = 0
        
        # Увеличиваем количество прокруток и время ожидания
        max_scrolls = 30  # Увеличено с 10 до 30
        scroll_attempts = 0
        no_change_count = 0
        
        for _ in range(max_scrolls):
            scroll_attempts += 1
            # Прокручиваем вниз
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Увеличено с 1.5 до 2 секунд для подгрузки данных
            
            # Проверяем количество строк в таблице
            try:
                rows = driver.find_elements(By.CSS_SELECTOR, 'div[class*="IndividualTableRow"]')
                current_row_count = len(rows)
                
                # Если количество строк увеличилось, продолжаем прокрутку
                if current_row_count > last_row_count:
                    last_row_count = current_row_count
                    no_change_count = 0
                    log_debug(f"АвтоПитер: найдено {current_row_count} строк после прокрутки {scroll_attempts}")
                else:
                    no_change_count += 1
            except Exception as e:
                log_debug(f"Ошибка проверки строк: {str(e)}")
            
            # Проверяем, появились ли новые данные по высоте страницы
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                no_change_count += 1
            else:
                last_height = new_height
                no_change_count = 0
            
            # Если несколько раз подряд ничего не изменилось, прекращаем прокрутку
            if no_change_count >= 3:
                log_debug(f"АвтоПитер: прекращаем прокрутку после {scroll_attempts} попыток (нет изменений)")
                break
        
        # Дополнительная прокрутка: вверх, затем постепенно вниз для гарантированной загрузки
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # Постепенная прокрутка вниз для загрузки всех элементов
        scroll_step = 500
        current_position = 0
        max_position = driver.execute_script("return document.body.scrollHeight")
        
        while current_position < max_position:
            current_position += scroll_step
            driver.execute_script(f"window.scrollTo(0, {current_position});")
            time.sleep(0.3)
        
        # Финальная прокрутка в самый низ
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # Явное ожидание появления всех строк таблицы
        try:
            wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, 'div[class*="IndividualTableRow"]')) > 0)
        except TimeoutException:
            log_debug(f"АвтоПитер: таймаут ожидания строк таблицы для {artikul}")
        
        # Финальная проверка количества строк
        try:
            final_rows = driver.find_elements(By.CSS_SELECTOR, 'div[class*="IndividualTableRow"]')
            log_debug(f"АвтоПитер: итоговое количество строк в таблице: {len(final_rows)}")
        except Exception as e:
            log_debug(f"Ошибка подсчета строк: {str(e)}")
        
        # Получаем ПОЛНЫЙ HTML после всех подгрузок
        full_html = driver.page_source
        
        # Парсим бренды из полного HTML
        return parse_autopiter_response(full_html, artikul)
        
    except Exception as e:
        log_debug(f"Ошибка Selenium парсинга АвтоПитер: {str(e)}")
        return []
    finally:
        if driver:
            return_driver_to_pool(driver)
        shutil.rmtree(temp_dir, ignore_errors=True)

def get_brands_by_artikul(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """Получает бренды с Autopiter по артикулу - ТОЛЬКО HTTP ЗАПРОСЫ (без Selenium)"""
    try:
        log_debug(f"АвтоПитер: начинаем парсинг {artikul}")
        
        # Используем только HTTP-запросы (без Selenium)
        url = f"https://autopiter.ru/goods/{quote(artikul)}"
        
        # Используем сессию для сохранения cookies
        session = requests.Session()
        session.headers.update({
            **HEADERS,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })
        
        # Настройка прокси, если указан
        if proxy:
            if isinstance(proxy, str):
                if proxy.startswith('http://'):
                    proxy = proxy[7:]  # Убираем 'http://'
                proxy_dict = {
                    'http': f'http://{proxy}',
                    'https': f'http://{proxy}'
                }
                session.proxies.update(proxy_dict)
                log_debug(f"АвтоПитер: использование прокси {proxy}")
        
        # Добавляем случайную задержку
        time.sleep(random.uniform(1, 3))
        
        response = session.get(url, timeout=15)
        
        if response.status_code == 200:
            brands = parse_autopiter_response(response.text, artikul)
            log_debug(f"АвтоПитер requests: найдено {len(brands)} брендов")
            return brands
        
        log_debug(f"АвтоПитер: HTTP {response.status_code} для {artikul}")
        return []
        
    except Exception as e:
        log_debug(f"Ошибка АвтоПитер для {artikul}: {str(e)}")
        return []

def parse_autopiter_response(html_content: str, artikul: str) -> List[str]:
    """
    Парсит ответ Autopiter и извлекает бренды используя точный селектор
    """
    brands = set()
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        brand_exclude_tokens = [
            'сверла', 'свечи', 'автошина', 'заклепка', 'игла',
            'лейка', 'лента', 'помпа', 'поплавок', 'ремень',
            'фильтр', 'хомут', 'шина', 'щетка', 'кольцо',
            'комплект', 'костюм', 'стартер', 'шайба', 'деталь',
            'накладка', 'тормозная', 'задняя', 'колесо',
            'производители', 'часто ищут', 'рекомендуем', 'сверла техмаш',
            'тестовый', 'клиента', 'без артикула', 'оригинальная',
            'дизель', 'дизеля', 'дизельный',
            'запчасть', 'китай', 'россия', 'россий', 'китайск',
            'производитель', 'бренд', 'артикул', 'номер', 'код',
            'наименование', 'название', 'описание',
            # Слова из описаний товаров, которые не должны быть брендами
            'между', 'металл', 'накала', 'накаливания', 'накаткой',
            'муфта', 'муфтой', 'рулевой', 'колонки', 'набор', 'бит', 'сталь',
            'насос', 'гур', 'передней', 'рессоры', 'задне', 'задней', 'задни',
            'втулка', 'кронштейн', 'осью', 'lh', 'rh', 'левая', 'правая',
            'передняя', 'задняя', 'верхняя', 'нижняя', 'боковая',
            'сцепления', 'диск', 'вала', 'карданный', 'подвесн',
            'свеча', 'накаливания', 'накала'
        ]

        def register_brand(value: Optional[str], source: str = '') -> None:
            brand = (value or '').strip()
            if not brand or len(brand) <= 1 or len(brand) >= 50:
                return
            brand_lower = brand.lower()
            
            # Исключаем чисто цифровые значения
            if brand_lower.isdigit():
                return
            
            # Исключаем служебные слова - проверяем точное совпадение И подстроку
            # Сначала проверяем точное совпадение (более строгая проверка)
            if brand_lower in brand_exclude_tokens:
                return
            # Затем проверяем, является ли бренд частью исключаемых слов
            if any(exclude in brand_lower for exclude in brand_exclude_tokens):
                return
            # Также проверяем обратное - является ли исключаемое слово частью бренда
            if any(brand_lower in exclude for exclude in brand_exclude_tokens if len(exclude) > len(brand_lower)):
                return
            
            # Исключаем артикулы, начинающиеся с определенных префиксов
            if brand_lower.startswith('12643') or brand_lower.startswith('d-') or brand_lower.startswith('dz'):
                return
            
            # Исключаем значения, начинающиеся с цифр (скорее всего артикулы)
            if brand[0].isdigit():
                return
            
            # Исключаем артикулы с форматом типа "43050.810", "DZ1560160020", "BAY15d", "MZ-005"
            # Проверяем, если больше 50% символов - цифры или дефисы/точки, то это артикул
            digit_and_separator_count = sum(1 for c in brand if c.isdigit() or c in '-./')
            if digit_and_separator_count > len(brand) * 0.5:
                return
            
            # Исключаем короткие коды типа "BAY15d", "MZ-005", "NI-007" (2-3 буквы + цифры)
            if len(brand) <= 10 and re.match(r'^[A-Z]{2,3}[-]?\d+[A-Z]?$', brand, re.IGNORECASE):
                return
            
            # Исключаем артикулы с форматом "XXX-XXX" где много цифр
            if re.match(r'^[A-Z0-9]{2,}[-/][A-Z0-9]{2,}', brand, re.IGNORECASE):
                # Проверяем, если больше 40% цифр, то это артикул
                digit_count = sum(1 for c in brand if c.isdigit())
                if digit_count > len(brand) * 0.4:
                    return
            
            # Исключаем значения, где первые 3 символа содержат цифры (скорее всего артикулы)
            if any(char.isdigit() for char in brand[:3]):
                return
            
            # Исключаем слишком короткие значения (меньше 2 символов) или слишком длинные
            if len(brand) < 2 or len(brand) > 50:
                return
            
            # Исключаем артикулы с форматом "2911033G1080", "2912021LE058", "2206010A86AD"
            # Паттерн: начинается с цифр, затем буквы, затем цифры (или наоборот)
            if re.match(r'^\d+[A-Z]+\d+', brand, re.IGNORECASE) or re.match(r'^[A-Z]+\d+[A-Z]+\d+', brand, re.IGNORECASE):
                return
            
            # Исключаем артикулы с форматом типа "2911033G", "2206010A" (много цифр + одна буква)
            if re.match(r'^\d{6,}[A-Z]{1,3}$', brand, re.IGNORECASE):
                return
            
            # Исключаем артикулы с форматом типа "G1080", "LE058" (буквы + цифры, если цифр больше 3)
            if re.match(r'^[A-Z]{1,4}\d{4,}$', brand, re.IGNORECASE):
                return
            
            # Исключаем значения, состоящие только из заглавных букв и цифр без пробелов (скорее всего артикулы)
            if brand.isupper() and not ' ' in brand and any(c.isdigit() for c in brand) and len(brand) > 5:
                digit_ratio = sum(1 for c in brand if c.isdigit()) / len(brand)
                if digit_ratio > 0.3:  # Если больше 30% цифр, то это артикул
                    return
                
            # Исключаем артикулы, где больше 60% символов - цифры (даже если есть буквы)
            digit_count = sum(1 for c in brand if c.isdigit())
            if digit_count > len(brand) * 0.6:
                return
            
            # Исключаем фразы из описаний (содержат пробелы и русские слова)
            # Если бренд содержит пробелы и состоит в основном из русских букв - это описание, а не бренд
            if ' ' in brand:
                russian_chars = sum(1 for c in brand if 'а' <= c.lower() <= 'я' or c.lower() == 'ё')
                total_chars = sum(1 for c in brand if c.isalpha())
                if total_chars > 0 and russian_chars / total_chars > 0.7:
                    # Это русская фраза из описания, а не бренд
                    return
            
            # Исключаем слова, которые начинаются с заглавной буквы и состоят только из русских букв
            # (обычно это слова из описаний, а не бренды)
            if brand[0].isupper() and all('а' <= c.lower() <= 'я' or c.lower() == 'ё' or c == ' ' for c in brand):
                # Проверяем, не является ли это известным брендом
                known_russian_brands = {'автокомпонент', 'автокомпонент плюс', 'автодеталь'}
                if brand_lower not in known_russian_brands:
                    return
            
            brands.add(brand)
            if source:
                log_debug(f"Autopiter: найден бренд '{brand}' ({source}) для {artikul}")
        
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
        
        log_debug(f"Autopiter: найдено {len(rows)} строк IndividualTableRow для {artikul}")
        
        # Проходим по всем строкам и ищем infoColumn с точным селектором
        for row_idx, row in enumerate(rows):
            info_column = row.select_one('div[class*="IndividualTableRow__infoColumn"]')
            if info_column:
                # Собираем все возможные тексты из строки для поиска бренда
                all_texts_in_row = []
                
                # 1. Используем точный селектор: span > span > span > span
                brand_spans = info_column.select('span > span > span > span')
                for span in brand_spans:
                    brand_text = span.get_text(strip=True)
                    if brand_text:
                        all_texts_in_row.append(brand_text)
        
                # 2. Пробуем через title
                brand_spans_title = info_column.select('span[title]')
                for span in brand_spans_title:
                    title_text = span.get('title')
                    if title_text:
                        all_texts_in_row.append(title_text)
                
                # 3. Пробуем все span внутри infoColumn
                all_spans = info_column.select('span')
                for span in all_spans:
                    span_text = span.get_text(strip=True)
                    if span_text and len(span_text) > 1 and len(span_text) < 50:
                        all_texts_in_row.append(span_text)
                
                # 4. Пробуем получить текст напрямую из infoColumn
                direct_text = info_column.get_text(strip=True, separator=' ')
                if direct_text:
                    # Разбиваем на слова и проверяем каждое
                    words = direct_text.split()
                    for word in words:
                        if len(word) > 1 and len(word) < 50:
                            all_texts_in_row.append(word)
                
                # Регистрируем все найденные тексты как потенциальные бренды
                for text in all_texts_in_row:
                    register_brand(text, f"строка {row_idx + 1}")

        # Дополнительно собираем бренды из блока "Производители" (чипы над таблицей)
        brand_chip_selectors = [
            "div[class*='Brands_root'] span[class*='ModalButton__button']",
            "div[class*='Brands_root'] span[title]",
            "div[class*='Brands_root'] a",
            "div[class*='Brands_root'] button",
        ]
        for selector in brand_chip_selectors:
            for element in soup.select(selector):
                text = element.get('title') or element.get_text(strip=True)
                register_brand(text, "блок производителей")
        
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
            
        # Разделяем по различным разделителям (включая запятую)
        separators = [', ', ',', ' / ', '/', ' & ', '&', ' + ', '+', ' - ', '-', ' | ', '|']
        
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
        
        # Если нет разделителей, пробуем разделить по заглавным буквам
        if not has_separator:
            # Ищем паттерны типа "BPWSKUBATRUCKMAX" -> "BPW", "SKUBA", "TRUCKMAX"
            if brand_clean.isupper() and len(brand_clean) > 10:
                # Разделяем по заглавным буквам, но сохраняем известные бренды
                known_brands = ['BPW', 'SKUBA', 'TRUCKMAX', 'DAF', 'OPEL', 'FORD', 'MANSONS', 'TRP', 
                               'BLUMAQ', 'EXOVO', 'SAMPASCANIA', 'SIMPECO', 'FRUEHAUF', 'GIGANT', 
                               'SMB', 'EUROPARTS', 'AFURAL', 'AIC', 'ASAMAUGER', 'DDA', 'FACET',
                               'FAW', 'HINO', 'ISUZU', 'MARSHALL', 'PARTS', 'RENAULT', 'RVI', 'VOLVO',
                               'SCANIA', 'VAN WEZEL', 'SAAB', 'SCHLIECKMANN', 'AIRSTAL', 'AUGER', 
                               'AURADIA', 'AUTOGAMMA', 'CARGO', 'AKINTECH', 'ABALAD', 'KUHNER',
                               'ANALOG DEVICES', 'ARVIN ROSI', 'CONELASTRA', 'CARDONE']
                
                # Сначала проверяем, есть ли известные бренды
                found_known = False
                for known_brand in known_brands:
                    if known_brand in brand_clean:
                        result.add(known_brand)
                        found_known = True
                
                # Если не нашли известные, пробуем разделить по заглавным
                if not found_known:
                    # Разделяем по заглавным буквам, но не разбиваем короткие части
                    parts = re.findall(r'[A-Z][a-z]*', brand_clean)
                    if len(parts) > 1:
                        for part in parts:
                            if len(part) > 2:
                                result.add(part)
                    else:
                        result.add(brand_clean)
                else:
                    result.add(brand_clean)
            else:
                result.add(brand_clean)
    
    return sorted(list(result))

def get_brands_by_artikul_armtek(artikul: str, proxy: Optional[str] = None, logger=None) -> List[str]:
	"""Получает бренды с Armtek по артикулу, используя только Selenium (быстро и стабильно)."""
	try:
		log_debug(f"Armtek: начало обработки артикула {artikul}")

		# 1) Selenium без прокси — самый быстрый путь
		brands_sel = parse_armtek_selenium(artikul, None)
		if brands_sel:
			return filter_armtek_brands(split_combined_brands(brands_sel))

		# 2) Selenium с прокси — если без прокси пусто
		if not proxy:
			proxy_dict = get_next_proxy()
			if proxy_dict:
				proxy_url = proxy_dict.get('http', '')
				if proxy_url.startswith('http://'):
					proxy_url = proxy_url[7:]
				proxy = proxy_url
				log_debug(f"Armtek: автоматически получен прокси: {proxy}")
		if proxy:
			brands_sel = parse_armtek_selenium(artikul, proxy)
			if brands_sel:
				return filter_armtek_brands(split_combined_brands(brands_sel))

		msg = f"Armtek: бренды не найдены для {artikul}"
		log_debug(msg)
		if logger:
			try:
				logger(msg)
			except Exception:
				pass
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

def parse_armtek_api_fallback(artikul: str, proxies: Optional[List[str]] = None) -> List[str]:
	"""API fallback для Armtek - извлекает бренды через HTTP запросы к странице"""
	brands = set()
	
	try:
		# Используем прямое обращение к странице поиска
		search_url = f"https://armtek.ru/search?text={artikul}"
		log_debug(f"Armtek API fallback: запрос к {search_url}")
		
		# Пробуем с разными прокси
		proxy_list = proxies or [None]
		
		for proxy in proxy_list:
			try:
				log_debug(f"Armtek API fallback: пробуем с прокси {proxy}")
				response = make_request(search_url, proxy, timeout=15)
				if response and response.status_code == 200:
					content = response.text
					log_debug(f"Armtek API fallback: получен ответ {len(content)} символов")
					
					# Ищем бренды в HTML через регулярные выражения
					import re
					
					# Расширенные паттерны для поиска брендов в HTML
					brand_patterns = [
						r'data-brand="([^"]+)"',
						r'"brand":\s*"([^"]+)"',
						r'class="brand[^"]*">\s*([^<]+)',
						r'<span[^>]*brand[^>]*>([^<]+)</span>',
						r'<div[^>]*brand[^>]*>([^<]+)</div>',
						r'class="font__caption1[^"]*brand[^"]*">\s*([^<]+)',
						r'class="pin-brand-name[^"]*">\s*([^<]+)',
						r'class="product-brand[^"]*">\s*([^<]+)',
						r'class="manufacturer[^"]*">\s*([^<]+)',
						r'class="vendor[^"]*">\s*([^<]+)',
						# Поиск в JSON данных
						r'"make":\s*"([^"]+)"',
						r'"manufacturer":\s*"([^"]+)"',
						r'"vendor":\s*"([^"]+)"',
					]
					
					for pattern in brand_patterns:
						matches = re.findall(pattern, content, re.IGNORECASE)
						for match in matches:
							brand = match.strip()
							if brand and len(brand) > 1 and len(brand) < 50:
								# Фильтруем артикулы и технические строки
								if not re.match(r'^[A-Z0-9\-]+$', brand) and not brand.lower() in ['артикул', 'бренд', 'цена', 'brand', 'manufacturer', 'vendor']:
									brands.add(brand)
									log_debug(f"Armtek API fallback: найден бренд '{brand}' по паттерну")
					
					# Дополнительный поиск через BeautifulSoup
					try:
						from bs4 import BeautifulSoup
						soup = BeautifulSoup(content, 'html.parser')
						
						# Ищем по селекторам
						selectors = [
							'.font__caption1.brand--selectable',
							'.pin-brand-name span',
							'.product-card .brand-name',
							'.catalog-item .brand-name',
							'[data-brand]',
							'.brand-name',
							'.product-brand',
							'.manufacturer-name',
							'.vendor-title'
						]
						
						for selector in selectors:
							elements = soup.select(selector)
							for el in elements:
								text = el.get_text(strip=True)
								if text and len(text) > 1 and len(text) < 50:
									if not re.match(r'^[A-Z0-9\-]+$', text) and not text.lower() in ['артикул', 'бренд', 'цена', 'brand', 'manufacturer', 'vendor']:
										brands.add(text)
										log_debug(f"Armtek API fallback: найден бренд '{text}' через BeautifulSoup")
					except Exception as e:
						log_debug(f"Armtek API fallback: ошибка BeautifulSoup: {str(e)}")
					
					if brands:
						log_debug(f"Armtek API fallback: найдено {len(brands)} брендов через HTTP парсинг")
						break
					else:
						log_debug("Armtek API fallback: бренды не найдены в HTML")
						
			except Exception as e:
				log_debug(f"Ошибка HTTP запроса к Armtek с прокси {proxy}: {str(e)}")
				continue
				
	except Exception as e:
		log_debug(f"Общая ошибка API fallback для Armtek: {str(e)}")
	
	return list(brands)

def parse_armtek_selenium(artikul: str, proxy: Optional[str] = None, logger=None) -> List[str]:
	"""Selenium-парсинг Armtek: ждем появления элементов и собираем бренды.
	Если на странице отображено сообщение "По вашему запросу ничего не найдено",
	возвращаем пустой список и логируем событие.
	"""
	brands: Set[str] = set()
	driver = None
	
	try:
		log_debug(f"Armtek Selenium: запуск для артикула {artikul}")
		
		# Получаем драйвер из пула или создаем новый
		driver = get_driver_from_pool()
		if driver is None:
			log_debug("Armtek Selenium: создаем новый драйвер")
			driver = _create_chrome_driver_robust(None, proxy)
			if driver is None:
				log_debug("Armtek Selenium: не удалось создать драйвер")
				return []
		
		# Если прокси содержит авторизацию, игнорируем его для Selenium (Chrome не поддерживает в CLI)
		effective_proxy = None if (proxy and '@' in proxy) else proxy
		
		url = f"https://armtek.ru/search?text={artikul}"
		log_debug(f"Armtek Selenium: загружаем URL {url}")
		
		# Retry логика для загрузки страницы с улучшенной обработкой ошибок
		for page_attempt in range(DRIVER_TIMEOUT_RETRIES):
			try:
				driver.get(url)
				log_debug(f"Armtek Selenium: страница загружена, попытка {page_attempt + 1}")
				break
			except Exception as e:
				error_msg = str(e)
				log_debug(f"Попытка {page_attempt + 1} загрузки страницы: {error_msg}")
				
				# Если произошла критическая ошибка (tab crashed), пересоздаем драйвер
				if "tab crashed" in error_msg.lower() or "chrome not reachable" in error_msg.lower() or "connection refused" in error_msg.lower():
					log_debug("Критическая ошибка Chrome, пересоздаем драйвер")
					try:
						# Закрываем сломанный драйвер
						if driver:
							try:
								driver.quit()
							except:
								pass
						
						# Очищаем процессы Chrome
						import subprocess
						subprocess.run(['pkill', '-f', 'chrome'], capture_output=True)
						subprocess.run(['pkill', '-f', 'chromedriver'], capture_output=True)
						
						# Создаем новый драйвер
						driver = _create_chrome_driver_robust(None, proxy)
						log_debug("Создан новый драйвер после критической ошибки")
						
						# Пробуем загрузить страницу с новым драйвером
						driver.get(url)
						break
					except Exception as recovery_error:
						log_debug(f"Не удалось восстановить драйвер: {str(recovery_error)}")
						return []
				
				if page_attempt < DRIVER_TIMEOUT_RETRIES - 1:
					time.sleep(2)  # Увеличиваем паузу между попытками
				else:
					log_debug("Не удалось загрузить страницу после всех попыток")
					return []
		
		# Явные ожидания появления результатов с улучшенной логикой
		wait = WebDriverWait(driver, SELENIUM_TIMEOUT)
		selectors_to_wait = [
			# Основные контейнеры результатов
			(By.CSS_SELECTOR, '.results'),
			(By.CSS_SELECTOR, '.search-results'),
			(By.CSS_SELECTOR, '.results-list__items'),
			# Бренды - обновленные селекторы
			(By.CSS_SELECTOR, 'span.font__body2.brand--selecting'),
			(By.CSS_SELECTOR, '.brand--selecting'),
			(By.CSS_SELECTOR, '.font__caption1.brand--selectable'),
			# Карточки товаров
			(By.CSS_SELECTOR, '.product-card'),
			(By.CSS_SELECTOR, '.catalog-item'),
			(By.CSS_SELECTOR, 'project-ui-article-card'),
			# Более общие селекторы для fallback
			(By.CSS_SELECTOR, '[class*="result"]'),
			(By.CSS_SELECTOR, '[class*="item"]'),
		]
		
		page_loaded = False
		# Ограничиваем количество попыток для ускорения
		max_attempts = min(5, len(selectors_to_wait))
		for i, (by, sel) in enumerate(selectors_to_wait[:max_attempts]):
			try:
				# Ждем видимости, а не только наличия в DOM
				wait.until(EC.visibility_of_any_elements_located((by, sel)))
				log_debug(f"Armtek Selenium: найден элемент {sel}")
				page_loaded = True
				break
			except Exception as e:
				log_debug(f"Armtek Selenium: элемент {sel} не найден: {str(e)}")
				continue
		
		if not page_loaded:
			log_debug("Armtek Selenium: страница не загрузилась или нет результатов")
			# Сохраняем HTML для отладки
			try:
				html_content = driver.page_source
				debug_file = f"/tmp/armtek_debug_{artikul}.html"
				with open(debug_file, 'w', encoding='utf-8') as f:
					f.write(html_content)
				log_debug(f"Armtek Selenium: HTML сохранен в {debug_file}")
			except Exception as e:
				log_debug(f"Armtek Selenium: не удалось сохранить HTML: {str(e)}")
			
			# Пробуем fallback - ждем просто загрузки страницы
			try:
				WebDriverWait(driver, 2).until(lambda d: d.execute_script("return document.readyState") == "complete")
				log_debug("Armtek Selenium: страница загружена, но нет ожидаемых элементов")
			except Exception:
				log_debug("Armtek Selenium: страница не загрузилась полностью")
				return []
		
		# Быстрая прокрутка страницы для подгрузки контента
		try:
			driver.execute_script('window.scrollTo(0, document.body.scrollHeight/2);')
			time.sleep(0.05)
			driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
			time.sleep(0.05)
		except Exception:
			pass
		
		# Ранний выход: проверяем блок "ничего не найдено"
		try:
			# Несколько надежных путей для текста "ничего не найдено"
			nf = driver.find_elements(By.CSS_SELECTOR, 'div.not-found__title p.font__headline5, p.font__headline5')
			if not nf:
				nf = driver.find_elements(By.XPATH, "//p[contains(@class,'font__headline5') and contains(translate(., 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ', 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'), 'ничего не найдено')]")
			if any('ничего не найдено' in (el.text or '').lower() for el in nf):
				msg = f"Armtek: по запросу {artikul} ничего не найдено"
				log_debug(msg)
				if logger:
					try:
						logger(msg)
					except Exception:
						pass
				return []
		except Exception:
			pass

		# Сбор брендов по селекторам - сначала точные селекторы для карточек товаров
		brand_selectors = [
			# Новые селекторы для современного Armtek
			'.font__caption1.brand--selectable',
			'.pin-brand-name span.font__caption1.brand--selectable',
			'.product-card__content .pin-brand-name .brand--selectable',
			'.pin-brand-name .brand--selectable',
			'.product-card .brand-name',
			'.catalog-item .brand-name',
			'.item-card .brand-name',
			# Точный селектор, предоставленный пользователем
			'body > app-root > div > mp-main > search-result > div > div > project-ui-search-result-with-filters > div > div.results.has-filter-on-desktop > project-ui-search-result > div > div > div.results-list__items.ng-star-inserted > div > div:nth-child(2) > project-ui-article-card > project-ui-article-card-with-suggestions > div > div.content > div.row.ng-star-inserted > div > div.item.item-mobile > span.font__body2.brand--selecting',
			# Селекторы для брендов в карточках товаров
			'.font__body2.brand--selecting',
			'.brand--selecting',
			'.brand-name',
			'.product-brand',
			'.manufacturer-name',
			'.vendor-title',
			'.item-brand',
			'.brand__name',
			# Дополнительные селекторы
			'[data-brand]',
			'.product-card [data-brand]',
			'.catalog-item [data-brand]',
			'.item-card [data-brand]',
			# Селекторы для текста брендов
			'.product-card .font__caption1',
			'.catalog-item .font__caption1',
			'.item-card .font__caption1',
		]

		# Определяем границу секции "Возможные замены" и функцию проверки порядка элементов в DOM
		replacements_header_el = None
		def is_before_replacements(element) -> bool:
			try:
				if replacements_header_el is None:
					return True
				# element.compareDocumentPosition(header) & 4 => element находится перед header
				pos = driver.execute_script("return arguments[0].compareDocumentPosition(arguments[1]);", element, replacements_header_el)
				return bool(int(pos) & 4)
			except Exception:
				return True

		try:
			# Ищем заголовок секции "Возможные замены"
			repl_headers = driver.find_elements(
				By.XPATH,
				"//p[contains(@class,'font__headline6') and contains(normalize-space(.), 'Возможные замены')]"
			)
			if repl_headers:
				replacements_header_el = repl_headers[0]
				log_debug("Armtek Selenium: найдена секция 'Возможные замены'")
		except Exception:
			pass
		
		# Сначала пробуем точные селекторы карточек товаров
		exact_selectors = [
			# Основные селекторы брендов (по скриншоту пользователя)
			'span.font__body2.brand--selecting',
			'.brand--selecting',
			'.font__caption1.brand--selectable',
			# Бренды в карточках товаров
			'.product-card .brand-name',
			'.catalog-item .brand-name',
			'.item-card .brand-name',
			'.pin-brand-name span.font__caption1.brand--selectable',
			'.product-card__content .pin-brand-name .brand--selectable',
			# Более общие селекторы
			'div.results-list__items span.font__body2.brand--selecting',
			'[class*="brand"]',
			'[data-brand]',
		]
		
		log_debug(f"Armtek Selenium: начинаем поиск брендов по {len(exact_selectors)} точным селекторам")
		
		for selector in exact_selectors:
			try:
				elements = driver.find_elements(By.CSS_SELECTOR, selector)
				log_debug(f"Armtek Selenium: найдено {len(elements)} элементов по селектору '{selector}'")
				
				for el in elements:
					text = el.text.strip()
					if text and len(text) > 1 and len(text) < 50:  # Ограничиваем длину
						# Исключаем элементы, находящиеся после секции "Возможные замены"
						if not is_before_replacements(el):
							log_debug(f"Armtek Selenium: пропускаем элемент '{text}' - находится после секции замен")
							continue
						# Дополнительная фильтрация мусора
						if not any(garbage in text.lower() for garbage in [
							'canvas', 'date', 'end', 'error', 'function', 'manager', 'max', 'tag', 'test',
							'unsupported', 'vin', 'whatsapp', 'telegram', 'google', 'gtm', 'scroll', 'wrap',
							'автозапчасти', 'аккумуляторы', 'аксессуары', 'акции', 'бренды', 'ваш', 'возврат',
							'войти', 'выбор', 'вывод', 'гараж', 'гарантийная', 'главная', 'госномеру',
							'грузовые', 'дней', 'доставка', 'инструмент', 'интернет', 'искать', 'искомый',
							'как', 'каталог', 'китайские', 'компании', 'контакты', 'корзина', 'легковые',
							'магазины', 'москва', 'мотозапчасти', 'моторные', 'мы', 'нет', 'новости', 'ооо',
							'оплата', 'оптовым', 'партнерам', 'планировщик', 'по', 'подбор', 'пожалуйста',
							'поиск', 'покупателям', 'поставщикам', 'правовая', 'программа', 'работа',
							'результаты', 'реклама', 'сортировать', 'срок', 'хорошо', 'цена', 'шины'
						]):
							brands.add(text)
							log_debug(f"Armtek Selenium: найден бренд '{text}' по селектору '{selector}'")
						else:
							log_debug(f"Armtek Selenium: пропускаем мусорный текст '{text}'")
				
				# Ранний выход при нахождении достаточного количества брендов
				if len(brands) >= 3:
					log_debug(f"Armtek Selenium: найдено достаточно брендов ({len(brands)}), прерываем поиск")
					break
			except Exception as e:
				log_debug(f"Armtek Selenium: ошибка поиска по селектору {selector}: {str(e)}")
		
		# Если точные селекторы не дали результатов, пробуем упрощенный поиск
		if not brands:
			log_debug("Armtek Selenium: точные селекторы не дали результатов, пробуем упрощенный поиск")
			# Упрощенный поиск - только основные селекторы для ускорения
			simple_selectors = [
				'span[class*="brand"]',
				'div[class*="brand"]',
				'[data-brand]',
				'.font__body2',
				'.font__caption1'
			]
			
			for selector in simple_selectors:
				try:
					elements = driver.find_elements(By.CSS_SELECTOR, selector)
					log_debug(f"Armtek Selenium: найдено {len(elements)} элементов по селектору '{selector}'")
					
					for el in elements:
						text = el.text.strip()
						if text and len(text) > 1 and len(text) < 50:
							# Простая фильтрация для ускорения
							if text.isalpha() or (len(text) <= 15 and any(c.isalpha() for c in text)):
								brands.add(text)
								log_debug(f"Armtek Selenium: найден бренд '{text}' по селектору '{selector}'")
					
					# Ранний выход при нахождении брендов
					if brands:
						break
				except Exception as e:
					log_debug(f"Armtek Selenium: ошибка поиска по селектору {selector}: {str(e)}")
		
		# Если брендов нет — пробуем из HTML и XPath
		if not brands:
			log_debug("Armtek Selenium: селекторы не дали результатов, пробуем парсинг HTML/XPath")
			# 1) XPath вариант извлечения брендов
			try:
				xpath_elems = driver.find_elements(By.XPATH, "//div[contains(@class,'results-list__items')]//span[contains(@class,'brand--selecting') or contains(@class,'brand-name')]")
				for el in xpath_elems:
					text = (el.text or '').strip()
					if text and 1 < len(text) < 50:
						brands.add(text)
			except Exception:
				pass

			# 2) HTML эвристика
			if not brands:
				page_source = driver.page_source
				html_brands = parse_armtek_page_text(page_source, artikul)
				if html_brands:
					brands.update(html_brands)
					log_debug(f"Armtek Selenium: найдено {len(html_brands)} брендов из HTML")
				else:
					log_debug("Armtek Selenium: HTML парсинг тоже не дал результатов")
		
		return list(brands)
	finally:
		# Возвращаем драйвер в пул вместо закрытия
		if driver:
			return_driver_to_pool(driver)
	
	# Fallback: если Selenium не сработал, пробуем API
	if not brands:
		log_debug(f"Armtek Selenium не сработал для {artikul}, пробуем API fallback")
		try:
			# Получаем прокси для API fallback
			proxy_list = []
			if proxy:
				proxy_list.append(proxy)
			else:
				proxy_dict = get_next_proxy()
				if proxy_dict:
					proxy_url = proxy_dict.get('http', '')
					if proxy_url.startswith('http://'):
						proxy_url = proxy_url[7:]
					proxy_list.append(proxy_url)
			
			api_brands = parse_armtek_api_fallback(artikul, proxy_list)
			if api_brands:
				log_debug(f"Armtek API fallback: найдено {len(api_brands)} брендов для {artikul}")
				return api_brands
			else:
				log_debug(f"Armtek API fallback: бренды не найдены для {artikul}")
		except Exception as e:
			log_debug(f"Armtek API fallback тоже не сработал: {str(e)}")
	
	if brands:
		log_debug(f"Armtek Selenium: итого найдено {len(brands)} брендов для {artikul}")
	else:
		log_debug(f"Armtek Selenium: бренды не найдены для {artikul}")
	
	return sorted(brands)

def _create_chrome_driver_robust(temp_dir: str, proxy: Optional[str] = None) -> Optional[webdriver.Chrome]:
    """Создает Chrome драйвер с улучшенной обработкой ошибок и retry логикой"""
    for attempt in range(DRIVER_CREATION_RETRIES):
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Дополнительные настройки для стабильности
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-plugins')
            chrome_options.add_argument('--disable-images')
            # Не отключаем JS/CSS для Armtek: часть структуры и видимости управляется Angular
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            chrome_options.add_argument('--memory-pressure-off')
            chrome_options.add_argument('--max_old_space_size=4096')
            
            # Добавляем user-data-dir для стабильности сессий
            chrome_options.add_argument(f'--user-data-dir={temp_dir}')
            
            # Настройка прокси
            if proxy:
                if '@' in proxy:
                    # Формат: login:password@ip:port
                    auth_part, proxy_part = proxy.split('@', 1)
                    if ':' in auth_part:
                        username, password = auth_part.split(':', 1)
                        # Для Chrome с аутентификацией прокси используем расширение
                        chrome_options.add_argument(f'--proxy-server={proxy_part}')
                        # Добавляем расширение для аутентификации прокси
                        chrome_options.add_argument('--load-extension=/tmp/proxy-auth-extension')
                    else:
                        chrome_options.add_argument(f'--proxy-server={proxy}')
                else:
                    # Формат: ip:port
                    chrome_options.add_argument(f'--proxy-server={proxy}')
                
                log_debug(f"Armtek Selenium: добавлен прокси {proxy}")
            
            # Дополнительные опции для стабильности и производительности
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-plugins')
            chrome_options.add_argument('--disable-images')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_argument('--disable-background-timer-throttling')
            chrome_options.add_argument('--disable-backgrounding-occluded-windows')
            chrome_options.add_argument('--disable-renderer-backgrounding')
            chrome_options.add_argument('--disable-features=TranslateUI')
            chrome_options.add_argument('--disable-ipc-flooding-protection')
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--no-default-browser-check')
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_argument('--disable-gpu-logging')
            chrome_options.add_argument('--silent')
            chrome_options.add_argument('--disable-crash-reporter')
            chrome_options.add_argument('--disable-in-process-stack-traces')
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_argument('--disable-dev-tools')
            chrome_options.add_argument('--disable-software-rasterizer')
            
            # Пытаемся найти ChromeDriver в разных местах
            service = None
            chrome_paths = [
                '/usr/bin/chromedriver',
                '/usr/local/bin/chromedriver',
                'chromedriver',
                './chromedriver'
            ]
            
            for chrome_path in chrome_paths:
                try:
                    service = Service(executable_path=chrome_path)
                    break
                except Exception:
                    continue
            
            if service is None:
                service = Service()  # Автоопределение
            
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Устанавливаем таймауты
            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            driver.implicitly_wait(1)  # Еще больше уменьшаем для ускорения
            
            return driver
            
        except Exception as e:
            log_debug(f"Попытка {attempt + 1} создания Chrome драйвера: {str(e)}")
            if attempt < DRIVER_CREATION_RETRIES - 1:
                time.sleep(2 ** attempt)  # Экспоненциальная задержка
            else:
                log_debug(f"Не удалось создать Chrome драйвер после {DRIVER_CREATION_RETRIES} попыток")
                return None
    
    return None

def _create_chrome_driver(temp_dir: str, with_user_data: bool = True, proxy: Optional[str] = None):
    """Создает Chrome драйвер с настройками и прокси (для обратной совместимости)"""
    return _create_chrome_driver_robust(temp_dir, proxy)

def _create_chrome_driver_minimal(temp_dir: str, proxy: Optional[str] = None):
    """Создает Chrome драйвер с минимальными настройками и прокси"""
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        
        # Настройка прокси
        if proxy:
            if '@' in proxy:
                # Формат: login:password@ip:port
                auth_part, proxy_part = proxy.split('@', 1)
                if ':' in auth_part:
                    username, password = auth_part.split(':', 1)
                    # Для Chrome с аутентификацией прокси используем расширение
                    chrome_options.add_argument(f'--proxy-server={proxy_part}')
                    # Добавляем расширение для аутентификации прокси
                    chrome_options.add_argument('--load-extension=/tmp/proxy-auth-extension')
                else:
                    chrome_options.add_argument(f'--proxy-server={proxy}')
            else:
                # Формат: ip:port
                chrome_options.add_argument(f'--proxy-server={proxy}')
            
            log_debug(f"Armtek Selenium: добавлен прокси {proxy}")
        
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Устанавливаем таймауты
        driver.set_page_load_timeout(15)
        driver.implicitly_wait(5)
        
        return driver
        
    except Exception as e:
        log_debug(f"Ошибка создания минимального Chrome драйвера: {str(e)}")
        return None

def parse_armtek_page_text(page_text: str, artikul: str) -> set:
    """Парсит бренды из текста страницы Armtek с улучшенной фильтрацией"""
    brands = set()
    
    # Список мусорных слов для исключения
    garbage_words = {
        'canvas', 'date', 'end', 'error', 'function', 'manager', 'max', 'tag', 'test',
        'unsupported', 'vin', 'whatsapp', 'telegram', 'google', 'gtm', 'scroll', 'wrap',
        'автозапчасти', 'аккумуляторы', 'аксессуары', 'акции', 'бренды', 'ваш', 'возврат',
        'войти', 'выбор', 'вывод', 'гараж', 'гарантийная', 'главная', 'госномеру',
        'грузовые', 'дней', 'доставка', 'инструмент', 'интернет', 'искать', 'искомый',
        'как', 'каталог', 'китайские', 'компании', 'контакты', 'корзина', 'легковые',
        'магазины', 'москва', 'мотозапчасти', 'моторные', 'мы', 'нет', 'новости', 'ооо',
        'оплата', 'оптовым', 'партнерам', 'планировщик', 'по', 'подбор', 'пожалуйста',
        'поиск', 'покупателям', 'поставщикам', 'правовая', 'программа', 'работа',
        'результаты', 'реклама', 'сортировать', 'срок', 'хорошо', 'цена', 'шины',
        'armtekparts', 'armtekru', 'canvastext', 'roboto', 'ldwbs', 'oracj', 'twmh'
    }
    
    # Паттерны для поиска брендов в HTML атрибутах
    brand_patterns = [
        r'data-brand="([^"]+)"',
        r'brand["\s]*[:=]\s*["\']([^"\']+)["\']',
        r'производитель["\s]*[:=]\s*["\']([^"\']+)["\']',
        r'бренд["\s]*[:=]\s*["\']([^"\']+)["\']',
        r'brand-name="([^"]+)"',
        r'manufacturer="([^"]+)"',
        r'vendor="([^"]+)"',
    ]
    
    for pattern in brand_patterns:
        for match in re.findall(pattern, page_text, re.IGNORECASE):
            if match and len(match) > 1 and len(match) < 50:
                brand = match.strip()
                if brand.lower() not in garbage_words:
                    brands.add(brand)
    
    # Дополнительная эвристика: слова-бренды (латиница/кириллица) с улучшенной фильтрацией
    for word in re.findall(r'\b[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z0-9-]{1,19}\b', page_text):
        if (len(word) > 1 and len(word) < 50 and 
            not word.isdigit() and 
            word.lower() not in garbage_words and
            not any(char.isdigit() for char in word[:2])):  # Исключаем артикулы
            brands.add(word)
    
    return brands

def parse_armtek_http(artikul: str, proxy: Optional[Union[str, Dict[str, str]]] = None) -> List[str]:
    """Парсинг Armtek через HTTP запрос с улучшенной обработкой"""
    url = f"https://armtek.ru/search?text={quote(artikul)}"
    log_debug(f"Armtek HTTP: запрос к {url}")
    
    response = make_request(url, proxy, cache_key=f"armtek_http_{artikul}")
    if not response:
        return []
    
    html_text = response.text
    # Диагностика: проверим наличие ключевых классов в HTML
    try:
        if 'brand--selectable' not in html_text and 'brand--selecting' not in html_text:
            log_debug("Armtek HTTP: в HTML нет brand--selectable/brand--selecting — возможно, страница SSR без нужных блоков или требуется JS")
    except Exception:
        pass
    soup = BeautifulSoup(html_text, 'html.parser')
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
        # Точные и актуальные селекторы из интерфейса Armtek
        '.pin-brand-name span.font__caption1.brand--selectable',
        '.font__caption1.brand--selectable',
        'div.pin-brand-name .brand--selectable',
        # Структурные источники бренда
        '.product-card__brand',
        '[itemprop="brand"]',
        '.catalog-item__brand',
        '[data-brand]'
    ]
    
    for selector in brand_selectors:
        try:
            for tag in soup.select(selector):
                brand = tag.get_text(strip=True)
                if brand and 1 < len(brand) < 50 and not brand.isdigit():
                    brands.add(brand)
        except Exception:
            continue
    
    # Узкие регулярки по ожидаемым классам/атрибутам
    if not brands:
        try:
            regex_patterns = [
                r'class=\"font__caption1\s+brand--selectable\"[^>]*>([^<]+)</span>',
                r'pin-brand-name[^<]+class=\"font__caption1\s+brand--selectable\"[^>]*>([^<]+)</span>',
                r'data-brand=\"([^\"]+)\"'
            ]
            for rp in regex_patterns:
                for m in re.findall(rp, html_text):
                    val = (m or '').strip()
                    if val and 1 < len(val) < 50 and not val.isdigit():
                        brands.add(val)
        except Exception:
            pass
    
    return sorted(brands) if brands else []

def filter_armtek_brands(brands: List[str]) -> List[str]:
	"""Фильтрация брендов Armtek с минимальной очисткой от мусора"""
	filtered: List[str] = []
	
	# Минимальный список мусорных слов - только самые очевидные
	garbage_words = {
		'canvas', 'date', 'end', 'error', 'function', 'manager', 'max', 'tag', 'test',
		'unsupported', 'vin', 'whatsapp', 'telegram', 'google', 'gtm', 'scroll', 'wrap',
		'armtekparts', 'armtekru', 'canvastext', 'roboto', 'ldwbs', 'oracj', 'twmh',
		'brand', 'new', 'test', 'tag', 'date', 'end', 'error', 'function', 'manager',
		# Только самые очевидные мусорные слова из интерфейса
		'главная', 'войти', 'корзина', 'каталог', 'поиск', 'новости', 'акции',
		'контакты', 'о компании', 'правовая информация', 'программа лояльности',
		# Паразитные фрагменты из SSR/шифрования
		'nxmupi', 'wti'
	}
	
	for b in brands:
		brand = b.strip()
		if not brand:
			continue
			
		# Базовая фильтрация мусора
		if len(brand) < 2 or len(brand) > 50:
			continue
		if brand.isdigit():
			continue
		if brand.lower() in garbage_words:
			continue
			
		# Убираем только очевидные артикулы (начинающиеся с цифр)
		if brand[0].isdigit() and len(brand) > 3:
			continue

		# Убираем строки с непонятной смесью регистров типа NxMUPi, WtI
		letters_only = re.sub(r'[^A-Za-zА-Яа-яЁё]', '', brand)
		if 2 <= len(letters_only) <= 6 and re.search(r'[A-Z][a-z][A-Z]', brand):
			continue
			
		filtered.append(brand)
		
	return sorted(set(filtered))

def parse_armtek_http_response(html: str, artikul: str) -> List[str]:
	"""Парсит HTML ответа Armtek, извлекая бренды"""
	soup = BeautifulSoup(html, 'html.parser')
	brands: Set[str] = set()
	
	# 1) Явные селекторы
	selectors = [
		'.font__body2.brand--selecting',
		'.brand--selecting',
		'.brand-name', '.product-brand', '.manufacturer-name',
		'.vendor-title', '.item-brand', '.brand__name',
		'.catalog-item__brand', '.product__brand', '.item__brand'
	]
	for sel in selectors:
		for el in soup.select(sel):
			text = el.get_text(strip=True)
			if text:
				brands.add(text)
	
	# 2) data-brand
	for el in soup.find_all(attrs={"data-brand": True}):
		val = (el.get("data-brand") or '').strip()
		if val:
			brands.add(val)
	
	# 3) JSON-LD/скрипты
	for script in soup.find_all('script'):
		if not script.string:
			continue
		for m in re.findall(r'"brand"\s*:\s*"([^"]+)"', script.string):
			m = m.strip()
			if m:
				brands.add(m)
	
	# 4) Текстовая эвристика (с поддержкой кириллицы)
	if not brands:
		text_content = soup.get_text(" ")
		for word in re.findall(r'\b[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z0-9-]{1,19}\b', text_content):
			if len(word) > 1 and not word.isdigit():
				brands.add(word)
	
	filtered = filter_armtek_brands(list(brands))
	log_debug(f"Armtek HTTP: найдено {len(filtered)} брендов для {artikul}")
	return filtered

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
        max_total_attempts = 3  # Уменьшаем количество попыток для ускорения
        
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
                                timeout=5,  # Еще больше уменьшаем таймаут
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
                        time.sleep(0.1)  # Уменьшаем паузу для ускорения
                
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

def parse_armtek_alternative(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """Альтернативный метод парсинга Armtek через различные эндпоинты"""
    alternative_urls = [
        f"https://armtek.ru/catalog/search?q={artikul}",
        f"https://armtek.ru/products/search?query={artikul}",
        f"https://armtek.ru/search?q={artikul}",
        f"https://armtek.ru/catalog?search={artikul}",
        f"https://armtek.ru/search?query={artikul}",
        f"https://armtek.ru/catalog/search?query={artikul}",
        f"https://armtek.ru/products?search={artikul}",
        f"https://armtek.ru/items?q={artikul}"
    ]
    
    for url in alternative_urls:
        try:
            log_debug(f"Armtek альтернативный: пробуем {url}")
            response = make_request(url, proxy, max_retries=1)
            if response and response.status_code == 200:
                brands = parse_armtek_http_response(response.text, artikul)
                if brands:
                    log_debug(f"Armtek альтернативный: найдено {len(brands)} брендов на {url}")
                    return brands
        except Exception as e:
            log_debug(f"Ошибка запроса для {url}: {str(e)} (попытка 1)")
            continue
    
    log_debug(f"Armtek альтернативный: все эндпоинты не дали результатов для {artikul}")
    return []

# Вспомогательные методы для работы с пулом драйверов Armtek
def _create_chrome_driver_minimal():
    """Создает минимальный Chrome драйвер для Armtek"""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-images')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    # Уникальная временная директория для каждого драйвера
    temp_dir = os.path.join(tempfile.gettempdir(), f'chrome_armtek_{uuid.uuid4().hex[:8]}')
    options.add_argument(f'--user-data-dir={temp_dir}')
    
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        driver.implicitly_wait(2)
        return driver
    except Exception as e:
        log_debug(f"Ошибка создания драйвера: {str(e)}")
        return None

def _parse_with_driver(artikul: str, driver):
    """Парсит Armtek с использованием существующего драйвера"""
    try:
        url = f"https://armtek.ru/search?text={quote(artikul)}"
        driver.get(url)
        
        # Ждем загрузки страницы
        time.sleep(2)
        
        # Проверяем на "ничего не найдено"
        page_text = driver.page_source.lower()
        if 'ничего не найдено' in page_text or 'не найдено' in page_text:
            return []
        
        # Ищем бренды по селекторам
        brands = set()
        
        # Основные селекторы для брендов
        selectors = [
            '.font__body2.brand--selecting',
            '.brand--selecting',
            '[data-brand]',
            '.brand-name'
        ]
        
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    brand_text = elem.text.strip()
                    if brand_text and len(brand_text) > 1:
                        brands.add(brand_text.upper())
            except Exception:
                continue
        
        # Если ничего не найдено, пробуем парсинг по тексту
        if not brands:
            brands = parse_armtek_page_text(driver.page_source)
        
        return list(brands)
        
    except Exception as e:
        log_debug(f"Ошибка парсинга с драйвером для {artikul}: {str(e)}")
        return []

# Добавляем методы к функции get_brands_by_artikul_armtek
get_brands_by_artikul_armtek._create_chrome_driver_minimal = _create_chrome_driver_minimal
get_brands_by_artikul_armtek._parse_with_driver = _parse_with_driver

def parse_armtek_cross_numbers(artikul: str, proxy: Optional[str] = None, logger=None) -> List[str]:
	"""Selenium-парсинг Armtek: ищем реальные кросс-номера вместо выдуманных артикулов"""
	cross_numbers: Set[str] = set()
	temp_dir = tempfile.mkdtemp(prefix=f"chrome_armtek_{uuid.uuid4().hex[:8]}_")
	try:
		log_debug(f"Armtek Selenium: поиск кросс-номеров для артикула {artikul}")
		# Если прокси содержит авторизацию, игнорируем его для Selenium (Chrome не поддерживает в CLI)
		effective_proxy = None if (proxy and '@' in proxy) else proxy
		driver = _create_chrome_driver(temp_dir=temp_dir, with_user_data=True, proxy=effective_proxy)
		if driver is None:
			log_debug("Armtek Selenium: не удалось создать драйвер")
			return []
		url = f"https://armtek.ru/search?text={artikul}"
		driver.get(url)
		
		# Явные ожидания появления результатов
		wait = WebDriverWait(driver, SELENIUM_TIMEOUT)
		selectors_to_wait = [
			(By.CSS_SELECTOR, '.results-list__items'),
			(By.CSS_SELECTOR, '.font__body2.brand--selecting'),
			(By.CSS_SELECTOR, '.font__caption1.brand--selectable'),
		]
		for by, sel in selectors_to_wait:
			try:
				wait.until(EC.presence_of_element_located((by, sel)))
				break
			except Exception:
				continue
		
		# Прокручиваем страницу для подгрузки
		try:
			driver.execute_script('window.scrollTo(0, document.body.scrollHeight/2);')
			time.sleep(0.2)
			driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
			time.sleep(0.2)
		except Exception:
			pass
		
		# Ранний выход: проверяем блок "ничего не найдено"
		try:
			nf = driver.find_elements(By.CSS_SELECTOR, 'div.not-found__title p.font__headline5, p.font__headline5')
			if any('ничего не найдено' in (el.text or '').lower() for el in nf):
				msg = f"Armtek: по запросу {artikul} ничего не найдено"
				log_debug(msg)
				if logger:
					try:
						logger(msg)
					except Exception:
						pass
				return []
		except Exception:
			pass

		# Ищем реальные кросс-номера в карточках товаров
		try:
			# Ищем артикулы в карточках товаров
			article_selectors = [
				'.product-card__article',
				'.article-number',
				'.product-article',
				'.item-article',
				'.catalog-item__article',
				'[data-article]',
				'.font__caption1.article--selectable',
			]
			
			for selector in article_selectors:
				try:
					elements = driver.find_elements(By.CSS_SELECTOR, selector)
					for el in elements:
						text = el.text.strip()
						if text and len(text) > 3 and len(text) < 30:
							# Проверяем, что это похоже на артикул
							if re.match(r'^[A-Z0-9\-\.]+$', text):
								cross_numbers.add(text)
								log_debug(f"Armtek: найден кросс-номер '{text}' по селектору '{selector}'")
				except Exception as e:
					log_debug(f"Armtek Selenium: ошибка поиска по селектору {selector}: {str(e)}")
			
			# Если не нашли артикулы, ищем в тексте карточек
			if not cross_numbers:
				try:
					product_cards = driver.find_elements(By.CSS_SELECTOR, '.product-card, .catalog-item, .item-card')
					for card in product_cards:
						card_text = card.text
						# Ищем артикулы в тексте карточки
						articles = re.findall(r'\b[A-Z]{2,}[0-9\-\.]{2,}\b', card_text)
						for article in articles:
							if len(article) > 3 and len(article) < 30:
								cross_numbers.add(article)
								log_debug(f"Armtek: найден кросс-номер '{article}' в тексте карточки")
				except Exception as e:
					log_debug(f"Armtek Selenium: ошибка поиска в карточках: {str(e)}")
			
		except Exception as e:
			log_debug(f"Armtek Selenium: ошибка поиска кросс-номеров: {str(e)}")
		
		# Фильтруем результаты - убираем исходный артикул и слишком похожие
		filtered_cross_numbers = set()
		for cross in cross_numbers:
			if cross != artikul and not cross.startswith(artikul) and not artikul.startswith(cross):
				filtered_cross_numbers.add(cross)
		
		if filtered_cross_numbers:
			log_debug(f"Armtek: найдено {len(filtered_cross_numbers)} уникальных кросс-номеров")
			return sorted(list(filtered_cross_numbers))
		else:
			log_debug("Armtek: кросс-номера не найдены")
			return []
		
	finally:
		try:
			driver.quit()
		except Exception:
			pass
		shutil.rmtree(temp_dir, ignore_errors=True)