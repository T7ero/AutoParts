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
import gc
import signal
import psutil
from collections import deque

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
TIMEOUT = 5
SELENIUM_TIMEOUT = 12
PAGE_LOAD_TIMEOUT = 12

# Настройки для пула драйверов
DRIVER_POOL_SIZE = 2  # Уменьшено для экономии ресурсов
DRIVER_CREATION_RETRIES = 2  # Уменьшено количество попыток
DRIVER_TIMEOUT_RETRIES = 2

# Кеширование
REQUEST_CACHE = {}
CACHE_EXPIRATION = 600
FAILED_REQUESTS_CACHE = {}

# Глобальная переменная для хранения прокси
PROXY_LIST = []
PROXY_INDEX = 0
BAD_PROXIES = set()

# Семафор для ограничения одновременного создания драйверов
DRIVER_CREATION_SEMAPHORE = threading.Semaphore(1)  # Только 1 драйвер создается одновременно

class DriverPool:
    def __init__(self, max_size=2):
        self.max_size = max_size
        self.available = deque()
        self.in_use = set()
        self.lock = threading.Lock()
        self.creation_lock = threading.Lock()
        self.driver_temp_dirs = {}  # Для отслеживания временных директорий
        
    def get_driver(self) -> Optional[webdriver.Chrome]:
        """Получает драйвер из пула"""
        with self.lock:
            # Пытаемся взять доступный драйвер
            while self.available:
                driver, temp_dir = self.available.popleft()
                if self._is_driver_usable(driver):
                    self.in_use.add(id(driver))
                    log_debug(f"Взят драйвер из пула, доступно: {len(self.available)}, используется: {len(self.in_use)}")
                    return driver
                else:
                    try:
                        driver.quit()
                        # Очищаем временную директорию
                        if temp_dir and os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir, ignore_errors=True)
                    except:
                        pass
            
            # Если нет доступных, создаем новый (с ограничением)
            if len(self.in_use) < self.max_size:
                with self.creation_lock:
                    log_debug("Создание нового драйвера...")
                    result = self._create_new_driver()
                    if result:
                        driver, temp_dir = result
                        self.in_use.add(id(driver))
                        self.driver_temp_dirs[id(driver)] = temp_dir
                        log_debug(f"Создан новый драйвер, используется: {len(self.in_use)}")
                        return driver
            
            log_debug("Не удалось получить драйвер - пул переполнен")
            return None
    
    def return_driver(self, driver: Optional[webdriver.Chrome]):
        """Возвращает драйвер в пул"""
        if driver is None:
            return
            
        with self.lock:
            driver_id = id(driver)
            if driver_id in self.in_use:
                self.in_use.remove(driver_id)
                
                if self._is_driver_usable(driver) and len(self.available) < self.max_size:
                    temp_dir = self.driver_temp_dirs.get(driver_id)
                    self.available.append((driver, temp_dir))
                    log_debug(f"Драйвер возвращен в пул, доступно: {len(self.available)}, используется: {len(self.in_use)}")
                else:
                    try:
                        driver.quit()
                        # Очищаем временную директорию
                        temp_dir = self.driver_temp_dirs.pop(driver_id, None)
                        if temp_dir and os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception as e:
                        log_debug(f"Ошибка при закрытии драйвера: {str(e)}")
    
    def _is_driver_usable(self, driver: webdriver.Chrome) -> bool:
        """Проверяет, можно ли использовать драйвер"""
        try:
            # Простая проверка, что драйвер еще работает
            driver.current_url
            return True
        except Exception:
            return False
    
    def _create_new_driver(self) -> Optional[Tuple[webdriver.Chrome, str]]:
        """Создает новый драйвер"""
        with DRIVER_CREATION_SEMAPHORE:
            temp_dir = tempfile.mkdtemp(prefix=f"chrome_pool_{uuid.uuid4().hex[:8]}_")
            for attempt in range(DRIVER_CREATION_RETRIES):
                try:
                    driver = _create_chrome_driver_robust(temp_dir)
                    if driver:
                        return driver, temp_dir
                    time.sleep(1)
                except Exception as e:
                    log_debug(f"Попытка {attempt + 1} создания драйвера: {str(e)}")
                    if attempt < DRIVER_CREATION_RETRIES - 1:
                        time.sleep(2 ** attempt)
            
            # Если не удалось создать драйвер, очищаем временную директорию
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            return None
    
    def cleanup(self):
        """Полная очистка пула"""
        with self.lock:
            log_debug("Очистка пула драйверов...")
            while self.available:
                try:
                    driver, temp_dir = self.available.popleft()
                    driver.quit()
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
                except:
                    pass
            
            # Закрываем используемые драйверы
            for driver_id in list(self.in_use):
                try:
                    # Не можем закрыть используемые драйверы, просто удаляем из отслеживания
                    temp_dir = self.driver_temp_dirs.pop(driver_id, None)
                    if temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
                except:
                    pass
            
            self.in_use.clear()
            self.driver_temp_dirs.clear()

# Инициализация пула драйверов
DRIVER_POOL = DriverPool(max_size=DRIVER_POOL_SIZE)

def log_debug(message):
    print(f"[DEBUG] {message}")

def get_driver_from_pool() -> Optional[webdriver.Chrome]:
    """Получает драйвер из пула"""
    return DRIVER_POOL.get_driver()

def return_driver_to_pool(driver: webdriver.Chrome):
    """Возвращает драйвер в пул"""
    DRIVER_POOL.return_driver(driver)

def cleanup_driver_pool():
    """Очищает пул драйверов"""
    DRIVER_POOL.cleanup()

def force_cleanup_chrome_processes():
    """Принудительная очистка процессов Chrome"""
    try:
        log_debug("Принудительная очистка процессов Chrome...")
        
        # Используем psutil для более надежного поиска процессов
        chrome_processes = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                proc_name = proc.info['name'].lower() if proc.info['name'] else ''
                if any(name in proc_name for name in ['chrome', 'chromedriver', 'chromium']):
                    chrome_processes.append(proc)
                    log_debug(f"Найден процесс: {proc.info['name']} (PID: {proc.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Убиваем процессы
        for proc in chrome_processes:
            try:
                proc.kill()
                log_debug(f"Убит процесс: {proc.info['name']} (PID: {proc.info['pid']})")
            except Exception as e:
                log_debug(f"Не удалось убить процесс {proc.info['pid']}: {str(e)}")
        
        # Дополнительная очистка через subprocess
        for process_name in ['chrome', 'chromedriver', 'chromium']:
            try:
                subprocess.run(['pkill', '-9', '-f', process_name], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            except:
                pass
        
        # Очищаем временные директории
        temp_patterns = [
            '.com.google.Chrome*',
            '.org.chromium.Chromium*',
            'chrome_*',
            'chromium_*',
            'tmp*'
        ]
        
        for pattern in temp_patterns:
            try:
                subprocess.run(['find', '/tmp', '-name', pattern, '-type', 'd', '-exec', 'rm', '-rf', '{}', '+'], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            except:
                pass
        
        time.sleep(1)
        log_debug("Принудительная очистка завершена")
        
    except Exception as e:
        log_debug(f"Ошибка принудительной очистки: {str(e)}")

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
    """Помечает прокси как проблемный"""
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
        proxy_url = proxy_dict.get('http', '')
        if proxy_url.startswith('http://'):
            return proxy_url[7:]
    return None

def cleanup_chrome_processes():
    """Очищает процессы Chrome и временные директории"""
    try:
        force_cleanup_chrome_processes()
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
    """Выполняет HTTP-запрос с поддержкой прокси и повторными попытками"""

    # Настройка сессии
    session = requests.Session()
    
    # Настройка прокси
    if proxy:
        if isinstance(proxy, dict):
            session.proxies.update(proxy)
            log_debug("Используется словарь прокси")
        else:
            if '@' in proxy:
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
    
    # Настройка заголовков
    session.headers.update(HEADERS)
    
    # Выполнение запроса с повторными попытками
    for attempt in range(1, max_retries + 1):
        try:
            log_debug(f"Попытка {attempt} {'с прокси' if proxy else 'без прокси'} для {url}")
            
            response = session.get(url, timeout=timeout, allow_redirects=True)
            
            if response.status_code == 200:
                return response
            elif response.status_code == 403:
                log_debug(f"403 Forbidden для {url} (попытка {attempt})")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
            elif response.status_code == 429:
                log_debug(f"429 Rate Limit для {url} (попытка {attempt})")
                if attempt < max_retries:
                    time.sleep(5 * attempt)
                    continue
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
    """Парсит ответ Autopiter и извлекает бренды"""
    brands = set()
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Используем ТОЧНЫЙ селектор из DevTools пользователя
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
                        if (len(brand) < 50 and 
                            not any(exclude in brand.lower() for exclude in [
                                'сверла', 'свечи', 'автошина', 'заклепка', 'игла', 
                                'лейка', 'лента', 'помпа', 'поплавок', 'ремень', 
                                'фильтр', 'хомут', 'шина', 'щетка', 'кольцо',
                                'комплект', 'костюм', 'стартер', 'шайба', 'деталь',
                                'накладка', 'тормозная', 'задняя', 'комплект', 'колесо',
                                'производители', 'часто ищут', 'рекомендуем', 'сверла техмаш',
                                'тестовый', 'клиента', 'без артикула', 'оригинальная',
                                'дизель', 'дизеля', 'дизельный'
                            ]) and
                            not brand.lower().startswith('12643') and
                            not brand.lower().startswith('d-') and
                            not any(char.isdigit() for char in brand[:3])
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
                                    'тестовый', 'клиента', 'без артикула', 'оригинальная',
                                    'дизель', 'дизеля', 'дизельный'
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
        
        # Если нет разделителей, пробуем разделить по заглавным буквам
        if not has_separator:
            if brand_clean.isupper() and len(brand_clean) > 10:
                known_brands = ['BPW', 'SKUBA', 'TRUCKMAX', 'DAF', 'OPEL', 'FORD', 'MANSONS', 'TRP', 
                               'BLUMAQ', 'EXOVO', 'SAMPASCANIA', 'SIMPECO', 'FRUEHAUF', 'GIGANT', 
                               'SMB', 'EUROPARTS', 'AFURAL', 'AIC', 'ASAMAUGER', 'DDA', 'FACET',
                               'FAW', 'HINO', 'ISUZU', 'MARSHALL', 'PARTS', 'RENAULT', 'RVI', 'VOLVO',
                               'SCANIA', 'VAN WEZEL', 'SAAB', 'SCHLIECKMANN', 'AIRSTAL', 'AUGER', 
                               'AURADIA', 'AUTOGAMMA', 'CARGO', 'AKINTECH', 'ABALAD', 'KUHNER',
                               'ANALOG DEVICES', 'ARVIN ROSI', 'CONELASTRA', 'CARDONE']
                
                found_known = False
                for known_brand in known_brands:
                    if known_brand in brand_clean:
                        result.add(known_brand)
                        found_known = True
                
                if not found_known:
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
    """Получает бренды с Armtek по артикулу"""
    try:
        log_debug(f"Armtek: начало обработки артикула {artikul}")

        # 1) Selenium без прокси — самый быстрый путь
        brands_sel = parse_armtek_selenium(artikul, None, logger)
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
            brands_sel = parse_armtek_selenium(artikul, proxy, logger)
            if brands_sel:
                return filter_armtek_brands(split_combined_brands(brands_sel))

        # 3) HTTP fallback
        brands_http = parse_armtek_http_fallback(artikul, proxy)
        if brands_http:
            return filter_armtek_brands(split_combined_brands(brands_http))

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

def parse_armtek_http_fallback(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """HTTP fallback для Armtek"""
    try:
        url = f"https://armtek.ru/search?text={quote(artikul)}"
        log_debug(f"Armtek HTTP fallback: запрос к {url}")
        
        response = make_request(url, proxy, timeout=10)
        if response and response.status_code == 200:
            return parse_armtek_http_response(response.text, artikul)
    except Exception as e:
        log_debug(f"Ошибка HTTP fallback для Armtek: {str(e)}")
    
    return []

def parse_armtek_selenium(artikul: str, proxy: Optional[str] = None, logger=None) -> List[str]:
    """Selenium-парсинг Armtek"""
    brands: Set[str] = set()
    driver = None
    
    try:
        log_debug(f"Armtek Selenium: запуск для артикула {artikul}")
        
        # Получаем драйвер из пула
        driver = get_driver_from_pool()
        if driver is None:
            log_debug("Armtek Selenium: не удалось получить драйвер из пула")
            return []
        
        # Если прокси содержит авторизацию, игнорируем его для Selenium
        effective_proxy = None if (proxy and '@' in proxy) else proxy
        
        url = f"https://armtek.ru/search?text={artikul}"
        log_debug(f"Armtek Selenium: загружаем URL {url}")
        
        # Retry логика для загрузки страницы
        for page_attempt in range(DRIVER_TIMEOUT_RETRIES):
            try:
                driver.get(url)
                log_debug(f"Armtek Selenium: страница загружена, попытка {page_attempt + 1}")
                break
            except Exception as e:
                error_msg = str(e)
                log_debug(f"Попытка {page_attempt + 1} загрузки страницы: {error_msg}")
                
                if "tab crashed" in error_msg.lower() or "chrome not reachable" in error_msg.lower():
                    log_debug("Критическая ошибка Chrome, пересоздаем драйвер")
                    try:
                        return_driver_to_pool(driver)
                        driver = None
                        
                        # Очищаем процессы
                        force_cleanup_chrome_processes()
                        
                        # Пробуем получить новый драйвер
                        driver = get_driver_from_pool()
                        if driver:
                            driver.get(url)
                            break
                    except Exception as recovery_error:
                        log_debug(f"Не удалось восстановить драйвер: {str(recovery_error)}")
                        return []
                
                if page_attempt < DRIVER_TIMEOUT_RETRIES - 1:
                    time.sleep(2)
                else:
                    log_debug("Не удалось загрузить страницу после всех попыток")
                    return []
        
        # Явные ожидания появления результатов
        wait = WebDriverWait(driver, SELENIUM_TIMEOUT)
        selectors_to_wait = [
            (By.CSS_SELECTOR, '.results-list__items'),
            (By.CSS_SELECTOR, '.font__body2.brand--selecting'),
            (By.CSS_SELECTOR, '.font__caption1.brand--selectable'),
            (By.CSS_SELECTOR, '.product-card'),
        ]
        
        page_loaded = False
        for by, sel in selectors_to_wait:
            try:
                wait.until(EC.visibility_of_any_elements_located((by, sel)))
                log_debug(f"Armtek Selenium: найден элемент {sel}")
                page_loaded = True
                break
            except Exception as e:
                log_debug(f"Armtek Selenium: элемент {sel} не найден: {str(e)}")
                continue
        
        if not page_loaded:
            log_debug("Armtek Selenium: страница не загрузилась или нет результатов")
            try:
                WebDriverWait(driver, 3).until(lambda d: d.execute_script("return document.readyState") == "complete")
                log_debug("Armtek Selenium: страница загружена, но нет ожидаемых элементов")
            except Exception:
                log_debug("Armtek Selenium: страница не загрузилась полностью")
                return []
        
        # Прокрутка страницы
        try:
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight/3);')
            time.sleep(0.1)
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight*2/3);')
            time.sleep(0.1)
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
            time.sleep(0.1)
        except Exception:
            pass
        
        # Проверяем блок "ничего не найдено"
        try:
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

        # Сбор брендов по селекторам
        brand_selectors = [
            '.font__caption1.brand--selectable',
            '.pin-brand-name span.font__caption1.brand--selectable',
            '.product-card__content .pin-brand-name .brand--selectable',
            '.pin-brand-name .brand--selectable',
            '.product-card .brand-name',
            '.font__body2.brand--selecting',
            '.brand--selecting',
        ]
        
        for selector in brand_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                log_debug(f"Armtek Selenium: найдено {len(elements)} элементов по селектору '{selector}'")
                
                for el in elements:
                    text = el.text.strip()
                    if text and len(text) > 1 and len(text) < 50:
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
            except Exception as e:
                log_debug(f"Armtek Selenium: ошибка поиска по селектору {selector}: {str(e)}")
        
        return list(brands)
        
    except Exception as e:
        log_debug(f"Armtek Selenium: общая ошибка: {str(e)}")
        return []
    finally:
        # Всегда возвращаем драйвер в пул
        if driver:
            return_driver_to_pool(driver)

def _create_chrome_driver_robust(temp_dir: str, proxy: Optional[str] = None) -> Optional[webdriver.Chrome]:
    """Создает Chrome драйвер с улучшенной обработкой ошибок"""
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
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            chrome_options.add_argument('--memory-pressure-off')
            chrome_options.add_argument('--max_old_space_size=4096')
            
            # Добавляем user-data-dir для стабильности сессий
            chrome_options.add_argument(f'--user-data-dir={temp_dir}')
            
            # Настройка прокси
            if proxy and '@' not in proxy:  # Пропускаем прокси с авторизацией
                chrome_options.add_argument(f'--proxy-server={proxy}')
                log_debug(f"Armtek Selenium: добавлен прокси {proxy}")
            
            # Дополнительные опции для стабильности и производительности
            chrome_options.add_argument('--disable-background-timer-throttling')
            chrome_options.add_argument('--disable-backgrounding-occluded-windows')
            chrome_options.add_argument('--disable-renderer-backgrounding')
            chrome_options.add_argument('--disable-features=TranslateUI')
            chrome_options.add_argument('--disable-ipc-flooding-protection')
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--no-default-browser-check')
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_argument('--log-level=3')
            
            # Пытаемся найти ChromeDriver
            service = None
            chrome_paths = [
                '/usr/bin/chromedriver',
                '/usr/local/bin/chromedriver',
                'chromedriver',
                './chromedriver'
            ]
            
            for chrome_path in chrome_paths:
                try:
                    if os.path.exists(chrome_path):
                        service = Service(executable_path=chrome_path)
                        break
                except Exception:
                    continue
            
            if service is None:
                service = Service()  # Автоопределение
            
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Устанавливаем таймауты
            driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            driver.implicitly_wait(1)
            
            return driver
            
        except Exception as e:
            log_debug(f"Попытка {attempt + 1} создания Chrome драйвера: {str(e)}")
            if attempt < DRIVER_CREATION_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                log_debug(f"Не удалось создать Chrome драйвер после {DRIVER_CREATION_RETRIES} попыток")
                return None
    
    return None

def parse_armtek_http_response(html: str, artikul: str) -> List[str]:
    """Парсит HTML ответа Armtek"""
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
    
    # 4) Текстовая эвристика
    if not brands:
        text_content = soup.get_text(" ")
        for word in re.findall(r'\b[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z0-9-]{1,19}\b', text_content):
            if len(word) > 1 and not word.isdigit():
                brands.add(word)
    
    filtered = filter_armtek_brands(list(brands))
    log_debug(f"Armtek HTTP: найдено {len(filtered)} брендов для {artikul}")
    return filtered

def filter_armtek_brands(brands: List[str]) -> List[str]:
    """Фильтрация брендов Armtek"""
    filtered: List[str] = []
    
    garbage_words = {
        'canvas', 'date', 'end', 'error', 'function', 'manager', 'max', 'tag', 'test',
        'unsupported', 'vin', 'whatsapp', 'telegram', 'google', 'gtm', 'scroll', 'wrap',
        'armtekparts', 'armtekru', 'canvastext', 'roboto', 'ldwbs', 'oracj', 'twmh',
        'brand', 'new', 'test', 'tag', 'date', 'end', 'error', 'function', 'manager',
        'главная', 'войти', 'корзина', 'каталог', 'поиск', 'новости', 'акции',
        'контакты', 'о компании', 'правовая информация', 'программа лояльности',
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

        # Убираем строки с непонятной смесью регистров
        letters_only = re.sub(r'[^A-Za-zА-Яа-яЁё]', '', brand)
        if 2 <= len(letters_only) <= 6 and re.search(r'[A-Z][a-z][A-Z]', brand):
            continue
            
        filtered.append(brand)
        
    return sorted(set(filtered))

def get_brands_by_artikul_emex(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """Получает бренды с Emex по артикулу"""
    try:
        encoded_artikul = quote(artikul)
        
        # Ротация User-Agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        ]
        
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://emex.ru/search?detailNum={encoded_artikul}",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        # Подготовим варианты записи артикула
        try:
            raw_num = artikul.strip()
            candidate_nums = list(dict.fromkeys([
                raw_num,
                raw_num.upper(),
                raw_num.replace('-', ''),
                raw_num.replace('-', '').upper(),
            ]))
        except Exception:
            candidate_nums = [artikul]

        # Создаем сессию с прокси
        session = requests.Session()
        session.headers.update(headers)
        
        # Настройка прокси
        proxies = None
        if proxy:
            try:
                if isinstance(proxy, str):
                    if proxy.startswith('http://'):
                        proxy = proxy[7:]
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
            try:
                proxy_dict = get_next_proxy()
                if proxy_dict:
                    session.proxies.update(proxy_dict)
                    log_debug(f"Emex: автоматически получен прокси")
            except Exception as e:
                log_debug(f"Emex: ошибка получения прокси: {str(e)}")
        
        # Устанавливаем куки
        try:
            session.cookies.set("regionId", "263", domain="emex.ru")
            session.cookies.set("locationId", "263", domain="emex.ru")
        except Exception:
            pass
        
        # Прогрев сессии
        try:
            session.get("https://emex.ru/", timeout=5, proxies=proxies)
            time.sleep(0.5)
        except Exception as e:
            log_debug(f"Emex: ошибка прогрева сессии: {str(e)}")
            pass
        
        # Получаем XSRF токен
        xsrf_token = (
            session.cookies.get("XSRF-TOKEN")
            or session.cookies.get("xsrf-token")
            or session.cookies.get("X_XSRF_TOKEN")
        )
        if xsrf_token:
            session.headers.update({"X-XSRF-TOKEN": xsrf_token})

        # Основные попытки
        api_variants = [
            {"showAll": "false", "isHeaderSearch": "true"},
            {"showAll": "true", "isHeaderSearch": "true"},
        ]
        
        total_attempts = 0
        max_total_attempts = 2  # Уменьшено количество попыток
        
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
                    
                    log_debug(f"Emex API: попытка {total_attempts + 1} для {artikul}")
                    
                    response = session.get(
                        api_url,
                        headers=headers,
                        timeout=5,
                        proxies=proxies
                    )
                    
                    total_attempts += 1
                    
                    if response.status_code == 200:
                        content_type = response.headers.get('content-type', '').lower()
                        if 'application/json' in content_type:
                            try:
                                data = response.json()
                                brands = set()
                                
                                search_result = data.get("searchResult", {})
                                if search_result:
                                    makes = search_result.get("makes", {})
                                    if makes:
                                        makes_list = makes.get("list", [])
                                        for item in makes_list:
                                            if isinstance(item, dict):
                                                brand = item.get("make")
                                                if brand and brand.strip():
                                                    brands.add(brand.strip())
                                                    log_debug(f"Emex API: добавлен бренд '{brand}' для {artikul}")
                                    
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
                    
                    elif response.status_code == 429:
                        log_debug(f"Emex API: Rate limit для {artikul}, пропускаем")
                        break
                    elif response.status_code == 403:
                        log_debug(f"Emex API: 403 Forbidden для {artikul}, помечаем прокси как проблемный")
                        try:
                            current_http = session.proxies.get('http') or ''
                            if current_http:
                                mark_proxy_bad(current_http)
                        except Exception:
                            pass
                        new_proxy = get_next_proxy()
                        if new_proxy:
                            session.proxies.update(new_proxy)
                        break
                    
                except requests.exceptions.Timeout:
                    log_debug(f"Emex API: таймаут для {artikul} (попытка {total_attempts})")
                    if total_attempts >= max_total_attempts:
                        log_debug(f"Emex API: слишком много таймаутов для {artikul}, пропускаем")
                        break
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
                    if not proxy:
                        try:
                            new_proxy_dict = get_next_proxy()
                            if new_proxy_dict:
                                session.proxies.update(new_proxy_dict)
                                log_debug(f"Emex API: смена прокси после ошибки")
                        except Exception:
                            pass
                    continue
                
                time.sleep(0.1)

        return []
        
    except Exception as e:
        log_debug(f"Ошибка Emex для {artikul}: {str(e)}")
        return []

# Инициализация прокси при импорте модуля
load_proxies_from_file()

# Функция для глобальной очистки ресурсов
def global_cleanup():
    """Глобальная очистка всех ресурсов"""
    log_debug("Запуск глобальной очистки ресурсов...")
    cleanup_driver_pool()
    force_cleanup_chrome_processes()
    log_debug("Глобальная очистка завершена")

# Регистрируем очистку при завершении
import atexit
atexit.register(global_cleanup)