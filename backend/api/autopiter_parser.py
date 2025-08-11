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
# Уменьшаем таймауты для ускорения работы
TIMEOUT = 10  # Уменьшаем с 15 до 10 секунд для ускорения
SELENIUM_TIMEOUT = 10  # Уменьшаем с 15 до 10 секунд для ускорения
PAGE_LOAD_TIMEOUT = 10  # Уменьшаем с 15 до 10 секунд для ускорения

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
        '.goods-info .brand',
        # Блок "Производители:" на странице товара
        'div:contains("Производители") a',
        'div:contains("Производитель") a'
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
        'автокомпонент', 'камаз', 'корпус межосевого дифференциала', 'нет в наличии', 'или выбрать другой удобный для вас способ',
        'каталоги', 'оплата', 'популярные категории', 'строительство и ремонт', 'электрика и свет',
        'палец sitrak', 'переключатели подрулевые в сборе', 'мтз', 'сад и огород',
        'fmsi', 'ac delco', 'achim', 'achr', 'b-tech', 'beru', 'champion', 'chery', 'dragonzap',
        'ford', 'hot-parts', 'lucas', 'mobis', 'ngk', 'nissan', 'robiton', 'tesla', 'trw', 'vag',
        'valeo', 'auto-comfort', 'autotech', 'createk', 'howo', 'kamaz', 'leo trade', 'prc',
        'shaanxi', 'shacman', 'sitrak', 'weichai', 'zg.link', 'ast', 'foton', 'htp', 'jmc',
        'shaft-gear', 'wayteko', 'zevs', 'jac', 'faw', 'gspartshinotoyota', 'gspartshino',
        'toyota / lexus', 'toyota/lexus', 'gspartshinotoyota / lexus', 'gspartshinotoyota/lexus',
        # Новые мусорные бренды из последних логов
        'new', 'хорошо', 'корзина', 'cookies', 'сайт был лучше', 'лучше', 'был', 'сайт',
        'telegram', 'whatsapp', 'запчасти', 'грузовые', 'сортировать по', 'сортировать',
        'выбор', 'armtek', 'каталог', 'главная', 'подбор', 'гараж', 'войти',
        'мы используем', 'используем', 'чтобы', 'был лучше', 'лучшехорошо',
        'telegramwhatsapp', 'грузовые запчасти', 'выбор armtek', 'сортировать по:выбор armtek',
        'каталогглавнаяподборкорзинагаражвойти', 'мы используем cookies, чтобы сайт был лучшехорошо'
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
            not brand_lower.startswith('возможные замены') and
            not brand_lower.startswith('войти') and
            not brand_lower.startswith('выбор armtek') and
            not brand_lower.startswith('гараж') and
            not brand_lower.startswith('гарантийная политика') and
            not brand_lower.startswith('главная') and
            not brand_lower.startswith('дней') and
            not brand_lower.startswith('доставка') and
            not brand_lower.startswith('инструмент') and
            not brand_lower.startswith('искомый товар') and
            not brand_lower.startswith('как сделать заказ') and
            not brand_lower.startswith('каталог') and
            not brand_lower.startswith('лучшее предложение') and
            not brand_lower.startswith('магазины') and
            not brand_lower.startswith('мы в социальных сетях') and
            not brand_lower.startswith('кислородный датчик') and
            not brand_lower.startswith('датчик кислорода') and
            not brand_lower.startswith('запчасть') and
            not brand_lower.startswith('китай') and
            not brand_lower.startswith('рааз') and
            not brand_lower.startswith('или выбрать другой удобный для') and
            not brand_lower.startswith('каталоги') and
            not brand_lower.startswith('оплата') and
            not brand_lower.startswith('корпус межосевого дифференциала') and
            not brand_lower.startswith('нет в наличии') and
            not brand_lower.startswith('популярные категории') and
            not brand_lower.startswith('строительство и ремонт') and
            not brand_lower.startswith('электрика и свет') and
            not brand_lower.startswith('палец sitrak') and
            not brand_lower.startswith('дизель') and
            not brand_lower.startswith('мтз') and
            not brand_lower.startswith('сад и огород') and
            not brand_lower.startswith('fmsi') and
            not brand_lower.startswith('ac delco') and
            not brand_lower.startswith('achim') and
            not brand_lower.startswith('achr') and
            not brand_lower.startswith('b-tech') and
            not brand_lower.startswith('beru') and
            not brand_lower.startswith('champion') and
            not brand_lower.startswith('chery') and
            not brand_lower.startswith('dragonzap') and
            not brand_lower.startswith('ford') and
            not brand_lower.startswith('hot-parts') and
            not brand_lower.startswith('lucas') and
            not brand_lower.startswith('mobis') and
            not brand_lower.startswith('ngk') and
            not brand_lower.startswith('nissan') and
            not brand_lower.startswith('robiton') and
            not brand_lower.startswith('tesla') and
            not brand_lower.startswith('trw') and
            not brand_lower.startswith('vag') and
            not brand_lower.startswith('valeo') and
            not brand_lower.startswith('auto-comfort') and
            not brand_lower.startswith('autotech') and
            not brand_lower.startswith('createk') and
            not brand_lower.startswith('howo') and
            not brand_lower.startswith('kamaz') and
            not brand_lower.startswith('leo trade') and
            not brand_lower.startswith('prc') and
            not brand_lower.startswith('shaanxi') and
            not brand_lower.startswith('shacman') and
            not brand_lower.startswith('sitrak') and
            not brand_lower.startswith('weichai') and
            not brand_lower.startswith('zg.link') and
            not brand_lower.startswith('ast') and
            not brand_lower.startswith('foton') and
            not brand_lower.startswith('htp') and
            not brand_lower.startswith('jmc') and
            not brand_lower.startswith('shaft-gear') and
            not brand_lower.startswith('wayteko') and
            not brand_lower.startswith('zevs') and
            not brand_lower.startswith('jac') and
            not brand_lower.startswith('faw') and
            not brand_lower.startswith('gspartshinotoyota') and
            not brand_lower.startswith('gspartshino') and
            not brand_lower.startswith('toyota / lexus') and
            not brand_lower.startswith('toyota/lexus') and
            not brand_lower.startswith('gspartshinotoyota / lexus') and
            not brand_lower.startswith('gspartshinotoyota/lexus') and
            # Новые проверки для мусорных брендов из логов
            not brand_lower.startswith('new') and
            not brand_lower.startswith('хорошо') and
            not brand_lower.startswith('telegram') and
            not brand_lower.startswith('whatsapp') and
            not brand_lower.startswith('telegramwhatsapp') and
            not brand_lower.startswith('грузовые') and
            not brand_lower.startswith('сортировать') and
            not brand_lower.startswith('выбор') and
            not brand_lower.startswith('armtek') and
            not brand_lower.startswith('подбор') and
            not brand_lower.startswith('мы используем') and
            not brand_lower.startswith('используем') and
            not brand_lower.startswith('cookies') and
            not brand_lower.startswith('сайт был') and
            not brand_lower.startswith('лучше') and
            not brand_lower.startswith('был') and
            not brand_lower.startswith('сайт') and
            not brand_lower.startswith('чтобы') and
            not brand_lower.startswith('лучшехорошо')):
            filtered_brands.add(brand_clean)
    
    return sorted(list(filtered_brands))

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
    # Белый список разрешенных брендов
    allowed_brands = {
        'QUNZE', 'NIPPON', 'MOTORS MATTO', 'JMC', 'KOBELCO', 'PRC', 
        'HUANG LIN', 'ERISTIC', 'HINO', 'OOTOKO', 'MITSUBISHI', 'TOYOTA',
        'AUTOKAT', 'ZEVS', 'PITWORK', 'HITACHI', 'NISSAN', 'DETOOL', 'CHEMIPRO',
        'STELLOX', 'FURO', 'EDCON', 'REPARTS',
        # Добавлено из пожеланий: считать брендами
        'HTP', 'FVR', 'ISUZU', 'G-BRAKE', 'АККОР', 'ДИЗЕЛЬ'
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
    """Получает бренды с Emex по артикулу"""
    try:
        encoded_artikul = quote(artikul)
        api_url = f"https://emex.ru/api/search/search?detailNum={encoded_artikul}&locationId=263&showAll=false&isHeaderSearch=true"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://emex.ru/search?detailNum={encoded_artikul}",
            "X-Requested-With": "XMLHttpRequest",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            # Исключаем br, чтобы не получать brotli-сжатый ответ, который requests не распакует без доп. зависимостей
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
        }
        
        # Готовим сессию и прогреваем куки/регион и CSRF
        session = requests.Session()
        session.headers.update(headers)
        # Ставим региональные куки явно
        try:
            session.cookies.set("regionId", "263", domain="emex.ru")
            session.cookies.set("locationId", "263", domain="emex.ru")
        except Exception:
            pass
        try:
            # Прогрев главной и страницы поиска, чтобы получить XSRF-TOKEN и прочие необходимые куки
            session.get("https://emex.ru/", timeout=10)
            session.get(f"https://emex.ru/search?detailNum={encoded_artikul}", timeout=10)
            session.get(f"https://emex.ru/products/{encoded_artikul}", timeout=10)
        except Exception:
            pass
        # Пробуем добавить XSRF токен, если он есть в куках
        xsrf_token = (
            session.cookies.get("XSRF-TOKEN")
            or session.cookies.get("xsrf-token")
            or session.cookies.get("X_XSRF_TOKEN")
            or session.cookies.get("csrf-token")
        )
        if xsrf_token:
            session.headers.update({"X-XSRF-TOKEN": xsrf_token})

        # Подготовим варианты записи артикула: как есть, без тире/пробелов, в верхнем регистре
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

        # Сначала пробуем без прокси
        try:
            log_debug(f"[API] Emex: попытка 1 для {artikul}")
            
            # Пробуем разные конфигурации запроса
            for attempt in range(2):
                try:
                    if attempt == 0:
                        # Первая попытка с обычными заголовками
                        response = session.get(
                            api_url,
                            headers=headers,
                            timeout=20
                        )
                    else:
                        # Вторая попытка с отключенным сжатием
                        headers_no_compression = headers.copy()
                        headers_no_compression['Accept-Encoding'] = 'identity'
                        response = session.get(
                            api_url,
                            headers=headers_no_compression,
                            timeout=20
                        )
                    
                    log_debug(f"Emex API: попытка {attempt + 1}, статус {response.status_code} для {artikul}")
                    log_debug(f"Emex API: content-type: {response.headers.get('content-type', 'unknown')}")
                    log_debug(f"Emex API: content-encoding: {response.headers.get('content-encoding', 'none')}")
                    
                    if response.status_code == 200:
                        # Проверяем content-type
                        content_type = response.headers.get('content-type', '').lower()
                        if 'application/json' in content_type:
                            try:
                                # Пробуем декодировать JSON с обработкой сжатия
                                data = response.json()
                                brands = set()
                                
                                # Подробное логирование структуры ответа
                                log_debug(f"Emex API: структура ответа для {artikul}: {list(data.keys()) if isinstance(data, dict) else 'не dict'}")
                                
                                # Обработка структуры ответа Emex
                                search_result = data.get("searchResult", {})
                                if search_result:
                                    log_debug(f"Emex API: searchResult ключи: {list(search_result.keys())}")
                                    
                                    # Проверяем makes - это основной источник брендов
                                    makes = search_result.get("makes", {})
                                    if makes:
                                        makes_list = makes.get("list", [])
                                        log_debug(f"Emex API: найдено {len(makes_list)} makes для {artikul}")
                                        
                                        for item in makes_list:
                                            if isinstance(item, dict):
                                                # Извлекаем бренд из поля "make"
                                                brand = item.get("make")
                                                if brand and brand.strip():
                                                    brands.add(brand.strip())
                                                    log_debug(f"Emex API: добавлен бренд '{brand}' для {artikul}")
                                    # Дополнительно берём бренд из searchResult.make, если он есть
                                    sr_make = search_result.get("make")
                                    if isinstance(sr_make, str) and sr_make.strip():
                                        brands.add(sr_make.strip())
                                        log_debug(f"Emex API: добавлен бренд из searchResult.make '{sr_make}' для {artikul}")
                                
                                # Если не нашли в makes, проверяем details
                                # Для этого эндпоинта бренды находятся в makes.list и в searchResult.make
                                
                                # Если все еще нет брендов, ищем в других полях
                                if not brands:
                                    log_debug(f"Emex API: поиск брендов в других полях для {artikul}")
                                    for key, value in data.items():
                                        if isinstance(value, dict):
                                            for sub_key, sub_value in value.items():
                                                if isinstance(sub_value, list):
                                                    for item in sub_value:
                                                        if isinstance(item, dict) and "make" in item:
                                                            brand = item["make"]
                                                            if brand and brand.strip():
                                                                brands.add(brand.strip())
                                                                log_debug(f"Emex API: добавлен бренд из {key}.{sub_key} '{brand}' для {artikul}")
                                
                                log_debug(f"Emex API: итого найдено {len(brands)} брендов для {artikul}")
                                if brands:
                                    return sorted(list(brands))
                                
                            except json.JSONDecodeError as e:
                                log_debug(f"Emex API: ошибка декодирования JSON для {artikul} (попытка {attempt + 1}): {str(e)}")
                                # Пробуем декодировать как текст и посмотреть что получилось
                                try:
                                    text_content = response.text
                                    log_debug(f"Emex API: первые 200 символов ответа для {artikul}: {text_content[:200]}")
                                    if text_content.startswith('{'):
                                        # Возможно это JSON, но с проблемами кодировки
                                        log_debug(f"Emex API: ответ начинается с {{, пробуем исправить кодировку")
                                        # Пробуем исправить кодировку
                                        try:
                                            data = json.loads(text_content)
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
                                                                log_debug(f"Emex API: добавлен бренд после исправления кодировки '{brand}' для {artikul}")
                                        except Exception:
                                            pass
                                    # Возврат, если удалось собрать бренды
                                    if 'brands' in locals() and brands:
                                        log_debug(f"Emex API: найдено {len(brands)} брендов после исправления кодировки для {artikul}")
                                        return sorted(list(brands))
                                except:
                                    pass
                        log_debug(f"Emex API: ответ для {artikul}: {response.text[:500]}...")
                except requests.exceptions.Timeout:
                    log_debug(f"Emex API: таймаут для {artikul} (попытка {attempt + 1})")
                except requests.exceptions.RequestException as e:
                    log_debug(f"Emex API: ошибка запроса для {artikul} (попытка {attempt + 1}): {str(e)}")
                
                # Если это не последняя попытка, ждем немного
                if attempt < 1:
                    time.sleep(1)
        
            # Дополнительные попытки с разными параметрами и вариантами артикула
            if 'brands' not in locals() or not brands:
                alt_variants = [
                    {"showAll": "false", "isHeaderSearch": "true"},
                    {"showAll": "true", "isHeaderSearch": "true"},
                    {"showAll": "false", "isHeaderSearch": "false"},
                    {"showAll": "true", "isHeaderSearch": "false"},
                ]
                for num in candidate_nums:
                    num_enc = quote(num)
                    for params in alt_variants:
                        try:
                            alt_api_url = (
                                f"https://emex.ru/api/search/search?detailNum={num_enc}"
                                f"&locationId=263&showAll={params['showAll']}&isHeaderSearch={params['isHeaderSearch']}"
                            )
                            response = session.get(alt_api_url, headers=headers, timeout=20)
                            if response.status_code == 200 and 'application/json' in response.headers.get('content-type','').lower():
                                data = response.json()
                                brands = set()
                                search_result = data.get("searchResult", {})
                                makes = (search_result or {}).get("makes", {})
                                makes_list = (makes or {}).get("list", [])
                                for item in makes_list:
                                    if isinstance(item, dict):
                                        brand = item.get("make")
                                        if brand and brand.strip():
                                            brands.add(brand.strip())
                                sr_make = search_result.get("make") if isinstance(search_result, dict) else None
                                if isinstance(sr_make, str) and sr_make.strip():
                                    brands.add(sr_make.strip())
                                if brands:
                                    log_debug(
                                        f"Emex API (alt {params['showAll']}/{params['isHeaderSearch']} num={num}): найдено {len(brands)} брендов для {artikul}"
                                    )
                                    return sorted(list(brands))
                        except Exception as e:
                            log_debug(
                                f"Emex API (alt {params['showAll']}/{params['isHeaderSearch']} num={num}): ошибка {str(e)}"
                            )

        except Exception as e:
            log_debug(f"Emex API: внешняя ошибка при обращении к API без прокси: {str(e)}")

        # Строгая политика: если API не вернул бренды – возвращаем пустой список (без HTTP fallback)
        return []
        
    except Exception as e:
        log_debug(f"Ошибка Emex для {artikul}: {str(e)}")
        return []

# Инициализация прокси при импорте модуля
load_proxies_from_file()