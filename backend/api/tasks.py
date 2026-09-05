import pandas as pd
from celery import shared_task
from django.core.files import File
from core.models import ParsingTask
from .autopiter_parser import (
    get_brands_by_artikul,
    get_brands_by_artikul_armtek,
    get_brands_by_artikul_emex,
    AutopiterRateLimitException,
    AutopiterForbiddenException,
    AutopiterNetworkException,
    AutopiterBlockedException,
    looks_like_analytics_garbage_token,
    cleanup_chrome_processes,
    cleanup_driver_pool,
    get_next_proxy,
    get_proxy_string,
    load_proxies_from_file,
    is_autopiter_proxy_enabled,
    log_debug,
    filter_armtek_brands,
    split_combined_brands,
    reset_armtek_selenium_state,
    PROXY_LIST,
)
import re
import unicodedata
import concurrent.futures
import time
import gc
import threading
import queue
from collections import deque
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from typing import List, Dict, Optional, Set
import os
from celery.utils.log import get_task_logger
from datetime import datetime

# Кэш для ускорения работы парсера
PARSER_CACHE = {}
CACHE_EXPIRATION = 21600  # 6 часов вместо 1
NEGATIVE_CACHE_EXPIRATION = 7200  # 2 часа для пустых

CANCELLED_PARSING_TASKS: Set[int] = set()
CANCELLED_TASKS_LOCK = threading.Lock()


class TaskCancelledException(Exception):
    """Специальное исключение для остановки задачи по запросу пользователя"""


@shared_task
def cleanup_old_media_results():
    """Ежедневная очистка media/results и ротация больших логов."""
    from .maintenance import run_media_maintenance
    return run_media_maintenance()


def compute_armtek_quality_metrics(results_armtek: list) -> dict:
    """Метрики качества Armtek: not found, garbage, valid."""
    from .autopiter_parser import _armtek_brand_text_is_valid, _get_armtek_ui_garbage

    ui_garbage = _get_armtek_ui_garbage()

    not_found_label = 'Бренды не найдены'
    total = len(results_armtek)
    not_found = 0
    garbage = 0
    valid = 0

    for row in results_armtek:
        brand = str(row.get('Бренд № 2', '')).strip()
        if not brand or brand == not_found_label:
            not_found += 1
        elif brand.lower() in ui_garbage or not _armtek_brand_text_is_valid(brand):
            garbage += 1
        else:
            valid += 1

    def _pct(n: int) -> float:
        return round(100.0 * n / total, 1) if total else 0.0

    return {
        'total': total,
        'not_found': not_found,
        'not_found_pct': _pct(not_found),
        'garbage': garbage,
        'garbage_pct': _pct(garbage),
        'valid': valid,
        'valid_pct': _pct(valid),
    }


def mark_parsing_task_cancelled(task_id: int) -> None:
    with CANCELLED_TASKS_LOCK:
        CANCELLED_PARSING_TASKS.add(int(task_id))


def clear_parsing_task_cancelled(task_id: int) -> None:
    with CANCELLED_TASKS_LOCK:
        CANCELLED_PARSING_TASKS.discard(int(task_id))


def is_parsing_task_cancelled(task_id: int) -> bool:
    with CANCELLED_TASKS_LOCK:
        return int(task_id) in CANCELLED_PARSING_TASKS

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
    # НО сохраняем:
    # - слэши / для названий типа "NISSAN/HINO/FUSO"
    # - звездочки * для размеров типа "430*50.8*10"
    # - двоеточия : для некоторых обозначений
    cleaned = re.sub(r'[\\?:\[\]]', '', cleaned)
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
    # Unicode-нормализация + защита от неразрывных/нулевой ширины пробелов
    a = unicodedata.normalize("NFKC", a).replace("\u00A0", " ").replace("\u200B", "")
    
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
    
    parts: List[str] = []
    
    # Разбиваем по типичным разделителям кросс-номеров:
    # ';' - как в наших файлах, '/' и ',' - как в названиях вида 'HDA-002 / 1-31800-142-0 / ME657650'
    raw_chunks = re.split(r"[;]", article.upper())
    for chunk in raw_chunks:
        sub_parts = re.split(r"[\/,]", chunk)
        for part in sub_parts:
            token = part.strip()
            if not token:
                continue
            clean_part = normalize_article_for_compare(token)
            # Минимальная длина артикула, отсекаем совсем короткие/шум
            if clean_part and len(clean_part) >= 3:
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
    # Unicode-нормализация + защита от неразрывных/нулевой ширины пробелов
    b = unicodedata.normalize("NFKC", b).replace("\u00A0", " ").replace("\u200B", "")

    # Маппинг похожих русских букв на английские для унификации (частая причина "видимых" дублей)
    ru_to_en_map = {
        'А': 'A',
        'В': 'B',
        'М': 'M',
        'Р': 'P',
        'Е': 'E',
        'О': 'O',
        'С': 'C',
        'Х': 'X',
        'К': 'K',
        'Н': 'H',
        'Т': 'T',
        'У': 'Y',
    }
    for ru_char, en_char in ru_to_en_map.items():
        b = b.replace(ru_char, en_char)

    # Оставляем только буквы и цифры
    b = re.sub(r"[^0-9A-Z]+", "", b)
    return b

def normalize_brand_display(brand: str) -> str:
    """Приводит бренд к однообразному человеко-читаемому виду для вывода.
    - Обрезает пробелы
    - Унифицирует разделители (" / " → "-" для некоторых синонимов)
    - Приводит регистр для известных аббревиатур и брендов
    """
    if not brand:
        return ""
    b = str(brand).strip()
    # унифицируем множественные пробелы
    b = re.sub(r"\s+", " ", b)
    # типовые синонимы/формы
    map_exact = {
        'hyundai / kia': 'Hyundai-Kia',
        'hyundai/kia': 'Hyundai-Kia',
        'hyundai- kia': 'Hyundai-Kia',
        'trw/lucas': 'TRW/Lucas',
        'ohno': 'OHNO',
        'rbi': 'RBI',
        'nso': 'NSO',
        'pm': 'PM',
        'gparts': 'GParts',
        'gsp': 'GSP',
        'prc': 'PRC',
    }
    low = b.lower()
    if low in map_exact:
        return map_exact[low]
    # Ставим Title Case для длинных брендов, но сохраняем аббревиатуры
    if len(b) <= 4 and b.upper() == b:
        return b  # уже аббревиатура
    # если это слова через дефис или слэш — приводим каждую часть к Title
    parts = re.split(r"([\-/])", b)
    for i in range(0, len(parts), 2):
        parts[i] = parts[i].strip().title()
    return ''.join(parts).strip()
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

def _split_comma_separated_brands(brand_str: str) -> List[str]:
    """Разбивает бренды, разделенные запятыми, на отдельные бренды.
    
    Например: "Bmw, Mini" -> ["Bmw", "Mini"]
              "Geunyoung, Geun Young" -> ["Geunyoung", "Geun Young"]
    """
    if not brand_str or not brand_str.strip():
        return []
    
    # Разбиваем по запятой и очищаем каждый бренд
    parts = [part.strip() for part in brand_str.split(',')]
    # Убираем пустые строки
    return [part for part in parts if part]


def filter_garbage_brands(brands: List[str], source: str = 'autopiter') -> List[str]:
    """Фильтрует мусорные бренды из результатов Autopiter и Emex"""
    from .brand_config import get_blacklist_for_source
    garbage_words = get_blacklist_for_source(source)
    
    filtered: List[str] = []
    # Дедупликация брендов на уровне результатов, иначе Emex (и иногда Autopiter)
    # может возвращать один и тот же бренд разными путями/в разных списках.
    seen_norm: set = set()
    brand_whitelist_tokens = {
        'jac', 'faw', 'автокомпонент', 'autocomponent',
        'sitrak', 'howo', 'wayteko', 'shaanxi', 'shacman',
        'mobis', 'valeo', 'createk', 'weichai', 'htp', 'jmc',
        'zevs', 'toyota / lexus', 'toyota/lexus', 'hino', 'nissan',
        'hot-parts', 'tesla', 'autotech'
    }
    # Часто встречающиеся "мусорные" токены, которые были не покрыты ранее
    extra_garbage_exact = {
        'запчасть', 'component', 'autocomponent', 'автодеталь', 'автокомпонент', 'автокомпонент плюс'
    }
    # Слова-числительные, утекающие как бренды из Emex
    ru_number_words = {
        'НУЛЬ','ОДИН','ДВА','ТРИ','ЧЕТЫРЕ','ПЯТЬ','ШЕСТЬ','СЕМЬ','ВОСЕМЬ','ДЕВЯТЬ','ДЕСЯТЬ',
        'ОДИННАДЦАТЬ','ДВЕНАДЦАТЬ','ТРИНАДЦАТЬ','ЧЕТЫРНАДЦАТЬ','ПЯТНАДЦАТЬ','ШЕСТНАДЦАТЬ',
        'СЕМНАДЦАТЬ','ВОСЕМНАДЦАТЬ','ДЕВЯТНАДЦАТЬ','ДВАДЦАТЬ'
    }
    # Словарь для объединения составных брендов
    # УБРАЛИ 'diesel' и 'дизель' - это не бренд, а тип двигателя
    compound_brands = {
        'auto': 'AUTO-COMFORT',
        'comfort': 'AUTO-COMFORT',
        'hot': 'HOT-PARTS',
        'parts': 'HOT-PARTS',
        'g': 'G-BRAKE',
        'brake': 'G-BRAKE',
        'zevs': 'ZEVS',
        'z': 'ZEVS',
        'shaanxi': 'SHAANXI/SHACMAN',
        'shacman': 'SHAANXI/SHACMAN'
    }
    
    # Сначала объединяем составные бренды
    processed_brands = set()
    for brand in brands:
        brand_clean = brand.strip()
        if not brand_clean:
            continue
            
        brand_lower = brand_clean.lower()

        # Обрабатываем составные бренды с слэшем (например, "SHAANXI/SHACMAN")
        if '/' in brand_clean:
            parts = [p.strip() for p in brand_clean.split('/')]
            # Если это известный составной бренд
            if len(parts) == 2:
                part1_lower = parts[0].lower()
                part2_lower = parts[1].lower()
                if part1_lower in compound_brands or part2_lower in compound_brands:
                    compound_brand = compound_brands.get(part1_lower) or compound_brands.get(part2_lower)
                    if compound_brand and compound_brand not in processed_brands:
                        processed_brands.add(compound_brand)
                        cb_norm = normalize_brand_for_compare(compound_brand)
                        if cb_norm and cb_norm not in seen_norm:
                            seen_norm.add(cb_norm)
                            filtered.append(compound_brand)
                        continue
                # Если обе части в whitelist, оставляем как есть
                if (part1_lower in brand_whitelist_tokens or part2_lower in brand_whitelist_tokens):
                    display = normalize_brand_display(brand_clean)
                    norm = normalize_brand_for_compare(display)
                    if norm and norm not in seen_norm:
                        seen_norm.add(norm)
                        filtered.append(display)
                    continue

        whitelist_match = False
        for token in brand_whitelist_tokens:
            if brand_lower == token or brand_lower.startswith(f"{token} ") or brand_lower.startswith(f"{token}/"):
                display = normalize_brand_display(brand_clean)
                norm = normalize_brand_for_compare(display)
                if norm and norm not in seen_norm:
                    seen_norm.add(norm)
                    filtered.append(display)
                whitelist_match = True
                break
        if whitelist_match:
            continue
        
        # Проверяем, является ли это частью составного бренда
        if brand_lower in compound_brands:
            compound_brand = compound_brands[brand_lower]
            if compound_brand not in processed_brands:
                processed_brands.add(compound_brand)
                cb_norm = normalize_brand_for_compare(compound_brand)
                if cb_norm and cb_norm not in seen_norm:
                    seen_norm.add(cb_norm)
                    filtered.append(compound_brand)
            continue
        
        # Проверяем, что бренд не является мусором
        # Строгая проверка: точное совпадение И подстрока
        is_garbage = (
            brand_lower in garbage_words or
            brand_lower in extra_garbage_exact or
            brand_clean.upper() in ru_number_words or
            looks_like_analytics_garbage_token(brand_clean) or
            any(garbage in brand_lower for garbage in garbage_words) or
            any(garbage in brand_lower for garbage in extra_garbage_exact)
        )
        
        if (brand_clean and 
            len(brand_clean) > 1 and 
            not is_garbage and
            not any(char.isdigit() for char in brand_clean) and
            not brand_clean.startswith('...') and
            not brand_clean.endswith('...')):
            # Нормализуем отображение
            display = normalize_brand_display(brand_clean)
            norm = normalize_brand_for_compare(display)
            if norm and norm not in seen_norm:
                seen_norm.add(norm)
                filtered.append(display)

    # Emex часто отдает одновременно составной бренд и его части:
    # "Carville Racing" + "Carville" + "Racing", "Golden Asia" + "Golden" + "Asia".
    # Если составной бренд присутствует, удаляем его однословные компоненты.
    multi_word_tokens: set = set()
    for b in filtered:
        low = (b or "").strip().lower()
        if " " in low:
            for tok in re.split(r"\s+", low):
                if tok:
                    multi_word_tokens.add(tok)

    if multi_word_tokens:
        filtered = [
            b for b in filtered
            if not ((b or "").strip().lower() in multi_word_tokens and " " not in (b or "").strip())
        ]

    return filtered

def split_large_file(file_path: str, max_rows_per_batch: int = 100) -> List[str]:
    """Разбивает большой Excel файл на части для параллельной обработки"""
    try:
        import os
        # Создаем директорию для временных файлов
        temp_dir = "media/temp"
        os.makedirs(temp_dir, exist_ok=True)
        
        df = pd.read_excel(file_path)
        df.dropna(how='all', inplace=True)
        
        total_rows = len(df)
        if total_rows <= max_rows_per_batch:
            return [file_path]  # Файл не нужно разбивать
        
        batch_files = []
        for i in range(0, total_rows, max_rows_per_batch):
            batch_df = df.iloc[i:i + max_rows_per_batch]
            batch_file = f"{temp_dir}/batch_{i//max_rows_per_batch}_{file_path.split('/')[-1]}"
            batch_df.to_excel(batch_file, index=False)
            batch_files.append(batch_file)
        
        return batch_files
    except Exception as e:
        log_debug(f"Ошибка разбиения файла: {str(e)}")
        return [file_path]

@shared_task(bind=True, time_limit=360000, soft_time_limit=350000)  # 100 часов максимум, 97 часов мягкий лимит
def process_parsing_task(self, task_id):
    # Сброс состояния Selenium для новой задачи
    from .autopiter_parser import (
        reset_autopiter_selenium_state,
        reset_armtek_selenium_state,
        reset_emex_parser_state,
        cleanup_chrome_processes,
        cleanup_driver_pool,
    )
    reset_autopiter_selenium_state()
    reset_armtek_selenium_state()
    reset_emex_parser_state()
    
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
    
    def ensure_not_cancelled():
        if is_parsing_task_cancelled(task_id):
            raise TaskCancelledException()

    def update_task_fields(**kwargs):
        ensure_not_cancelled()
        updated = ParsingTask.objects.filter(id=task_id).update(**kwargs)
        if updated == 0:
            raise TaskCancelledException()
        for key, value in kwargs.items():
            setattr(task, key, value)

    # Отмечаем задачу как выполняющуюся
    update_task_fields(status='in_progress')
    
    log_messages = []
    # Путь к файловому логу для этой задачи
    log_file_path = os.path.join('media', 'results', f'parsing_task_{task_id}.log')
    # Готовим файл логов: создаём директорию и очищаем старое содержимое
    try:
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        with open(log_file_path, 'w', encoding='utf-8') as _f:
            _f.write('')
    except Exception:
        # Если не удалось создать файл логов — работаем только с in-memory логами
        log_file_path = None

    logger = get_task_logger(__name__)
    channel_layer = get_channel_layer()
    
    def ws_send():
        try:
            # Проверяем количество активных потоков перед отправкой
            active_threads = threading.active_count()
            if active_threads > 50:  # Если слишком много потоков, пропускаем отправку
                log(f"Пропускаем ws_send: слишком много активных потоков ({active_threads})")
                return
            
            # Рассчитываем прогресс
            progress = 0
            if hasattr(task, '_total_cross_numbers') and getattr(task, '_total_cross_numbers', 0) > 0:
                progress = min(100, int((getattr(task, '_processed_cross_numbers', 0) / task._total_cross_numbers) * 100))
            elif hasattr(task, '_total_rows') and task._total_rows > 0:
                progress = min(100, int((task._processed_rows / task._total_rows) * 100))
            
            async_to_sync(channel_layer.group_send)(
                f'task_{task.id}',
                {
                    'type': 'task_update',
                    'data': {
                        'id': task.id,
                        'status': task.status,
                        'error_message': task.error_message,
                        'result_files': {},
                        'log': '',
                        'progress': progress,
                        'current_row': getattr(task, '_current_row', 0),
                        'total_rows': getattr(task, '_total_rows', 0),
                        'processed_rows': getattr(task, '_processed_rows', 0),
                        'current_number': getattr(task, '_current_number', ''),
                        'total_cross_numbers': getattr(task, '_total_cross_numbers', 0),
                        'processed_cross_numbers': getattr(task, '_processed_cross_numbers', 0),
                    }
                }
            )
        except Exception as e:
            log(f"Ошибка ws_send: {str(e)}")
    
    try:
        # Обслуживание media/results (очистка >7 дн., ротация логов)
        try:
            from .maintenance import run_media_maintenance
            maint = run_media_maintenance()
            if maint.get('deleted'):
                print(f"[maintenance] Удалено старых файлов: {maint['deleted']}")
        except Exception as maint_err:
            print(f"[maintenance] Ошибка: {maint_err}")

        # Загружаем прокси при старте задачи
        load_proxies_from_file()

        def log(msg: str):
            """Логирование c временной меткой + запись в файл (если доступен)."""
            from datetime import datetime as _dt
            timestamp = _dt.now().strftime('%d.%m.%Y, %H:%M:%S')
            line = f"[{timestamp}] {msg}"
            log_messages.append(line)
            try:
                logger.info(line)
            except Exception:
                pass
            print(line)
            if log_file_path:
                try:
                    with open(log_file_path, 'a', encoding='utf-8') as f:
                        f.write(line + '\n')
                except Exception:
                    pass

        # Проверяем размер файла и разбиваем на части если нужно
        df = pd.read_excel(task.file.path)
        df.dropna(how='all', inplace=True)
        
        # Если файл очень большой (>200 строк), разбиваем на части
        batch_files = [task.file.path]
        if len(df) > 200:
            log(f"Файл содержит {len(df)} строк, разбиваем на части для оптимизации...")
            batch_files = split_large_file(task.file.path, max_rows_per_batch=100)
            log(f"Файл разбит на {len(batch_files)} частей")
        
        # Будем последовательно обрабатывать все части, суммируя результаты
        total_rows = 0
        results_autopiter = []
        results_armtek = []
        results_emex = []
        frames = []
        for batch_index, batch_path in enumerate(batch_files):
            try:
                df = pd.read_excel(batch_path)
                df.dropna(how='all', inplace=True)
                total_rows += len(df)
                frames.append(df)
                log(f"Обрабатываем часть {batch_index + 1} из {len(batch_files)}: {len(df)} строк")
            except Exception as e:
                log(f"Ошибка чтения части {batch_index + 1}: {str(e)}")
                continue
        
        # Собираем все части в единый DataFrame
        if frames:
            df = pd.concat(frames, ignore_index=True)
        else:
            df = pd.DataFrame()
        
        # Инициализируем таймаут и счетчики
        task._timeout_check = time.time()
        task._processed_rows = 0
        task._total_rows = total_rows
        task._current_row = 0
        task._total_cross_numbers = 0
        task._processed_cross_numbers = 0
        task._current_number = ''
        
        # Быстрый проход по DataFrame, чтобы посчитать общее количество кросс-номеров
        try:
            total_cross = 0
            total_cross_raw = 0
            for _, src_row in df.iterrows():
                cross_from_g = safe_cell_to_str(src_row.iloc[6]) if len(src_row) > 6 else ''
                part_from_f = safe_cell_to_str(src_row.iloc[5]) if len(src_row) > 5 else ''
                numbers_source_value = cross_from_g if cross_from_g else part_from_f
                if not numbers_source_value:
                    continue
                nums = [n.strip() for n in str(numbers_source_value).split(';') if n and str(n).strip()]
                total_cross_raw += len(nums)
                deduped_numbers = []
                seen_norm_articles = set()
                for num in nums:
                    norm = normalize_article_for_compare(num)
                    if not norm:
                        continue
                    if norm in seen_norm_articles:
                        continue
                    seen_norm_articles.add(norm)
                    deduped_numbers.append(num)
                total_cross += len(deduped_numbers)
            task._total_cross_numbers = total_cross
            task._total_cross_numbers_raw = total_cross_raw
        except Exception as e:
            log(f"Ошибка подсчёта общего количества кросс-номеров: {e}")
            task._total_cross_numbers = 0
        
        # Сохраняем метаданные в sources
        if not isinstance(task.sources, dict):
            task.sources = {}
        task.sources['_meta'] = {
            'total_rows': total_rows,
            'processed_rows': 0,
            'current_row': 0,
            'total_cross_numbers': getattr(task, '_total_cross_numbers', 0),
            'total_cross_numbers_raw': getattr(task, '_total_cross_numbers_raw', 0),
            'processed_cross_numbers': 0,
            'current_number': ''
        }
        update_task_fields(sources=task.sources)

        # Чтение выбранных источников
        selected_sources = {"autopiter", "emex", "armtek"}
        try:
            raw_sources = None
            for attr in ("sources", "source_list", "options", "meta", "params"):
                val = getattr(task, attr, None)
                if val:
                    raw_sources = val
                    break
            if isinstance(raw_sources, str):
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
        try:
            raw_total = int(getattr(task, "_total_cross_numbers_raw", 0) or 0)
            dedup_total = int(getattr(task, "_total_cross_numbers", 0) or 0)
            if raw_total and dedup_total and raw_total != dedup_total:
                log(
                    f"Кросс-номера: в файле всего {raw_total}, после дедупликации (нормализация артикула) осталось {dedup_total}. "
                    f"Прогресс считается по {dedup_total}, чтобы совпадало с реальной обработкой."
                )
        except Exception:
            pass

        log(f"Начинаем обработку {total_rows} строк")
        ws_send()
        
        # Батч-обработка: по 25 строк с промежуточным сохранением результатов
        batch_size = 25
        cross_progress_lock = threading.Lock()
        autopiter_adaptive_lock = threading.Lock()
        autopiter_adaptive_state = {
            'timeout_events': deque(maxlen=30),
            'force_single_until_row': -1,
            'is_degraded': False,
        }

        try:
            autopiter_adaptive_enabled = os.getenv("AUTOPITER_ADAPTIVE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
        except Exception:
            autopiter_adaptive_enabled = True
        try:
            autopiter_timeout_window = int(os.getenv("AUTOPITER_TIMEOUT_WINDOW", "30"))
        except Exception:
            autopiter_timeout_window = 30
        try:
            autopiter_timeout_threshold = float(os.getenv("AUTOPITER_TIMEOUT_THRESHOLD", "0.35"))
        except Exception:
            autopiter_timeout_threshold = 0.35
        try:
            autopiter_recover_threshold = float(os.getenv("AUTOPITER_TIMEOUT_RECOVER_THRESHOLD", "0.15"))
        except Exception:
            autopiter_recover_threshold = 0.15
        try:
            autopiter_degrade_min_samples = int(os.getenv("AUTOPITER_TIMEOUT_MIN_SAMPLES", "10"))
        except Exception:
            autopiter_degrade_min_samples = 10
        try:
            autopiter_degrade_cooldown_rows = int(os.getenv("AUTOPITER_DEGRADE_COOLDOWN_ROWS", "8"))
        except Exception:
            autopiter_degrade_cooldown_rows = 8

        autopiter_timeout_window = max(10, min(200, autopiter_timeout_window))
        autopiter_timeout_threshold = max(0.05, min(0.95, autopiter_timeout_threshold))
        autopiter_recover_threshold = max(0.01, min(0.90, autopiter_recover_threshold))
        autopiter_degrade_min_samples = max(5, min(100, autopiter_degrade_min_samples))
        autopiter_degrade_cooldown_rows = max(2, min(100, autopiter_degrade_cooldown_rows))
        autopiter_adaptive_state['timeout_events'] = deque(maxlen=autopiter_timeout_window)

        def _is_timeout_like_autopiter_error(exc: Exception) -> bool:
            if isinstance(exc, AutopiterNetworkException):
                return True
            text = str(exc).lower()
            timeout_markers = (
                "timed out",
                "timeout",
                "read timed out",
                "readtimeout",
                "httpconnectionpool",
                "connection broken",
                "renderer",
                "tab crashed",
                "message from renderer",
            )
            return any(marker in text for marker in timeout_markers)

        def _record_autopiter_event(is_timeout: bool, row_idx: int):
            if not autopiter_adaptive_enabled:
                return
            with autopiter_adaptive_lock:
                events = autopiter_adaptive_state['timeout_events']
                events.append(1 if is_timeout else 0)
                samples = len(events)
                if samples < autopiter_degrade_min_samples:
                    return
                timeout_ratio = (sum(events) / samples) if samples else 0.0
                if (not autopiter_adaptive_state['is_degraded']) and timeout_ratio >= autopiter_timeout_threshold:
                    autopiter_adaptive_state['is_degraded'] = True
                    autopiter_adaptive_state['force_single_until_row'] = row_idx + autopiter_degrade_cooldown_rows
                    log(
                        f"Autopiter adaptive: рост таймаутов ({timeout_ratio:.0%}, {samples} событий), "
                        f"временно снижаем до 1 потока до строки {autopiter_adaptive_state['force_single_until_row'] + 1}"
                    )

        def _resolve_autopiter_workers(nnums: int, configured_workers: int, row_idx: int) -> int:
            if not autopiter_adaptive_enabled:
                return max(1, min(nnums, configured_workers))
            with autopiter_adaptive_lock:
                is_degraded = autopiter_adaptive_state['is_degraded']
                force_until = autopiter_adaptive_state['force_single_until_row']
                events = autopiter_adaptive_state['timeout_events']
                samples = len(events)
                timeout_ratio = (sum(events) / samples) if samples else 0.0

                if is_degraded and row_idx > force_until:
                    if samples >= autopiter_degrade_min_samples and timeout_ratio <= autopiter_recover_threshold:
                        autopiter_adaptive_state['is_degraded'] = False
                        log(
                            f"Autopiter adaptive: таймауты снизились ({timeout_ratio:.0%}, {samples} событий), "
                            "возвращаем 2 потока (или значение AUTOPITER_MAX_WORKERS)"
                        )
                    else:
                        autopiter_adaptive_state['force_single_until_row'] = row_idx + autopiter_degrade_cooldown_rows

                use_single = autopiter_adaptive_state['is_degraded'] and row_idx <= autopiter_adaptive_state['force_single_until_row']

            selected = 1 if use_single else configured_workers
            return max(1, min(nnums, selected))

        # Armtek adaptive parallelism
        armtek_adaptive_lock = threading.Lock()
        armtek_adaptive_state = {
            'timeout_events': deque(maxlen=20),
            'force_single_until_row': -1,
            'is_degraded': False,
        }
        try:
            armtek_adaptive_enabled = os.getenv("ARMTEK_ADAPTIVE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
        except Exception:
            armtek_adaptive_enabled = True
        try:
            armtek_timeout_window = int(os.getenv("ARMTEK_TIMEOUT_WINDOW", "20"))
        except Exception:
            armtek_timeout_window = 20
        try:
            armtek_timeout_threshold = float(os.getenv("ARMTEK_TIMEOUT_THRESHOLD", "0.30"))
        except Exception:
            armtek_timeout_threshold = 0.30
        try:
            armtek_recover_threshold = float(os.getenv("ARMTEK_TIMEOUT_RECOVER_THRESHOLD", "0.12"))
        except Exception:
            armtek_recover_threshold = 0.12
        try:
            armtek_degrade_min_samples = int(os.getenv("ARMTEK_TIMEOUT_MIN_SAMPLES", "8"))
        except Exception:
            armtek_degrade_min_samples = 8
        try:
            armtek_degrade_cooldown_rows = int(os.getenv("ARMTEK_DEGRADE_COOLDOWN_ROWS", "8"))
        except Exception:
            armtek_degrade_cooldown_rows = 8

        armtek_timeout_window = max(10, min(200, armtek_timeout_window))
        armtek_timeout_threshold = max(0.05, min(0.95, armtek_timeout_threshold))
        armtek_recover_threshold = max(0.01, min(0.90, armtek_recover_threshold))
        armtek_degrade_min_samples = max(5, min(100, armtek_degrade_min_samples))
        armtek_degrade_cooldown_rows = max(2, min(100, armtek_degrade_cooldown_rows))
        armtek_adaptive_state['timeout_events'] = deque(maxlen=armtek_timeout_window)

        def _is_timeout_like_armtek_error(exc: Exception) -> bool:
            text = str(exc).lower()
            markers = (
                "timed out",
                "timeout",
                "read timed out",
                "renderer",
                "tab crashed",
                "message from renderer",
                "httpconnectionpool",
                "connection broken",
                "max retries exceeded",
                "script timeout",
            )
            return any(m in text for m in markers)

        def _record_armtek_event(is_timeout: bool, row_idx: int):
            if not armtek_adaptive_enabled:
                return
            with armtek_adaptive_lock:
                events = armtek_adaptive_state['timeout_events']
                events.append(1 if is_timeout else 0)
                samples = len(events)
                if samples < armtek_degrade_min_samples:
                    return
                ratio = (sum(events) / samples) if samples else 0.0
                if (not armtek_adaptive_state['is_degraded']) and ratio >= armtek_timeout_threshold:
                    armtek_adaptive_state['is_degraded'] = True
                    armtek_adaptive_state['force_single_until_row'] = row_idx + armtek_degrade_cooldown_rows
                    log(
                        f"Armtek adaptive: рост таймаутов ({ratio:.0%}, {samples} событий), "
                        f"временно снижаем до 1 потока до строки {armtek_adaptive_state['force_single_until_row'] + 1}"
                    )

        def _resolve_armtek_workers(nnums: int, configured_workers: int, row_idx: int) -> int:
            if not armtek_adaptive_enabled:
                return max(1, min(nnums, configured_workers))
            with armtek_adaptive_lock:
                is_degraded = armtek_adaptive_state['is_degraded']
                force_until = armtek_adaptive_state['force_single_until_row']
                events = armtek_adaptive_state['timeout_events']
                samples = len(events)
                ratio = (sum(events) / samples) if samples else 0.0

                if is_degraded and row_idx > force_until:
                    if samples >= armtek_degrade_min_samples and ratio <= armtek_recover_threshold:
                        armtek_adaptive_state['is_degraded'] = False
                        log(
                            f"Armtek adaptive: таймауты снизились ({ratio:.0%}, {samples} событий), "
                            "возвращаем 2 потока (или значение ARMTEK_MAX_WORKERS)"
                        )
                    else:
                        armtek_adaptive_state['force_single_until_row'] = row_idx + armtek_degrade_cooldown_rows

                use_single = armtek_adaptive_state['is_degraded'] and row_idx <= armtek_adaptive_state['force_single_until_row']
            selected = 1 if use_single else configured_workers
            return max(1, min(nnums, selected))
        
        # Собираем ВСЕ артикулы из файла, чтобы обработать их отдельными проходами
        all_records = []  # (brand_from_e, part_number_from_f, name_from_b, num)
        for _, row in df.iterrows():
            brand_from_e_raw = safe_cell_to_str(row.iloc[4]) if len(row) > 4 else ''
            brand_from_e = brand_from_e_raw.strip() if brand_from_e_raw else ''
            
            # Фильтрация бренда как артикула
            if brand_from_e:
                brand_from_e_raw_lower = brand_from_e.lower()
                is_article = (
                    (brand_from_e_raw_lower.startswith('d-') and any(c.isdigit() for c in brand_from_e)) or
                    (brand_from_e_raw_lower.startswith('dz') and any(c.isdigit() for c in brand_from_e)) or
                    (brand_from_e and brand_from_e[0].isdigit() and 
                     sum(1 for c in brand_from_e if c.isdigit()) > len(brand_from_e) * 0.7)
                )
                if is_article:
                    brand_from_e = ''

            part_number_from_f = safe_cell_to_str(row.iloc[5]) if len(row) > 5 else ''
            name_from_b = safe_cell_to_str(row.iloc[1]) if len(row) > 1 else ''
            cross_number_from_g = safe_cell_to_str(row.iloc[6]) if len(row) > 6 else ''
            numbers_source_value = cross_number_from_g if cross_number_from_g else part_number_from_f
            
            if not numbers_source_value:
                continue
            
            numbers_to_parse = [n.strip() for n in numbers_source_value.split(';') if n.strip()]
            deduped_numbers = []
            seen_norm_articles = set()
            for num in numbers_to_parse:
                norm = normalize_article_for_compare(num)
                if not norm or norm in seen_norm_articles:
                    continue
                seen_norm_articles.add(norm)
                deduped_numbers.append(num)
            
            for num in deduped_numbers:
                all_records.append((brand_from_e, part_number_from_f, name_from_b, num))

        # Вспомогательная функция для обработки одного артикула в разных источниках
        def process_single_record_for_source(source, record):
            brand_from_e, part_number_from_f, name_from_b, num = record
            try:
                proxy = None
                if source == 'autopiter' and autopiter_proxy_enabled:
                    proxy = get_proxy_string()
                elif source == 'emex' and emex_use_proxy_enabled:
                    proxy = get_proxy_string()
                
                # Получаем бренды в зависимости от источника
                if source == 'autopiter':
                    brands = get_brands_by_artikul(num, proxy)
                    brands = filter_garbage_brands(brands, source='autopiter')
                elif source == 'emex':
                    brands = get_brands_by_artikul_emex(num, proxy)
                    brands = filter_garbage_brands(brands, source='emex')
                else:  # armtek
                    brands = get_brands_by_artikul_armtek(num, None)  # всегда без прокси
                    if brands:
                        brands = filter_armtek_brands(split_combined_brands(brands))
                
                records_for_source = []
                if brands:
                    for b2 in brands:
                        for single_brand in _split_comma_separated_brands(b2):
                            single_brand = single_brand.lstrip('_').strip()
                            if not single_brand:
                                continue
                            # Не добавляем артикулы/цифровые мусорные значения
                            if (single_brand.lower().startswith('d-') or
                                single_brand.lower().startswith('dz') or
                                (single_brand and single_brand[0].isdigit()) or
                                sum(1 for c in single_brand if c.isdigit()) > len(single_brand) * 0.6):
                                continue
                            
                            normalized_article = normalize_article_for_compare(num)
                            if normalized_article:
                                d = {
                                    'Бренд № 1': clean_excel_string(brand_from_e),
                                    'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),
                                    'Наименование': clean_excel_string(name_from_b),
                                    'Бренд № 2': clean_excel_string(single_brand),
                                    'Артикул по Бренду № 2': clean_excel_string(num),
                                    'Источник': source
                                }
                                records_for_source.append(d)
                else:
                    # Для Armtek добавляем запись "Бренды не найдены"
                    if source == 'armtek':
                        d = {
                            'Бренд № 1': clean_excel_string(brand_from_e),
                            'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),
                            'Наименование': clean_excel_string(name_from_b),
                            'Бренд № 2': 'Бренды не найдены',
                            'Артикул по Бренду № 2': clean_excel_string(num),
                            'Источник': source
                        }
                        records_for_source.append(d)
                return records_for_source
            except Exception as e:
                log(f"Error processing {source} for {num}: {str(e)}")
                return []

        def on_article_done(num):
            """Прогресс по кросс-номерам: +1 после завершения Автопитера."""
            with cross_progress_lock:
                task._processed_cross_numbers = getattr(task, '_processed_cross_numbers', 0) + 1
                task._current_number = str(num) if num is not None else ''
                if not isinstance(task.sources, dict):
                    task.sources = {}
                if '_meta' not in task.sources:
                    task.sources['_meta'] = {}
                task.sources['_meta'].update({
                    'current_number': task._current_number,
                    'total_cross_numbers': getattr(task, '_total_cross_numbers', 0),
                    'processed_cross_numbers': getattr(task, '_processed_cross_numbers', 0),
                })
                ws_send()

        autopiter_proxy_enabled = is_autopiter_proxy_enabled()
        # определяем переменную для Emex
        emex_use_proxy_enabled = os.getenv('EMEX_USE_PROXY', '0').strip().lower() in ('1', 'true', 'yes')

        # ===== ПЕРВЫЙ ПРОХОД: ТОЛЬКО AUTOPITER =====
        autopiter_workers = 3  # Автопитер лучше держать на одном потоке для стабильности
        log(f"Начинаем обработку всех артикулов через AUTOPITER ({len(all_records)} шт.)")

        with concurrent.futures.ThreadPoolExecutor(max_workers=autopiter_workers) as executor:
            future_map = {executor.submit(process_single_record_for_source, 'autopiter', rec): rec for rec in all_records}
            for future in concurrent.futures.as_completed(future_map):
                rec = future_map[future]
                try:
                    res_list = future.result()
                    results_autopiter.extend(res_list)
                    # Обновляем прогресс только на этом этапе
                    on_article_done(rec[3])
                except Exception as e:
                    log(f"Ошибка обработки Autopiter для {rec[3]}: {str(e)}")
                    
        # ===== ВТОРОЙ ПРОХОД: ТОЛЬКО EMEX =====
        emex_parallel = 5  # можно оставить как было
        log(f"Начинаем обработку всех артикулов через EMEX ({len(all_records)} шт.)")

        with concurrent.futures.ThreadPoolExecutor(max_workers=emex_parallel) as executor:
            future_map = {executor.submit(process_single_record_for_source, 'emex', rec): rec for rec in all_records}
            for future in concurrent.futures.as_completed(future_map):
                rec = future_map[future]
                try:
                    results_emex.extend(future.result())
                except Exception as e:
                    log(f"Ошибка обработки Emex для {rec[3]}: {str(e)}")

        # ===== ТРЕТИЙ ПРОХОД: ТОЛЬКО ARMTEK =====
        armtek_workers = 1
        log(f"Начинаем обработку всех артикулов через ARMTEK ({len(all_records)} шт.)")

        with concurrent.futures.ThreadPoolExecutor(max_workers=armtek_workers) as executor:
            future_map = {executor.submit(process_single_record_for_source, 'armtek', rec): rec for rec in all_records}
            for future in concurrent.futures.as_completed(future_map):
                rec = future_map[future]
                try:
                    results_armtek.extend(future.result())
                except Exception as e:
                    log(f"Ошибка обработки Armtek для {rec[3]}: {str(e)}")

        # Собираем статистику вручную (эмулируем старый цикл)
        stats = {
            'rows_processed': total_rows,
            'brand1_filtered_as_article': 0,
            'brand2_filtered_as_article': 0,
            'brand2_filtered_as_garbage': 0,
            'unique_brands': {
                'autopiter': set(),
                'emex': set(),
                'armtek': set(),
            }
        }
        
        for d in results_autopiter:
            stats['unique_brands']['autopiter'].add(d.get('Бренд № 2', ''))
        for d in results_emex:
            stats['unique_brands']['emex'].add(d.get('Бренд № 2', ''))
        for d in results_armtek:
            stats['unique_brands']['armtek'].add(d.get('Бренд № 2', ''))

        # Обновляем итоговые счетчики строк (эмуляция старого цикла)
        task._processed_rows = total_rows
        task._current_row = total_rows
        task._processed_cross_numbers = getattr(task, '_total_cross_numbers', 0)
        
        if not isinstance(task.sources, dict):
            task.sources = {}
        if '_meta' not in task.sources:
            task.sources['_meta'] = {}
        task.sources['_meta'].update({
            'processed_rows': task._processed_rows,
            'current_row': task._current_row,
            'total_rows': task._total_rows,
            'processed_cross_numbers': task._processed_cross_numbers
        })
        update_task_fields(sources=task.sources, status='in_progress')
        ws_send()

        completion_log = f"[{datetime.now().strftime('%d.%m.%Y, %H:%M:%S')}] Обработка завершена. Обработано строк: {task._processed_rows} из {total_rows}"
        log(completion_log)
        print(f"[DEBUG] {completion_log}")
        ensure_not_cancelled()
        
        # Создаем результаты
        try:
            if results_autopiter:
                results_autopiter = dedupe_rows(results_autopiter)
                df_autopiter = pd.DataFrame(results_autopiter)
                autopiter_file = f'media/results/autopiter_results_{task.id}.xlsx'
                try:
                    df_autopiter.to_excel(autopiter_file, index=False, engine='openpyxl')
                    log(f"Создан файл Autopiter: {autopiter_file}")
                except Exception as e:
                    log(f"Ошибка создания файла Autopiter: {str(e)}")
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
                    df_armtek.to_excel(armtek_file, index=False, engine='openpyxl')
                    log(f"Создан файл Armtek: {armtek_file}")
                except Exception as e:
                    log(f"Ошибка создания файла Armtek: {str(e)}")
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
                    df_emex.to_excel(emex_file, index=False, engine='openpyxl')
                    log(f"Создан файл Emex: {emex_file}")
                except Exception as e:
                    log(f"Ошибка создания файла Emex: {str(e)}")
                    df_emex.to_excel(emex_file, index=False)
                    log(f"Создан файл Emex (без engine): {emex_file}")
                task.result_files = task.result_files or {}
                task.result_files['emex'] = emex_file
                log(f"Файл Emex добавлен в result_files: {emex_file}")
        except Exception as e:
            log(f"Критическая ошибка при создании Excel файлов: {str(e)}")
        
        # Итоговый отчёт по качеству и уникальным брендам
        try:
            os.makedirs('media/results', exist_ok=True)

            summary_lines = [
                f"Обработано строк: {stats['rows_processed']} из {total_rows}",
                f"Бренд №1 отфильтрован как артикул: {stats['brand1_filtered_as_article']}",
                f"Бренд №2 отфильтрован как артикул: {stats['brand2_filtered_as_article']}",
                f"Бренд №2 отфильтрован как мусор: {stats['brand2_filtered_as_garbage']}",
                "",
                f"Уникальные бренды Autopiter: {len(stats['unique_brands']['autopiter'])}",
                f"Уникальные бренды Emex: {len(stats['unique_brands']['emex'])}",
                f"Уникальные бренды Armtek: {len(stats['unique_brands']['armtek'])}",
            ]

            if results_armtek:
                armtek_q = compute_armtek_quality_metrics(results_armtek)
                summary_lines.extend([
                    "",
                    f"Armtek — всего записей брендов: {armtek_q['total']}",
                    f"Armtek — «Бренды не найдены»: {armtek_q['not_found']} ({armtek_q['not_found_pct']}%)",
                    f"Armtek — мусорные бренды: {armtek_q['garbage']} ({armtek_q['garbage_pct']}%)",
                    f"Armtek — валидные бренды: {armtek_q['valid']} ({armtek_q['valid_pct']}%)",
                ])
                log(
                    f"Armtek качество: not_found={armtek_q['not_found_pct']}%, "
                    f"garbage={armtek_q['garbage_pct']}%, valid={armtek_q['valid_pct']}%"
                )
                if not isinstance(task.sources, dict):
                    task.sources = {}
                task.sources.setdefault('_meta', {})['armtek_quality'] = armtek_q

            # Сохраняем summary в Excel
            summary_df = pd.DataFrame([line.split(': ', 1) for line in summary_lines if line],
                                      columns=['Показатель', 'Значение'])
            summary_path = f"media/results/summary_{task.id}.xlsx"
            task.result_files = task.result_files or {}
            summary_df.to_excel(summary_path, index=False, engine='openpyxl')
            task.result_files['summary'] = summary_path
            log(f"Создан файл summary (xlsx): {summary_path}")

            # Экспорт уникальных брендов
            unique_rows = []
            for source_name, brands_set in stats['unique_brands'].items():
                for b in sorted(brands_set):
                    unique_rows.append({'Источник': source_name, 'Бренд': b})
            if unique_rows:
                df_unique = pd.DataFrame(unique_rows)
                unique_path = f"media/results/unique_brands_{task.id}.xlsx"
                df_unique.to_excel(unique_path, index=False, engine='openpyxl')
                task.result_files['unique_brands'] = unique_path
                log(f"Создан файл уникальных брендов: {unique_path}")
        except Exception as e:
            log(f"Ошибка создания итогового отчёта или файла уникальных брендов: {str(e)}")
        
        # Принудительно сохраняем task с файлами
        update_task_fields(status='completed', result_files=task.result_files)
        log(f"Task завершен. Result files: созданы файлы результатов")
        ws_send()
        
        # Очистка Chrome процессов и пула драйверов
        cleanup_chrome_processes()
        cleanup_driver_pool()
        
        # Финальная очистка и подтверждение завершения
        log(f"Task {task_id} успешно завершена. Обработано строк: {task._processed_rows}")
        
        return {
            'status': 'completed',
            'task_id': task_id,
            'result_files': {},
            'processed_rows': task._processed_rows,
            'message': 'Task completed successfully'
        }
        
    except TaskCancelledException:
        log(f"Task {task_id} отменена пользователем")
        cleanup_chrome_processes()
        cleanup_driver_pool()
        return {
            'status': 'cancelled',
            'task_id': task_id,
            'message': 'Task was cancelled'
        }
    except Exception as e:
        task.status = 'error'
        task.error_message = str(e)
        try:
            update_task_fields(status='error', error_message=str(e))
        except TaskCancelledException:
            pass
        ws_send()
        cleanup_chrome_processes()
        cleanup_driver_pool()
        raise 
    finally:
        clear_parsing_task_cancelled(task_id)