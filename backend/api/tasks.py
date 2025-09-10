import pandas as pd
from celery import shared_task
from django.core.files import File
from core.models import ParsingTask
from .autopiter_parser import (
    get_brands_by_artikul, 
    get_brands_by_artikul_armtek, 
    get_brands_by_artikul_emex, 
    cleanup_chrome_processes,
    cleanup_driver_pool,
    get_next_proxy,
    get_proxy_string,
    load_proxies_from_file,
    log_debug
)
import re
import concurrent.futures
import time
import gc
import threading
import queue
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from typing import List, Dict, Optional
from celery.utils.log import get_task_logger
from datetime import datetime
# Кэш для ускорения работы парсера
PARSER_CACHE = {}
CACHE_EXPIRATION = 3600  # 1 час
NEGATIVE_CACHE_EXPIRATION = 1800  # 30 минут для пустых результатов

def get_cache_key(artikul: str, source: str) -> str:
    """Создает ключ кэша для артикула и источника"""
    return f"{artikul.lower().strip()}_{source}"

def get_from_cache(artikul: str, source: str) -> Optional[List[str]]:
    """Получает результат из кэша"""
    key = get_cache_key(artikul, source)
    if key in PARSER_CACHE:
        cache_entry = PARSER_CACHE[key]
        if time.time() - cache_entry['timestamp'] < cache_entry['expiration']:
            return cache_entry['result']
        else:
            del PARSER_CACHE[key]  # Удаляем устаревшую запись
    return None

def set_cache(artikul: str, source: str, result: List[str], is_empty: bool = False):
    """Сохраняет результат в кэш"""
    key = get_cache_key(artikul, source)
    expiration = NEGATIVE_CACHE_EXPIRATION if is_empty else CACHE_EXPIRATION
    PARSER_CACHE[key] = {
        'result': result,
        'timestamp': time.time(),
        'expiration': expiration
    }

def clean_excel_string(s):
    if not isinstance(s, str):
        return s
    # Удаляем все управляющие символы и недопустимые для Excel символы
    cleaned = re.sub(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]', '', s)
    # Удаляем символы, которые нельзя использовать в Excel
    cleaned = re.sub(r'[\\/*?:\[\]]', '', cleaned)
    # Ограничиваем длину строки для Excel
    if len(cleaned) > 32000:
        cleaned = cleaned[:32000]
    return cleaned

def safe_cell_to_str(value: object) -> str:
    """Безопасно конвертирует ячейку Excel в строку: пусто, если NaN/None."""
    try:
        if value is None:
            return ''
        # pandas NaN/NaT
        if isinstance(value, float) and pd.isna(value):
            return ''
        if pd.isna(value):
            return ''
    except Exception:
        pass
    return str(value).strip()

def normalize_article_for_compare(article: str) -> str:
    """Нормализует артикул для сравнения: верхний регистр, убираем все разделители.
    Также нормализует русские и английские буквы (А/A, В/B, М/M, Р/P, Е/E, О/O, С/C, Х/X, К/K, Н/H).
    """
    if not article:
        return ''
    a = article.upper().strip()
    
    # Маппинг русских букв на английские для унификации
    ru_to_en_map = {
        'А': 'A',  # русская А -> английская A
        'В': 'B',  # русская В -> английская B  
        'М': 'M',  # русская М -> английская M
        'Р': 'P',  # русская Р -> английская P
        'Е': 'E',  # русская Е -> английская E
        'О': 'O',  # русская О -> английская O
        'С': 'C',  # русская С -> английская C
        'Х': 'X',  # русская Х -> английская X
        'К': 'K',  # русская К -> английская K
        'Н': 'H',  # русская Н -> английская H
    }
    
    # Заменяем русские буквы на английские
    for ru_char, en_char in ru_to_en_map.items():
        a = a.replace(ru_char, en_char)
    
    # Убираем все не буквенно-цифровые символы (тире, точки, пробелы, подчеркивания и т.д.)
    a = re.sub(r"[^0-9A-Z]+", "", a)
    return a

def split_compound_article(article: str) -> list:
    """Разбивает составной артикул на отдельные части (например: '55110-48700 551104E700' -> ['5511048700', '551104E700'])"""
    if not article:
        return []
    
    # Нормализуем артикул
    normalized = normalize_article_for_compare(article)
    if not normalized:
        return []
    
    # Ищем составные артикулы (два артикула подряд)
    # Паттерн: цифры+буквы, затем еще цифры+буквы
    parts = []
    
    # Простое разбиение по пробелам в оригинальном артикуле
    original_parts = article.upper().strip().split()
    for part in original_parts:
        clean_part = normalize_article_for_compare(part)
        if clean_part and len(clean_part) >= 3:  # Минимальная длина артикула
            parts.append(clean_part)
    
    # Если не нашли части, возвращаем нормализованный артикул
    if not parts:
        parts = [normalized]
    
    return parts

def normalize_brand_for_compare(brand: str) -> str:
    """Нормализует бренд для сравнения: верхний регистр, только буквы/цифры.
    Убираем пробелы, дефисы, подчеркивания и прочие разделители.
    """
    if not brand:
        return ''
    b = str(brand).upper().strip()
    # Оставляем только буквы и цифры (рус/лат)
    b = re.sub(r"[^0-9A-ZА-ЯЁ]+", "", b)
    return b

def dedupe_rows(rows: list) -> list:
    """Удаляет дубли по ключу (Бренд № 2, Артикул № 2, Источник),
    причем Артикул № 2 разбивается на составные части и нормализуется,
    а бренды приводятся к буквенно-цифровому виду без разделителей.
    Игнорируем различия в 'Бренд № 1', 'Артикул по Бренду № 1', 'Наименование'.
    """
    seen: set = set()
    unique: list = []

    for row in rows:
        brand2_norm = normalize_brand_for_compare(row.get('Бренд № 2', ''))
        source_norm = (row.get('Источник') or '').lower().strip()

        article2_raw = row.get('Артикул по Бренду № 2', '')
        parts = split_compound_article(article2_raw)
        if not parts:
            parts = [normalize_article_for_compare(article2_raw)]

        # Если после нормализации артикул пустой — пропускаем строку
        parts = [p for p in parts if p]
        if not parts:
            continue

        keys = [(brand2_norm, p, source_norm) for p in parts]

        if any(k in seen for k in keys):
            # уже есть один из вариантов — считаем дубликатом
            continue

        for k in keys:
            seen.add(k)

        unique.append(row)

    return unique

def filter_garbage_brands(brands: List[str]) -> List[str]:
    """Фильтрует мусорные бренды из результатов Autopiter и Emex"""
    garbage_words = {
        'артикул', 'тестовый', 'клиента', 'ремень', 'грм', 'без артикула', 'оригинальная',
        'дизель', 'дизеля', 'дизельный',
        'крышка', 'решетки', 'фен', 'строительный', 'полироль', 'mat', 'номер', 'корея',
        'русская', 'артель', 'освар', 'plak', 'zabectuaptukyl', 'zikmar', 'plak',
        'testartikul', 'euroflextestartikul', 'тестовый артикул', 'артикул клиента',
        'артикул №', 'без артикула', 'оригинальная', 'артикул', 'см предыдущий артикул',
        'new', 'хорошо', 'корзина', 'cookies', 'сайт был лучше', 'лучше', 'был', 'сайт',
        'telegram', 'whatsapp', 'запчасти', 'грузовые', 'сортировать по', 'сортировать',
        'выбор', 'armtek', 'каталог', 'главная', 'подбор', 'гараж', 'войти',
        'мы используем', 'используем', 'чтобы', 'был лучше', 'лучшехорошо',
        'как сделать заказ', 'аксессуары', 'dragonflys', 'грузовые запчасти',
        'оплата', 'доставка', 'возврат', 'гарантийная политика', 'контакты',
        'новости', 'акции', 'партнерам', 'поставщикам', 'покупателям', 'реклама на сайте',
        'программа лояльности', 'правовая информация', 'о компании', 'работа в компании',
        'китайские авто', 'новые товары', 'популярные товары', 'сезонные товары',
        'моторные масла', 'аккумуляторы', 'инструмент', 'автохимия', 'автокосметика',
        'автоглушитель', 'автокомпонент', 'автодеталь', 'автокомпонент плюс',
        'автокомпонент', 'компонент', 'автодеталь', 'автокомпонент плюс',
        'наконечник правый', 'наконечник рулевой п', 'наконечник рулевой тяги',
        'pyчнoй тoпливoпoдкaчивaющий нacoc', 'шины и диски', 'колпачок маслосъемный',
        'невский фильтр', 'подушка дизеля боковая', 'сальник распредвала',
        'корпус межосевого дифференциала', 'нет в наличии', 'или выбрать другой удобный для вас способ',
        'каталоги', 'популярные категории', 'строительство и ремонт', 'электрика и свет',
        'палец sitrak', 'переключатели подрулевые в сборе', 'мтз', 'сад и огород',
        'fmsi', 'ac delco', 'achim', 'achr', 'b-tech', 'beru', 'champion', 'chery', 'dragonzap',
        'ford', 'hot-parts', 'lucas', 'mobis', 'ngk', 'nissan', 'robiton', 'tesla', 'trw', 'vag',
        'valeo', 'autotech', 'createk', 'howo', 'kamaz', 'leo trade', 'prc',
        'shaanxi', 'shacman', 'sitrak', 'weichai', 'zg.link', 'ast', 'foton', 'htp', 'jmc',
        'shaft-gear', 'wayteko', 'zevs', 'jac', 'faw', 'gspartshinotoyota', 'gspartshino',
        'toyota / lexus', 'toyota/lexus', 'gspartshinotoyota / lexus', 'gspartshinotoyota/lexus',
        'telegramwhatsapp', 'грузовые запчасти', 'выбор armtekсортировать по:выбор armtek',
        'каталогглавнаяподборкорзинагаражвойти', 'мы используем cookies, чтобы сайт был лучшехорошо',
        'прокладка гбц на hino hino', 'прокладка гбц производства японии', 'прокладка клапанной крышки',
        'колпачок маслосъемный', 'о-кольцо стержня капана (victor reinz)', 'прокладка гбц',
        'прокладка', 'гбц', 'клапанной крышки', 'стержня капана', 'victor reinz', 'кольцо',
        'маслосъемный', 'капана', 'стержня', 'крышки', 'клапанной', 'производства японии',
        'японии', 'производства', 'hino hino', 'на hino', 'гбц на', 'гбц производства',
        'прокладка гбц на', 'прокладка гбц производства', 'прокладка клапанной',
        'о-кольцо стержня', 'кольцо стержня', 'стержня капана (victor reinz)',
        'капана (victor reinz)', '(victor reinz)', 'victor', 'reinz', 'кольцо стержня капана',
        'о-кольцо', 'кольцо', 'стержня', 'капана', 'victor reinz', 'маслосъемный колпачок',
        'колпачок маслосъемный', 'маслосъемный', 'колпачок', 'крышки клапанной',
        'клапанной крышки', 'крышки', 'клапанной', 'производства', 'японии', 'hino',
        'гбц', 'прокладка', 'кольцо', 'стержня', 'капана', 'victor', 'reinz', 'маслосъемный',
        'колпачок', 'крышки', 'клапанной', 'производства', 'японии', 'hino', 'гбц', 'прокладка',
        # Emex specific garbage
        'emex', 'вакансии', 'контакты', 'аккумуляторы', 'возврат', 'вход', 'доставка', 'оплата',
        'корзина', 'найти', 'подобрать', 'деталь', 'компании', 'покупателям', 'поставщикам',
        'санкт-петербург', 'помощь', 'сотрудничество', 'товары', 'шины', 'диски', 'лампы',
        'масла', 'моторные', 'оферта', 'политика', 'cookies', 'использования', 'давайте',
        'эксперт', 'знает', 'лучше', 'результаты', 'поиска', 'номеру', 'детали', 'щетки',
        'стеклоочистителя', 'дилерская сеть', 'свет', 'вход', 'оптового', 'покупателя',
        'персональных', 'данных', 'сотрудничество', 'товары', 'щетки', 'стеклоочистителя'
    }
    
    filtered = []
    # Словарь для объединения составных брендов
    compound_brands = {
        'auto': 'AUTO-COMFORT',
        'comfort': 'AUTO-COMFORT',
        'hot': 'HOT-PARTS',
        'parts': 'HOT-PARTS',
        'g': 'G-BRAKE',
        'brake': 'G-BRAKE',
        'diesel': 'ДИЗЕЛЬ',
        'дизель': 'ДИЗЕЛЬ',
        'zevs': 'ZEVS',
        'z': 'ZEVS'
    }
    
    # Сначала объединяем составные бренды
    processed_brands = set()
    for brand in brands:
        brand_clean = brand.strip()
        if not brand_clean:
            continue
            
        brand_lower = brand_clean.lower()
        
        # Проверяем, является ли это частью составного бренда
        if brand_lower in compound_brands:
            compound_brand = compound_brands[brand_lower]
            if compound_brand not in processed_brands:
                processed_brands.add(compound_brand)
                filtered.append(compound_brand)
            continue
        
        # Проверяем, что бренд не является мусором
        if (brand_clean and 
            len(brand_clean) > 2 and 
            brand_lower not in garbage_words and
            not any(char.isdigit() for char in brand_clean) and
            not brand_clean.startswith('...') and
            not brand_clean.endswith('...') and
            not any(garbage in brand_lower for garbage in garbage_words)):
            filtered.append(brand_clean)
    
    return filtered

@shared_task(bind=True, time_limit=259200, soft_time_limit=252000)  # 72 часа максимум, 70 часов мягкий лимит
def process_parsing_task(self, task_id):
    # Проверяем, не завершена ли уже задача
    try:
        task = ParsingTask.objects.get(id=task_id)
        if task.status == 'completed':
            log_debug(f"Task {task_id} уже завершена, пропускаем повторную обработку")
            return None
        elif task.status == 'in_progress':
            # Проверяем, не выполняется ли уже эта задача
            log_debug(f"Task {task_id} уже выполняется, пропускаем повторную обработку")
            return None
    except ParsingTask.DoesNotExist:
        log_debug(f"Task {task_id} не найдена")
        return None
    
    # Отмечаем задачу как выполняющуюся
    task.status = 'in_progress'
    task.progress = 0
    task.save()
    
    log_messages = []
    logger = get_task_logger(__name__)
    channel_layer = get_channel_layer()
    
    def ws_send():
        try:
            # Проверяем количество активных потоков перед отправкой
            active_threads = threading.active_count()
            if active_threads > 50:  # Если слишком много потоков, пропускаем отправку
                log(f"Пропускаем ws_send: слишком много активных потоков ({active_threads})")
                return
                
            async_to_sync(channel_layer.group_send)(
                f'task_{task.id}',
                {
                    'type': 'task_update',
                    'data': {
                        'id': task.id,
                        'status': task.status,
                        'progress': task.progress,
                        'error_message': task.error_message,
                        'result_files': task.result_files,
                        'log': (task.log or '')[-2000:],  # последние 2000 символов
                    }
                }
            )
        except Exception as e:
            # Логируем ошибку но не прерываем выполнение
            log(f"Ошибка ws_send: {str(e)}")
    
    try:
        # Загружаем прокси при старте задачи
        load_proxies_from_file()
        
        df = pd.read_excel(task.file.path)
        # Очищаем DataFrame от пустых строк
        df.dropna(how='all', inplace=True)
        
        # Инициализируем таймаут и счетчик обработанных строк
        task._timeout_check = time.time()
        task._processed_rows = 0  # Добавляем счетчик обработанных строк
        
        total_rows = len(df)
        results_autopiter = []
        results_armtek = []
        results_emex = []

        def log(msg: str):
            # Пишем в память, stdout и celery-лог
            log_messages.append(msg)
            try:
                logger.info(msg)
            except Exception:
                pass
            print(msg)

        # Чтение выбранных источников (autopiter, emex, armtek) из полей задачи, если есть
        selected_sources = {"autopiter", "emex", "armtek"}
        try:
            raw_sources = None
            for attr in ("sources", "source_list", "options", "meta", "params"):
                val = getattr(task, attr, None)
                if val:
                    raw_sources = val
                    break
            if isinstance(raw_sources, str):
                # Пытаемся распарсить JSON, либо разделенный запятыми список
                import json as _json
                try:
                    parsed = _json.loads(raw_sources)
                except Exception:
                    parsed = [s.strip() for s in raw_sources.split(',') if s.strip()]
            else:
                parsed = raw_sources
            if isinstance(parsed, dict) and 'sources' in parsed:
                parsed = parsed['sources']
            if isinstance(parsed, (list, set, tuple)):
                sel = set(str(s).strip().lower() for s in parsed)
                allowed = {"autopiter", "emex", "armtek"}
                selected_sources = sel.intersection(allowed) or selected_sources
        except Exception as e:
            log(f"Ошибка чтения источников из задачи: {e}")

        log(f"Выбранные источники: {sorted(selected_sources)}")

        log(f"Начинаем обработку {total_rows} строк")
        ws_send()
        # Батч-обработка: по 50 строк с промежуточным сохранением результатов
        batch_size = 50
        
        # Оптимизированная функция для параллельного парсинга с таймаутами и прокси
        def parse_all_parallel(numbers, brand, part_number, name):
            results = {'autopiter': [], 'emex': []}
            state = {"emex_disabled": False, "emex_failures": 0}
            ARTICLE_TIMEOUT = 20  # общий таймаут на один артикул
            emex_semaphore = threading.Semaphore(2)  # ограничиваем одновременные Emex-запросы

            def parse_one(site, parser_func, max_retries=1):
                def inner(num, proxy=None):
                    # Проверяем кэш перед парсингом
                    cached_result = get_from_cache(num, site)
                    if cached_result is not None:
                        log(f"{site.capitalize()}: результат из кэша для {num} → {cached_result}")
                        return [(brand, part_number, name, b, num, site) for b in cached_result]
                    
                    for attempt in range(max_retries):
                        try:
                            if attempt == 0:
                                if site == 'emex' and proxy:
                                    log(f"{site.capitalize()}: попытка {attempt+1} с прокси для {num}")
                                else:
                                    proxy = None
                                    log(f"{site.capitalize()}: попытка {attempt+1} без прокси для {num}")
                            else:
                                proxy = get_next_proxy()
                                log(f"{site.capitalize()}: попытка {attempt+1} с прокси для {num}")
                            
                            # Уменьшаем задержку для ускорения
                            time.sleep(0.05 if site == 'autopiter' else 0.05)  # Уменьшаем для Emex
                            brands = parser_func(num, proxy)
                            
                            # Сохраняем результат в кэш
                            is_empty = len(brands) == 0
                            set_cache(num, site, brands, is_empty)
                            
                            log(f"{site}: {num} → {brands}")
                            return [(brand, part_number, name, b, num, site) for b in brands]
                        except Exception as e:
                            log(f"Error parsing {site} for {num} (attempt {attempt + 1}): {str(e)}")
                            if attempt < max_retries - 1:
                                time.sleep(0.2)  # Еще больше уменьшаем время ожидания
                            else:
                                log(f"Failed to parse {site} for {num} after {max_retries} attempts")
                                # Сохраняем пустой результат в кэш
                                set_cache(num, site, [], True)
                                return []
                return inner
            
            # Параллельная обработка артикулов с семафором для Emex
            log(f"Начинаем парсинг {len(numbers)} артикулов для строки {index + 1}")

            def worker(num):
                local = {'autopiter': [], 'emex': []}
                if 'autopiter' in selected_sources:
                    local['autopiter'].extend(parse_one('autopiter', get_brands_by_artikul)(num))
                if 'emex' in selected_sources and not state['emex_disabled']:
                    with emex_semaphore:
                        proxy = get_proxy_string()
                        try:
                            emex_res = parse_one('emex', get_brands_by_artikul_emex)(num, proxy)
                            if emex_res:
                                state['emex_failures'] = 0
                            else:
                                state['emex_failures'] += 1
                            local['emex'].extend(emex_res)
                            if state['emex_failures'] >= 5:
                                state['emex_disabled'] = True
                                log("Emex: слишком много неудач подряд, временно отключаем Emex для этой партии")
                        except Exception as e:
                            state['emex_failures'] += 1
                            log(f"Emex: критическая ошибка для артикула {num}: {str(e)}")
                return local

            # Последовательная обработка для предотвращения исчерпания потоков
            for num in numbers:
                try:
                    res = worker(num)
                    results['autopiter'].extend(res.get('autopiter', []))
                    results['emex'].extend(res.get('emex', []))
                except Exception as e:
                    log(f"Ошибка обработки артикула {num}: {str(e)}")

            return results
        
        # Основной цикл с улучшенной обработкой ошибок и предотвращением бесконечного цикла
        for index, row in df.iterrows():
            try:
                # Проверка таймаута каждые 100 строк для менее частой проверки
                if index % 100 == 0:
                    elapsed_time = time.time() - task._timeout_check
                    if elapsed_time > 252000:  # 70 часов - мягкий лимит
                        log(f"Task timeout approaching ({elapsed_time/3600:.1f} hours), finishing up...")
                        break
                    elif elapsed_time > 259200:  # 72 часа - жесткий лимит
                        log(f"Task timeout reached ({elapsed_time/3600:.1f} hours), forcing stop...")
                        break
                
                # Правильное чтение данных из Excel с защитой от NaN
                # A1: "Бренд № 1" - данные из колонки E входного файла (индекс 4)
                brand_from_e = safe_cell_to_str(row.iloc[4]) if len(row) > 4 else ''
                # B1: "Артикул по Бренду № 1" - данные из колонки F входного файла (индекс 5) - для записи в итоговый файл
                part_number_from_f = safe_cell_to_str(row.iloc[5]) if len(row) > 5 else ''
                # C1: "Наименование" - данные из колонки B входного файла (индекс 1)
                name_from_b = safe_cell_to_str(row.iloc[1]) if len(row) > 1 else ''
                # E1: "Артикул по Бренду № 2" - данные из колонки G входного файла (индекс 6) - для парсинга
                cross_number_from_g = safe_cell_to_str(row.iloc[6]) if len(row) > 6 else ''
                
                # Для парсинга используем кросс-номера из столбца G (если есть),
                # иначе fallback: используем артикул из столбца F
                numbers_source_value = cross_number_from_g if cross_number_from_g else part_number_from_f
                if not numbers_source_value:
                    log(f"Пропускаем строку {index + 1}: нет кросс-номеров и артикула для парсинга (G/F пустые)")
                    task._processed_rows += 1
                    continue
                
                # Создаем список кросс-номеров для парсинга (только из столбца G)
                numbers_to_parse = [n.strip() for n in numbers_source_value.split(';') if n.strip()]
                
                # Если нет артикулов для парсинга, пропускаем
                if not numbers_to_parse:
                    log(f"Пропускаем строку {index + 1}: нет артикулов для парсинга")
                    task._processed_rows += 1  # Увеличиваем счетчик
                    continue
                
                log(f"Обрабатываем строку {index + 1}: {len(numbers_to_parse)} артикулов")
                # Обновляем прогресс и логи для отображения в интерфейсе
                progress = int((index + 1) / total_rows * 100)
                task.progress = progress
                task.status = 'in_progress'
                
                # Сохраняем логи в базу данных для отображения в интерфейсе
                current_log = f"[{datetime.now().strftime('%d.%m.%Y, %H:%M:%S')}] Обрабатываем строку {index + 1}: {len(numbers_to_parse)} артикулов"
                if task.log:
                    task.log += '\n' + current_log
                else:
                    task.log = current_log
                
                # Ограничиваем размер логов (последние 1000 символов)
                if len(task.log) > 10000:
                    lines = task.log.split('\n')
                    task.log = '\n'.join(lines[-50:])  # Последние 50 строк
                
                task.save()
                ws_send()
                
                # Обрабатываем каждый артикул отдельно для создания отдельных строк
                for current_number in numbers_to_parse:
                    if not current_number:
                        continue
                    
                    try:
                        # Параллельно Autopiter, Emex для текущего артикула
                        parallel_results = parse_all_parallel([current_number], brand_from_e, part_number_from_f, name_from_b)
                        
                        # Обрабатываем результаты Autopiter для текущего артикула
                        for (b1, pn1, n1, b2, pn2, src) in parallel_results['autopiter']:
                            # Фильтруем бренд № 2 (результат парсинга)
                            if b2 and b2.strip():
                                filtered_brands = filter_garbage_brands([b2])
                                if filtered_brands:
                                    # Создаем отдельную запись для каждого отфильтрованного бренда
                                    for filtered_brand in filtered_brands:
                                        # Нормализуем артикул для предотвращения дублей
                                        normalized_article = normalize_article_for_compare(pn2)
                                        if normalized_article:  # Только если артикул не пустой после нормализации
                                            d = {
                                                'Бренд № 1': clean_excel_string(brand_from_e),  # Из колонки E входного файла
                                                'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),  # Из колонки F входного файла
                                                'Наименование': clean_excel_string(name_from_b),  # Из колонки B входного файла
                                                'Бренд № 2': clean_excel_string(filtered_brand),  # Результат парсинга
                                                'Артикул по Бренду № 2': clean_excel_string(pn2),  # Конкретный найденный артикул
                                                'Источник': src
                                            }
                                            results_autopiter.append(d)
                            else:
                                # Нормализуем артикул для предотвращения дублей
                                normalized_article = normalize_article_for_compare(pn2)
                                if normalized_article:  # Только если артикул не пустой после нормализации
                                    d = {
                                        'Бренд № 1': clean_excel_string(brand_from_e),  # Из колонки E входного файла
                                        'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),  # Из колонки F входного файла
                                        'Наименование': clean_excel_string(name_from_b),  # Из колонки B входного файла
                                        'Бренд № 2': clean_excel_string(b2),  # Результат парсинга
                                        'Артикул по Бренду № 2': clean_excel_string(pn2),  # Конкретный найденный артикул
                                        'Источник': src
                                    }
                                    results_autopiter.append(d)
                        
                        # Обрабатываем результаты Emex для текущего артикула
                        for (b1, pn1, n1, b2, pn2, src) in parallel_results['emex']:
                            # Фильтруем бренд № 2 (результат парсинга)
                            if b2 and b2.strip():
                                filtered_brands = filter_garbage_brands([b2])
                                if filtered_brands:
                                    # Создаем отдельную запись для каждого отфильтрованного бренда
                                    for filtered_brand in filtered_brands:
                                        # Нормализуем артикул для предотвращения дублей
                                        normalized_article = normalize_article_for_compare(pn2)
                                        if normalized_article:  # Только если артикул не пустой после нормализации
                                            d = {
                                                'Бренд № 1': clean_excel_string(brand_from_e),  # Из колонки E входного файла
                                                'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),  # Из колонки F входного файла
                                                'Наименование': clean_excel_string(name_from_b),  # Из колонки B входного файла
                                                'Бренд № 2': clean_excel_string(filtered_brand),  # Результат парсинга
                                                'Артикул по Бренду № 2': clean_excel_string(pn2),  # Конкретный найденный артикул
                                                'Источник': src
                                            }
                                            results_emex.append(d)
                            else:
                                # Нормализуем артикул для предотвращения дублей
                                normalized_article = normalize_article_for_compare(pn2)
                                if normalized_article:  # Только если артикул не пустой после нормализации
                                    d = {
                                        'Бренд № 1': clean_excel_string(brand_from_e),  # Из колонки E входного файла
                                        'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),  # Из колонки F входного файла
                                        'Наименование': clean_excel_string(name_from_b),  # Из колонки B входного файла
                                        'Бренд № 2': clean_excel_string(b2),  # Результат парсинга
                                        'Артикул по Бренду № 2': clean_excel_string(pn2),  # Конкретный найденный артикул
                                        'Источник': src
                                    }
                                    results_emex.append(d)
                        
                        # Armtek (Selenium) - оптимизированная версия (если выбран)
                        def parse_armtek_parallel(numbers, brand_from_e, part_number_from_f, name_from_b):
                            results = []
                            if not numbers:
                                return results
                            # Дедуп номерoв по нормализованному виду (с учетом рус/лат букв) с сохранением порядка
                            seen_norm: set = set()
                            unique_numbers: list = []
                            for n in numbers:
                                nn = normalize_article_for_compare(n)
                                if not nn or nn in seen_norm:
                                    continue
                                seen_norm.add(nn)
                                unique_numbers.append(n)

                            log(f"Armtek: начало обработки {len(unique_numbers)} артикулов для строки {index + 1}")

                            def parse_one(num):
                                # Проверяем кэш перед парсингом
                                cached_result = get_from_cache(num, 'armtek')
                                if cached_result is not None:
                                    log(f"Armtek: результат из кэша для {num} → {cached_result}")
                                    if cached_result:
                                        return [(brand_from_e, part_number_from_f, name_from_b, b, num, 'armtek') for b in cached_result]
                                    else:
                                        return [(brand_from_e, part_number_from_f, name_from_b, 'Бренды не найдены', num, 'armtek')]
                                
                                max_retries = 1
                                for attempt in range(max_retries):
                                    try:
                                        if attempt == 0:
                                            proxy = None
                                            log(f"Armtek: попытка {attempt+1} без прокси для {num}")
                                        else:
                                            proxy = get_next_proxy()
                                            log(f"Armtek: попытка {attempt+1} с прокси для {num}")
                                        
                                        # Уменьшаем задержку для ускорения
                                        time.sleep(0.1)
                                        # Используем функцию для поиска брендов
                                        from .autopiter_parser import get_brands_by_artikul_armtek
                                        brands = get_brands_by_artikul_armtek(num, proxy)
                                        
                                        # Сохраняем результат в кэш
                                        is_empty = len(brands) == 0
                                        set_cache(num, 'armtek', brands, is_empty)
                                        
                                        if brands:
                                            # Фильтруем бренды для Armtek так же, как для других источников
                                            filtered_brands = filter_garbage_brands(brands)
                                            
                                            # Дополнительная фильтрация для Armtek: убираем составные артикулы
                                            # которые могут содержать несуществующие части
                                            clean_results = []
                                            for brand in filtered_brands:
                                                # Проверяем, не является ли это составным артикулом
                                                if ' ' in brand and len(brand.split()) > 1:
                                                    # Это составной артикул, пропускаем его
                                                    log(f"Armtek: пропускаем составной артикул '{brand}' для {num}")
                                                    continue
                                                clean_results.append(brand)
                                            
                                            if clean_results:
                                                log(f"armtek: {num} → найдено {len(clean_results)} брендов (после фильтрации)")
                                                return [(brand_from_e, part_number_from_f, name_from_b, brand, num, 'armtek') for brand in clean_results]
                                            else:
                                                log(f"armtek: {num} → все бренды отфильтрованы как составные артикулы")
                                                return [(brand_from_e, part_number_from_f, name_from_b, 'Бренды не найдены', num, 'armtek')]
                                        else:
                                            log(f"armtek: {num} → бренды не найдены")
                                            return [(brand_from_e, part_number_from_f, name_from_b, 'Бренды не найдены', num, 'armtek')]
                                    except Exception as e:
                                        log(f"Error parsing armtek for {num} (attempt {attempt + 1}): {str(e)}")
                                        if attempt < max_retries - 1:
                                            time.sleep(0.5)
                                        else:
                                            log(f"Failed to parse armtek for {num} after {max_retries} attempts")
                                            # Сохраняем пустой результат в кэш
                                            set_cache(num, 'armtek', [], True)
                                            return []

                            # Контролируемый параллелизм: 2-3 потока для стабильности Selenium
                            import concurrent.futures
                            max_workers = 3
                            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                                future_to_num = {executor.submit(parse_one, num): num for num in unique_numbers}
                                for future in concurrent.futures.as_completed(future_to_num):
                                    num = future_to_num[future]
                                    try:
                                        for res in future.result() or []:
                                            results.append(res)
                                    except Exception as e:
                                        log(f"Error processing armtek result for {num}: {str(e)}")

                            log(f"Armtek: завершена обработка для строки {index + 1}, найдено {len(results)} результатов")
                            return results
                        
                        # Armtek переносим на батч обработки (выполним после цикла по номерам)
                    
                    except Exception as e:
                        log(f"Ошибка при обработке артикула {current_number} в строке {index + 1}: {str(e)}")
                        continue
                
                # После обработки всех номеров строки запускаем Armtek батчом (если выбран)
                if 'armtek' in selected_sources and numbers_to_parse:
                    armtek_results = parse_armtek_parallel(numbers_to_parse, brand_from_e, part_number_from_f, name_from_b)
                    for (b1, pn1, n1, brand, original_num, src) in armtek_results:
                        results_armtek.append({
                            'Бренд № 1': clean_excel_string(brand_from_e),
                            'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),
                            'Наименование': clean_excel_string(name_from_b),
                            'Бренд № 2': clean_excel_string(brand),
                            'Артикул по Бренду № 2': clean_excel_string(original_num),
                            'Источник': src
                        })
                    # промежуточный лог
                    task.log = '\n'.join(log_messages[-100:])
                    task.save(); ws_send()

                # Увеличиваем счетчик обработанных строк
                task._processed_rows += 1
                
                # Обновляем прогресс каждые 3 строки для более частого обновления
                if (index + 1) % 3 == 0 or index == total_rows - 1:
                    progress = int((index + 1) / total_rows * 100)
                    task.progress = progress
                    task.log = '\n'.join(log_messages[-100:])  # Ограничиваем лог
                    task.status = 'in_progress'
                    task.save()
                    ws_send()
                    
                    # Принудительная очистка памяти
                    gc.collect()
                    
                    # Периодическая очистка процессов Chrome каждые 5 строк для предотвращения накопления процессов
                    if (index + 1) % 5 == 0:
                        try:
                            cleanup_chrome_processes()
                            cleanup_driver_pool()
                            log("Performed periodic Chrome and driver pool cleanup")
                        except Exception as e:
                            log(f"Error during Chrome cleanup: {str(e)}")

                # Чекпоинт каждые batch_size строк — записываем на диск промежуточные результаты
                if (index + 1) % batch_size == 0:
                    try:
                        if results_autopiter:
                            # Удаляем дубли
                            results_autopiter = dedupe_rows(results_autopiter)
                            df_autopiter = pd.DataFrame(results_autopiter)
                            autopiter_file = f'media/results/autopiter_results_{task.id}.xlsx'
                            df_autopiter.to_excel(autopiter_file, index=False, engine='openpyxl')
                            task.result_files = task.result_files or {}
                            task.result_files['autopiter'] = autopiter_file
                        if results_armtek:
                            results_armtek = dedupe_rows(results_armtek)
                            df_armtek = pd.DataFrame(results_armtek)
                            armtek_file = f'media/results/armtek_results_{task.id}.xlsx'
                            df_armtek.to_excel(armtek_file, index=False, engine='openpyxl')
                            task.result_files = task.result_files or {}
                            task.result_files['armtek'] = armtek_file
                        if results_emex:
                            results_emex = dedupe_rows(results_emex)
                            df_emex = pd.DataFrame(results_emex)
                            emex_file = f'media/results/emex_results_{task.id}.xlsx'
                            df_emex.to_excel(emex_file, index=False, engine='openpyxl')
                            task.result_files = task.result_files or {}
                            task.result_files['emex'] = emex_file
                        task.save()
                        log("Чекпоинт: промежуточные файлы результатов сохранены")
                    except Exception as e:
                        log(f"Ошибка чекпоинта сохранения файлов: {str(e)}")
                
            except Exception as e:
                log(f"Error processing row {index + 1}: {str(e)}")
                task._processed_rows += 1  # Увеличиваем счетчик даже при ошибке
                
                # Добавляем логирование ошибки в базу данных
                error_log = f"[{datetime.now().strftime('%d.%m.%Y, %H:%M:%S')}] Ошибка обработки строки {index + 1}: {str(e)}"
                if task.log:
                    task.log += '\n' + error_log
                else:
                    task.log = error_log
                task.save()
                continue
        
        completion_log = f"[{datetime.now().strftime('%d.%m.%Y, %H:%M:%S')}] Обработка завершена. Обработано строк: {task._processed_rows} из {total_rows}"
        log(completion_log)
        
        # Добавляем в базу данных
        if task.log:
            task.log += '\n' + completion_log
        else:
            task.log = completion_log
        task.save()
        
        # Создаем результаты с улучшенной обработкой ошибок
        try:
            if results_autopiter:
                results_autopiter = dedupe_rows(results_autopiter)
                df_autopiter = pd.DataFrame(results_autopiter)
                autopiter_file = f'media/results/autopiter_results_{task.id}.xlsx'
                try:
                    # Используем openpyxl engine для лучшей совместимости
                    df_autopiter.to_excel(autopiter_file, index=False, engine='openpyxl')
                    log(f"Создан файл Autopiter: {autopiter_file}")
                except Exception as e:
                    log(f"Ошибка создания файла Autopiter: {str(e)}")
                    # Пробуем без engine
                    df_autopiter.to_excel(autopiter_file, index=False)
                    log(f"Создан файл Autopiter (без engine): {autopiter_file}")
                task.result_files = task.result_files or {}
                task.result_files['autopiter'] = autopiter_file
                log(f"Файл Autopiter добавлен в result_files: {autopiter_file}")
            
            if results_armtek:
                results_armtek = dedupe_rows(results_armtek)
                df_armtek = pd.DataFrame(results_armtek)
                armtek_file = f'media/results/armtek_results_{task.id}.xlsx'
                try:
                    # Используем openpyxl engine для лучшей совместимости
                    df_armtek.to_excel(armtek_file, index=False, engine='openpyxl')
                    log(f"Создан файл Armtek: {armtek_file}")
                except Exception as e:
                    log(f"Ошибка создания файла Armtek: {str(e)}")
                    # Пробуем без engine
                    df_armtek.to_excel(armtek_file, index=False)
                    log(f"Создан файл Armtek (без engine): {armtek_file}")
                task.result_files = task.result_files or {}
                task.result_files['armtek'] = armtek_file
                log(f"Файл Armtek добавлен в result_files: {armtek_file}")
            
            if results_emex:
                results_emex = dedupe_rows(results_emex)
                df_emex = pd.DataFrame(results_emex)
                emex_file = f'media/results/emex_results_{task.id}.xlsx'
                try:
                    # Используем openpyxl engine для лучшей совместимости
                    df_emex.to_excel(emex_file, index=False, engine='openpyxl')
                    log(f"Создан файл Emex: {emex_file}")
                except Exception as e:
                    log(f"Ошибка создания файла Emex: {str(e)}")
                    # Пробуем без engine
                    df_emex.to_excel(emex_file, index=False)
                    log(f"Создан файл Emex (без engine): {emex_file}")
                task.result_files = task.result_files or {}
                task.result_files['emex'] = emex_file
                log(f"Файл Emex добавлен в result_files: {emex_file}")
        except Exception as e:
            log(f"Критическая ошибка при создании Excel файлов: {str(e)}")
        
        # Принудительно сохраняем task с файлами
        task.status = 'completed'
        task.progress = 100
        task.save()
        log(f"Task завершен. Result files: {task.result_files}")
        ws_send()
        
        # Очистка Chrome процессов и пула драйверов
        cleanup_chrome_processes()
        cleanup_driver_pool()
        
        # Финальная очистка и подтверждение завершения
        log(f"Task {task_id} успешно завершена. Обработано строк: {task._processed_rows}")
        
        # Возвращаем результат для предотвращения повторного выполнения
        return {
            'status': 'completed',
            'task_id': task_id,
            'result_files': task.result_files,
            'processed_rows': task._processed_rows,
            'message': 'Task completed successfully'
        }
        
    except Exception as e:
        task.status = 'error'
        task.error_message = str(e)
        task.save()
        ws_send()
        cleanup_chrome_processes()
        cleanup_driver_pool()
        raise 