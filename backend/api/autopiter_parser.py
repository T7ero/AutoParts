import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
import re
from urllib.parse import quote, unquote
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc

try:
    import fcntl  # Linux/Docker: межпроцессная блокировка создания Chrome
except ImportError:
    fcntl = None  # type: ignore

try:
    import redis  # type: ignore
except Exception:
    redis = None

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
SELENIUM_TIMEOUT = 20 # Оптимизированное время для ускорения
PAGE_LOAD_TIMEOUT = 30  # Увеличиваем для стабильности

# Настройки для пула драйверов
DRIVER_POOL_SIZE = 2
DRIVER_CREATION_RETRIES = 4  # Увеличиваем с 2 до 4
DRIVER_TIMEOUT_RETRIES = 3  # Увеличиваем количество попыток

# Один Chrome на воркер — иначе в Docker ловим "failed to start a thread"
CHROME_CREATE_SEMAPHORE = threading.Semaphore(1)
_CHROME_CREATE_LOCK_PATH = os.path.join(tempfile.gettempdir(), "autoparts_chrome_create.lock")

# Armtek Selenium: отключаем после серии ошибок ресурсов, чтобы не спамить chromedriver
ARMTEK_SELENIUM_FAILURES = 0
ARMTEK_SELENIUM_DISABLED = False
MAX_ARMTEK_SELENIUM_FAILURES = 2

# Autopiter Selenium: отключаем после серии ошибок
#AUTOPITER_SELENIUM_FAILURES = 0
#AUTOPITER_SELENIUM_DISABLED = False
#MAX_AUTOPITER_SELENIUM_FAILURES = 2

# сброс плохих прокси по времени:
BAD_PROXIES_EXPIRE = 300  # 5 минут
BAD_PROXIES_TIMESTAMP = {}  # словарь для отслеживания времени

# ===== ДОБАВИТЬ НОВЫЕ ПЕРЕМЕННЫЕ =====
CHROME_MAX_PROCESSES = int(os.getenv("CHROME_MAX_PROCESSES", "10"))
ARMTEK_CLEANUP_INTERVAL = int(os.getenv("ARMTEK_CLEANUP_INTERVAL", "3"))

_AUTOPITER_REQUEST_LOCK = threading.Lock()

class _ChromeCreateLock:
    """Сериализует запуск Chrome между потоками и celery fork-процессами."""

    def __enter__(self):
        CHROME_CREATE_SEMAPHORE.acquire()
        self._fp = None
        if fcntl is not None:
            try:
                self._fp = open(_CHROME_CREATE_LOCK_PATH, "a+", encoding="utf-8")
                fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX)
            except Exception as e:
                log_debug(f"Chrome lock (fcntl) недоступен: {e}")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._fp is not None:
            try:
                fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
                self._fp.close()
            except Exception:
                pass
        CHROME_CREATE_SEMAPHORE.release()
        return False


def reset_autopiter_selenium_state() -> None:
    """Сброс счётчика ошибок Autopiter Selenium."""
    global AUTOPITER_SELENIUM_FAILURES, AUTOPITER_SELENIUM_DISABLED
    AUTOPITER_SELENIUM_FAILURES = 0
    AUTOPITER_SELENIUM_DISABLED = False


def reset_armtek_selenium_state() -> None:
    """Сброс счётчика ошибок Armtek Selenium (начало новой задачи парсинга)."""
    global ARMTEK_SELENIUM_FAILURES, ARMTEK_SELENIUM_DISABLED
    ARMTEK_SELENIUM_FAILURES = 0
    ARMTEK_SELENIUM_DISABLED = False


def reset_emex_parser_state() -> None:
    """Сброс глобального состояния Emex между задачами Celery (воркер живёт долго)."""
    global EMEX_SELENIUM_FAILURES, EMEX_SELENIUM_DISABLED
    EMEX_SELENIUM_FAILURES = 0
    EMEX_SELENIUM_DISABLED = False


def _emex_use_proxy_enabled() -> bool:
    return os.getenv('EMEX_USE_PROXY', '0').strip().lower() in ('1', 'true', 'yes')


def _note_armtek_selenium_driver_failure() -> None:
    global ARMTEK_SELENIUM_FAILURES, ARMTEK_SELENIUM_DISABLED
    ARMTEK_SELENIUM_FAILURES += 1
    if ARMTEK_SELENIUM_FAILURES >= MAX_ARMTEK_SELENIUM_FAILURES:
        ARMTEK_SELENIUM_DISABLED = True
        log_debug(
            f"Armtek Selenium отключён после {ARMTEK_SELENIUM_FAILURES} ошибок Chrome "
            f"(используем HTTP fallback)"
        )

_ARMTEK_BRAND_SPAN_SELECTOR = (
    'span.font__body2.brand--selecting, span.font_body2.brand--selecting, '
    'span.font__caption1.brand--selectable, span.brand--selecting, '
    'span.brand--selectable, [class*="brand--selecting"], [class*="brand--selectable"]'
)


def _selenium_remote_http_timeout_seconds() -> float:
    """Таймаут HTTP к локальному chromedriver (Selenium Wire Protocol)."""
    try:
        v = float(os.getenv("AUTOPITER_SELENIUM_HTTP_TIMEOUT", "30"))
    except Exception:
        v = 30.0
    return max(10.0, min(120.0, v))


def _selenium_pool_health_check_timeout_seconds() -> float:
    """Короткий таймаут только для проверки живости перед возвратом в пул."""
    try:
        v = float(os.getenv("AUTOPITER_SELENIUM_POOL_HEALTH_TIMEOUT", "5"))
    except Exception:
        v = 5.0
    return max(2.0, min(30.0, v))


def _set_selenium_remote_command_timeout(driver, seconds: Optional[float]) -> None:
    """Ограничивает длительность HTTP-запросов к chromedriver (не путать с page load timeout)."""
    if driver is None:
        return
    ce = getattr(driver, "command_executor", None)
    if ce is None or not hasattr(ce, "set_timeout"):
        return
    try:
        ce.set_timeout(seconds)
    except Exception:
        pass

# Кеширование
REQUEST_CACHE = {}
CACHE_EXPIRATION = 600
FAILED_REQUESTS_CACHE = {}

# Пул HTTP-сессий на поток: переиспользование keep-alive и пула соединений (заметно ускоряет Autopiter/Emex API)
_HTTP_SESSION_TLS = threading.local()
_HTTP_POOL_CONN = 32
_HTTP_POOL_SIZE = 32


def _get_thread_requests_session() -> requests.Session:
    """Одна Session на поток с пулом соединений urllib3."""
    if getattr(_HTTP_SESSION_TLS, "session", None) is None:
        sess = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=_HTTP_POOL_CONN,
            pool_maxsize=_HTTP_POOL_SIZE,
            max_retries=0,
        )
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        _HTTP_SESSION_TLS.session = sess
    return _HTTP_SESSION_TLS.session

# Глобальная переменная для хранения прокси
PROXY_LIST = []
PROXY_INDEX = 0
# Набор проблемных прокси, которые следует временно исключать
BAD_PROXIES: Set[str] = set()

# Состояние для Emex Selenium: чтобы не создавать тысячи "падающих" сессий
EMEX_SELENIUM_FAILURES = 0
EMEX_SELENIUM_DISABLED = False
MAX_EMEX_SELENIUM_FAILURES = 3


class AutopiterRateLimitException(Exception):
    """Autopiter вернул rate-limit и нам нужно повторить позже."""
    pass


class AutopiterForbiddenException(Exception):
    """Autopiter временно запретил доступ (403), требуется повторить позже."""
    pass


class AutopiterNetworkException(Exception):
    """Сетевая ошибка/таймаут Autopiter. Нельзя негативно кэшировать надолго."""
    pass


class AutopiterBlockedException(Exception):
    """Autopiter показал captcha/страницу ошибки вместо каталога."""
    pass


_AUTOPITER_BLOCK_MARKERS = (
    'я не робот',
    'вы очень активный',
    'мы временно ограничили ваш доступ',
    'errorpage',
    'smartcaptcha',
    'captcha',
    'подтвердите, что вы не робот',
    'подтвердите что вы не робот',
)


def _autopiter_page_blocked(page_source: str) -> bool:
    """True, если вместо каталога показана captcha или страница ошибки."""
    if not page_source:
        return True
    low = page_source.lower()
    if any(marker in low for marker in _AUTOPITER_BLOCK_MARKERS):
        return True
    # ErrorPage без строк таблицы — типичный признак блокировки
    if 'errorpage' in low and 'individualtablerow' not in low:
        return True
    return False


def looks_like_analytics_garbage_token(text: str) -> bool:
    """Отсекает случайные JS/analytics-токены вроде LDwBSShMoYhCzEpEE."""
    s = (text or '').strip()
    if len(s) < 10 or ' ' in s:
        return False
    if not re.fullmatch(r'[A-Za-z0-9_-]+', s):
        return False
    letters = sum(1 for c in s if c.isalpha())
    if letters < 8:
        return False
    has_upper = any(c.isupper() for c in s)
    has_lower = any(c.islower() for c in s)
    has_digit = any(c.isdigit() for c in s)
    vowels = sum(1 for c in s.lower() if c in 'aeiouаеёиоуыэюя')
    if has_upper and has_lower and has_digit and len(s) >= 14:
        return True
    if letters >= 10 and vowels <= 1:
        return True
    return False

# Autopiter очень чувствителен к burst-нагрузке.
class _AutopiterAdaptiveLimiter:
    def __init__(self, min_interval: float = 0.25, max_interval: float = 2.5) -> None:
        self._min_interval = float(min_interval)
        self._max_interval = float(max_interval)
        self._interval = float(min_interval)
        self._next_allowed = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        """Ждём до разрешённого времени и резервируем следующий слот."""
        while True:
            with self._lock:
                now = time.time()
                wait_for = self._next_allowed - now
                if wait_for <= 0:
                    self._next_allowed = now + self._interval
                    return
            time.sleep(min(0.25, max(0.01, wait_for)))

    def penalize(self, cooldown: float) -> None:
        """Увеличиваем интервал и добавляем cooldown после 429/403."""
        try:
            cooldown = float(cooldown)
        except Exception:
            cooldown = self._max_interval
        cooldown = max(self._min_interval, min(self._max_interval, cooldown))
        with self._lock:
            self._interval = min(self._max_interval, max(self._interval, cooldown))
            now = time.time()
            self._next_allowed = max(self._next_allowed, now + cooldown)

    def reward(self) -> None:
        """Постепенно ускоряемся, если ответы успешные."""
        with self._lock:
            self._interval = max(self._min_interval, self._interval * 0.95)


_AUTOPITER_LIMITER = _AutopiterAdaptiveLimiter(min_interval=0.05, max_interval=3.0)

# Глобальный throttle (на все процессы celery), чтобы избежать "волн" 429.
_REDIS_THROTTLE_COOLDOWN_KEY = "autopiter:cooldown_until"
_REDIS_THROTTLE_LAST_TS_KEY = "autopiter:last_ts"
_REDIS_THROTTLE_EXPIRE_SECONDS = 120
_AUTOPITER_GLOBAL_MIN_INTERVAL = float(os.getenv("AUTOPITER_GLOBAL_MIN_INTERVAL", "0.25"))

_redis_local = threading.local()


def _get_redis_client():
    if redis is None:
        return None
    client = getattr(_redis_local, "client", None)
    if client is not None:
        return client
    try:
        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db = int(os.getenv("REDIS_DB", "0"))
        client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        _redis_local.client = client
        return client
    except Exception:
        return None


def _global_autopiter_throttle_wait() -> None:
    """Резервирует слот для следующего запроса к Autopiter."""
    client = _get_redis_client()
    if client is None:
        return

    try:
        now = time.time()
        lua = """
        local now = tonumber(ARGV[1])
        local min_interval = tonumber(ARGV[2])

        local cooldown_until = tonumber(redis.call('GET', KEYS[1]) or '0')
        local last_ts = tonumber(redis.call('GET', KEYS[2]) or '0')

        if now < cooldown_until then
          local next_allowed = cooldown_until
          if last_ts ~= nil and last_ts > 0 then
            local staggered = last_ts + min_interval
            if staggered > next_allowed then
              next_allowed = staggered
            end
          end
          redis.call('SET', KEYS[2], next_allowed)
          redis.call('EXPIRE', KEYS[2], 10)
          local wait_for = next_allowed - now
          if wait_for < 0 then
            wait_for = 0
          end
          return wait_for
        end

        local next_allowed = now
        if last_ts ~= nil and last_ts > 0 then
          next_allowed = last_ts + min_interval
          if now >= next_allowed then
            next_allowed = now
          end
        end

        redis.call('SET', KEYS[2], next_allowed)
        redis.call('EXPIRE', KEYS[2], 10)
        local wait_for = next_allowed - now
        if wait_for < 0 then
          wait_for = 0
        end
        return wait_for
        """
        wait_for = float(client.eval(lua, 2, _REDIS_THROTTLE_COOLDOWN_KEY, _REDIS_THROTTLE_LAST_TS_KEY, now, _AUTOPITER_GLOBAL_MIN_INTERVAL))
        if wait_for > 0:
            time.sleep(min(20.0, wait_for))
    except Exception:
        return


def _global_autopiter_penalize(cooldown: float) -> None:
    client = _get_redis_client()
    if client is None:
        return
    try:
        cooldown = float(cooldown)
        now = time.time()
        mult = float(os.getenv("AUTOPITER_GLOBAL_COOLDOWN_MULT", "1.8"))
        min_cooldown = float(os.getenv("AUTOPITER_GLOBAL_COOLDOWN_MIN", "2.0"))
        cap_cooldown = float(os.getenv("AUTOPITER_GLOBAL_COOLDOWN_CAP", "60.0"))
        enhanced = max(min_cooldown, cooldown * mult)
        enhanced = min(cap_cooldown, enhanced)
        new_until = now + enhanced
        existing = client.get(_REDIS_THROTTLE_COOLDOWN_KEY)
        try:
            existing_val = float(existing) if existing is not None else 0.0
        except Exception:
            existing_val = 0.0
        final_until = max(existing_val, new_until)
        client.set(_REDIS_THROTTLE_COOLDOWN_KEY, final_until, ex=_REDIS_THROTTLE_EXPIRE_SECONDS)
    except Exception:
        return

# Пул драйверов для Armtek
DRIVER_POOL: List[webdriver.Chrome] = []
DRIVER_POOL_LOCK = threading.Lock()
DRIVER_LAST_USED: Dict[int, float] = {}

DRIVER_USAGE_COUNT: Dict[int, int] = {}
MAX_USAGES_PER_DRIVER = 10  # сколько артикулов обрабатывает один драйвер

def log_debug(message):
    print(f"[DEBUG] {message}")


def _is_chrome_resource_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "failed to start a thread",
        "session not created",
        "resource temporarily unavailable",
        "cannot allocate memory",
        "too many open files",
        "errno 11",
        "errno 12",
        "errno 13",
    )
    return any(marker in text for marker in markers)


def _normalize_proxy_arg(proxy: Optional[Union[str, Dict[str, str]]]) -> Optional[str]:
    """Приводит прокси к строке ip:port или login:pass@ip:port для Selenium/HTTP."""
    if not proxy:
        return None
    if isinstance(proxy, dict):
        proxy_url = proxy.get('http') or proxy.get('https') or ''
        if isinstance(proxy_url, str) and proxy_url.startswith('http://'):
            return proxy_url[7:]
        if isinstance(proxy_url, str) and proxy_url.startswith('https://'):
            return proxy_url[8:]
        return None
    if isinstance(proxy, str):
        value = proxy.strip()
        if value.startswith('http://'):
            return value[7:]
        if value.startswith('https://'):
            return value[8:]
        return value or None
    return None


def _is_selenium_fatal_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "tab crashed",
        "chrome not reachable",
        "connection refused",
        "timed out receiving message from renderer",
        "script timeout",
        "httpconnectionpool",
        "read timed out",
        "failed to establish a new connection",
        "remote end closed",
        "invalid session id",
        "session not created",
        "no such window",
        "failed to start a thread",
    )
    return any(marker in text for marker in markers)


def _recover_armtek_driver(
    old_driver: Optional[webdriver.Chrome],
    proxy: Optional[str] = None,
) -> Optional[webdriver.Chrome]:
    """Закрывает битый драйвер и создаёт новый с уникальным user-data-dir."""
    if old_driver is not None:
        try:
            old_driver.quit()
        except Exception:
            pass
    temp_dir = tempfile.mkdtemp(prefix=f"chrome_armtek_{uuid.uuid4().hex[:8]}_")
    effective_proxy = _normalize_proxy_arg(proxy)
    if effective_proxy and '@' in effective_proxy:
        effective_proxy = None
    return _create_chrome_driver_robust(temp_dir, effective_proxy)


def get_driver_from_pool() -> Optional[webdriver.Chrome]:
    """Получает драйвер из пула или создает новый"""
    global DRIVER_POOL, DRIVER_POOL_LOCK, DRIVER_USAGE_COUNT
    
    with DRIVER_POOL_LOCK:
        if DRIVER_POOL:
            driver = DRIVER_POOL.pop()
            driver_id = id(driver)
            DRIVER_LAST_USED[driver_id] = time.time()
            # Обнуляем счетчик использований при выдаче из пула
            # (счетчик увеличивается при возврате)
            return driver
    
    # Создаем новый драйвер
    temp_dir = tempfile.mkdtemp(prefix=f"chrome_pool_{uuid.uuid4().hex[:8]}_")
    for attempt in range(DRIVER_CREATION_RETRIES):
        try:
            driver = _create_chrome_driver_robust(temp_dir)
            if driver:
                driver_id = id(driver)
                DRIVER_LAST_USED[driver_id] = time.time()
                DRIVER_USAGE_COUNT[driver_id] = 0  # начальное значение
                return driver
            time.sleep(1)
        except Exception as e:
            log_debug(f"Попытка {attempt + 1} создания драйвера: {str(e)}")
            time.sleep(2)
    
    return None

def return_driver_to_pool(driver: webdriver.Chrome):
    """Возвращает драйвер в пул или закрывает его"""
    global DRIVER_POOL, DRIVER_POOL_LOCK, DRIVER_LAST_USED, DRIVER_USAGE_COUNT
    
    if driver is None:
        return
    
    try:
        # Проверяем, жив ли драйвер
        ce = getattr(driver, "command_executor", None)
        old_http_timeout = None
        health_ok = False
        try:
            if ce is not None and hasattr(ce, "get_timeout"):
                old_http_timeout = ce.get_timeout()
                ce.set_timeout(_selenium_pool_health_check_timeout_seconds())
            _ = driver.title
            health_ok = True
        except Exception:
            health_ok = False
        finally:
            if ce is not None and hasattr(ce, "set_timeout"):
                try:
                    ce.set_timeout(old_http_timeout)
                except Exception:
                    pass

        if not health_ok:
            try:
                driver.quit()
            except Exception:
                pass
            DRIVER_LAST_USED.pop(id(driver), None)
            DRIVER_USAGE_COUNT.pop(id(driver), None)
            return

        driver_id = id(driver)
        
        # Проверяем счетчик использований
        usage_count = DRIVER_USAGE_COUNT.get(driver_id, 0) + 1
        if usage_count >= MAX_USAGES_PER_DRIVER:
            log_debug(f"Драйвер {driver_id} достиг лимита использований ({usage_count}), пересоздаём")
            try:
                driver.quit()
            except Exception:
                pass
            DRIVER_LAST_USED.pop(driver_id, None)
            DRIVER_USAGE_COUNT.pop(driver_id, None)
            return
        
        DRIVER_USAGE_COUNT[driver_id] = usage_count
        
        # Проверяем, не слишком ли старый драйвер
        if driver_id in DRIVER_LAST_USED:
            age = time.time() - DRIVER_LAST_USED[driver_id]
            if age > 300:  # 5 минут
                try:
                    driver.quit()
                except Exception:
                    pass
                DRIVER_LAST_USED.pop(driver_id, None)
                DRIVER_USAGE_COUNT.pop(driver_id, None)
                return
        
        with DRIVER_POOL_LOCK:
            if len(DRIVER_POOL) < DRIVER_POOL_SIZE:
                DRIVER_POOL.append(driver)
                DRIVER_LAST_USED[driver_id] = time.time()
            else:
                try:
                    driver.quit()
                except Exception:
                    pass
                DRIVER_LAST_USED.pop(driver_id, None)
                DRIVER_USAGE_COUNT.pop(driver_id, None)
    except Exception as e:
        log_debug(f"Ошибка возврата драйвера в пул: {str(e)}")
        try:
            driver.quit()
        except:
            pass
        DRIVER_LAST_USED.pop(id(driver), None)
        DRIVER_USAGE_COUNT.pop(id(driver), None)

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
    cleanup_chrome_processes()

def get_proxies_file_path() -> str:
    """Путь к файлу прокси в writable media/temp (не /app/proxies.txt на volume mount)."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(backend_dir, 'media', 'temp', 'proxies.txt')


def _resolve_proxies_file_path(file_path: Optional[str] = None) -> str:
    if file_path:
        return file_path
    primary = get_proxies_file_path()
    if os.path.exists(primary):
        return primary
    legacy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'proxies.txt')
    if os.path.exists(legacy):
        return legacy
    return primary


def load_proxies_from_file(file_path: Optional[str] = None) -> List[str]:
    """Загружает список прокси из файла"""
    global PROXY_LIST
    resolved_path = _resolve_proxies_file_path(file_path)
    try:
        if os.path.exists(resolved_path):
            with open(resolved_path, 'r', encoding='utf-8') as f:
                PROXY_LIST = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            log_debug(f"Загружено {len(PROXY_LIST)} прокси")
        else:
            log_debug(f"Файл прокси {resolved_path} не найден")
    except Exception as e:
        log_debug(f"Ошибка загрузки прокси: {e}")
    return PROXY_LIST


def _looks_like_host_port(part: str) -> bool:
    """True, если строка похожа на host:port (порт — число)."""
    if ':' not in part:
        return False
    host, port = part.rsplit(':', 1)
    if not port.isdigit():
        return False
    if re.fullmatch(r'\d{1,3}(\.\d{1,3}){3}', host):
        return True
    return '.' in host


def parse_proxy_line(proxy_str: str) -> Optional[Dict[str, str]]:
    """Парсит строку прокси в dict для requests.

    Поддерживаемые форматы:
    - login:password@host (без порта, порт будет добавлен автоматически)
    - login:password@ip:port
    - login:password@domain
    - ip:port
    """
    proxy_str = (proxy_str or '').strip()
    if not proxy_str or proxy_str.startswith('#'):
        return None

    # Если нет @, это просто host:port или host
    if '@' not in proxy_str:
        # Проверяем, есть ли порт
        if ':' in proxy_str:
            try:
                host, port = proxy_str.rsplit(':', 1)
                if port.isdigit():
                    url = f'http://{host}:{port}'
                    return {'http': url, 'https': url}
            except ValueError:
                pass
        # Если порта нет, генерируем случайный
        random_port = random.randint(10000, 10999)
        url = f'http://{proxy_str}:{random_port}'
        return {'http': url, 'https': url}

    # Разбираем login:password@host
    left, right = proxy_str.split('@', 1)
    
    # Проверяем, есть ли порт в правой части
    if ':' in right:
        host, port = right.rsplit(':', 1)
        if port.isdigit():
            # login:password@host:port
            login, password = left.split(':', 1)
            url = f'http://{quote(login, safe="")}:{quote(password, safe="")}@{host}:{port}'
            return {'http': url, 'https': url}
    
    # login:password@host (без порта) - генерируем случайный порт
    login, password = left.split(':', 1)
    random_port = random.randint(10000, 10999)
    url = f'http://{quote(login, safe="")}:{quote(password, safe="")}@{right}:{random_port}'
    return {'http': url, 'https': url}


def _session_set_proxy(session, proxy: Optional[Union[str, Dict[str, str]]]) -> Optional[Dict[str, str]]:
    """Настраивает requests.Session на прокси. Возвращает dict прокси или None."""
    session.proxies.clear()
    if not proxy:
        return None
    if isinstance(proxy, dict):
        session.proxies.update(proxy)
        return proxy
    proxy_value = str(proxy).strip()
    if proxy_value.startswith('http://'):
        proxy_value = proxy_value[7:]
    elif proxy_value.startswith('https://'):
        proxy_value = proxy_value[8:]
    proxy_dict = parse_proxy_line(proxy_value)
    if not proxy_dict:
        proxy_dict = {
            'http': f'http://{proxy_value}',
            'https': f'http://{proxy_value}',
        }
    session.proxies.update(proxy_dict)
    return proxy_dict


def _parse_proxy_credentials(proxy_value: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Возвращает (host, port, login, password) из строки прокси."""
    proxy_dict = parse_proxy_line(proxy_value)
    if not proxy_dict:
        return None, None, None, None
    url = proxy_dict.get('http', '')
    if url.startswith('http://'):
        url = url[7:]
    if '@' not in url:
        if ':' in url:
            host, port = url.rsplit(':', 1)
            return host, port, None, None
        return None, None, None, None
    auth_part, host_port = url.rsplit('@', 1)
    if ':' not in auth_part or ':' not in host_port:
        return None, None, None, None
    login, password = auth_part.split(':', 1)
    host, port = host_port.rsplit(':', 1)
    return host, port, unquote(login), unquote(password)


def _create_proxy_auth_extension(host: str, port: str, username: str, password: str) -> str:
    """Создаёт временное Chrome-расширение для HTTP-прокси с авторизацией."""
    plugin_dir = tempfile.mkdtemp(prefix='chrome_proxy_auth_')
    manifest_json = json.dumps({
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy Auth",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking",
        ],
        "background": {"scripts": ["background.js"]},
        "minimum_chrome_version": "76.0.0",
    }, ensure_ascii=True)
    background_js = f"""
var config = {{
    mode: "fixed_servers",
    rules: {{
        singleProxy: {{
            scheme: "http",
            host: {json.dumps(host)},
            port: parseInt({json.dumps(str(port))}, 10)
        }},
        bypassList: ["localhost", "127.0.0.1"]
    }}
}};
chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

function callbackFn(details) {{
    return {{
        authCredentials: {{
            username: {json.dumps(username)},
            password: {json.dumps(password)}
        }}
    }};
}}

chrome.webRequest.onAuthRequired.addListener(
    callbackFn,
    {{urls: ["<all_urls>"]}},
    ['blocking']
);
"""
    with open(os.path.join(plugin_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        f.write(manifest_json)
    with open(os.path.join(plugin_dir, 'background.js'), 'w', encoding='utf-8') as f:
        f.write(background_js)
    return plugin_dir


def _configure_chrome_proxy(chrome_options: Options, proxy: Optional[str]) -> bool:
    """Настраивает прокси в Chrome. Возвращает True, если загружено auth-расширение."""
    if not proxy:
        return False
    proxy_value = str(proxy).strip()
    if '@' in proxy_value:
        log_debug("Selenium: прокси с авторизацией не поддерживается, работаем без прокси")
        return False
    if proxy_value.startswith('http://'):
        proxy_value = proxy_value[7:]
    elif proxy_value.startswith('https://'):
        proxy_value = proxy_value[8:]
    host, port, login, password = _parse_proxy_credentials(proxy_value)
    if host and port and login and password:
        ext_dir = _create_proxy_auth_extension(host, port, login, password)
        chrome_options.add_argument(f'--load-extension={ext_dir}')
        log_debug(f"Selenium: прокси с авторизацией {_proxy_url_to_host_port(f'{login}:***@{host}:{port}')}")
        return True
    if host and port:
        chrome_options.add_argument(f'--proxy-server=http://{host}:{port}')
        log_debug(f"Selenium: прокси без авторизации {host}:{port}")
        return False
    chrome_options.add_argument(f'--proxy-server=http://{proxy_value}')
    log_debug(f"Selenium: прокси {proxy_value}")
    return False


def _proxy_url_to_host_port(proxy_url: str) -> str:
    """host:port из http://login:pass@host:port для логов."""
    value = proxy_url
    if value.startswith('http://'):
        value = value[7:]
    if '@' in value:
        value = value.split('@', 1)[1]
    return value


def get_next_proxy() -> Optional[Dict[str, str]]:
    global PROXY_LIST, PROXY_INDEX, BAD_PROXIES, BAD_PROXIES_TIMESTAMP
    
    # Очищаем старые плохие прокси (старше 5 минут)
    current_time = time.time()
    expired = [p for p, t in BAD_PROXIES_TIMESTAMP.items() if current_time - t > BAD_PROXIES_EXPIRE]
    for p in expired:
        BAD_PROXIES.discard(p)
        del BAD_PROXIES_TIMESTAMP[p]
    
    if not PROXY_LIST:
        load_proxies_from_file()
    if not PROXY_LIST:
        return None

    # Пробуем перебрать все прокси
    for _ in range(len(PROXY_LIST)):
        proxy_str = PROXY_LIST[PROXY_INDEX % len(PROXY_LIST)]
        PROXY_INDEX += 1
        
        if proxy_str in BAD_PROXIES:
            continue
        
        try:
            # Парсим прокси и возвращаем словарь
            proxy_dict = parse_proxy_line(proxy_str)
            if proxy_dict:
                log_debug(f"Используется прокси: {_proxy_url_to_host_port(proxy_dict['http'])}")
                return proxy_dict
        except Exception as e:
            log_debug(f"Ошибка парсинга прокси: {e}")
            BAD_PROXIES.add(proxy_str)
            BAD_PROXIES_TIMESTAMP[proxy_str] = time.time()
            continue
    
    # Если все прокси плохие - сбрасываем и пробуем сначала
    log_debug("Все прокси плохие, сбрасываем BAD_PROXIES")
    BAD_PROXIES.clear()
    BAD_PROXIES_TIMESTAMP.clear()
    return None


def _proxy_is_bad(proxy_line: str, proxy_dict: Optional[Dict[str, str]] = None) -> bool:
    """Проверяет, помечен ли прокси как проблемный (по строке файла или host:port)."""
    if proxy_line in BAD_PROXIES:
        return True
    if proxy_dict:
        host_port = _proxy_url_to_host_port(proxy_dict.get('http', ''))
        if host_port and host_port in BAD_PROXIES:
            return True
    parsed = parse_proxy_line(proxy_line)
    if parsed:
        host_port = _proxy_url_to_host_port(parsed.get('http', ''))
        if host_port and host_port in BAD_PROXIES:
            return True
    return False


def mark_proxy_bad(proxy_repr: str) -> None:
    """Помечает прокси как проблемный с временной меткой (по host:port!)"""
    global BAD_PROXIES, BAD_PROXIES_TIMESTAMP
    
    try:
        if proxy_repr.startswith('http://'):
            proxy_repr = proxy_repr[7:]
        elif proxy_repr.startswith('https://'):
            proxy_repr = proxy_repr[8:]
    except Exception:
        pass
    
    if not proxy_repr:
        return
        
    # ВАЖНО: Отрезаем логин и пароль
    if '@' in proxy_repr:
        proxy_repr = proxy_repr.split('@')[-1] # берем host:port
        
    BAD_PROXIES.add(proxy_repr)
    BAD_PROXIES_TIMESTAMP[proxy_repr] = time.time()
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


def is_autopiter_proxy_enabled() -> bool:
    """Нужно ли ходить на Autopiter через прокси."""
    explicit = os.getenv("AUTOPITER_USE_PROXY", "auto").strip().lower()
    if not PROXY_LIST:
        load_proxies_from_file()
    proxy_count = len(PROXY_LIST)
    if explicit in ("0", "false", "no", "off"):
        return False
    if explicit in ("1", "true", "yes", "on"):
        return proxy_count > 0
    return proxy_count > 0

def cleanup_chrome_processes():
    """Принудительно очищает процессы Chrome и временные директории"""
    try:
        # ВСЕГДА убиваем процессы, не проверяя количество
        for process_name in ['chrome', 'chromedriver', 'chromium']:
            try:
                subprocess.run(['pkill', '-9', '-f', process_name], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            except:
                pass
        
        # Очищаем временные директории
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
        
        time.sleep(0.5)
        
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
    """Выполняет HTTP-запрос с поддержкой прокси и повторными попытками."""
    session = _get_thread_requests_session()
    proxy_dict = _session_set_proxy(session, proxy)
    if proxy_dict:
        log_debug(f"Используется прокси: {_proxy_url_to_host_port(proxy_dict.get('http', ''))}")
    
    session.headers.update(HEADERS)
    
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
                    wait_time = 30 * (2 ** attempt)
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


def _create_chrome_driver_robust(temp_dir: Optional[str] = None, proxy: Optional[str] = None) -> Optional[webdriver.Chrome]:
    """Создает Chrome драйвер с улучшенной обработкой ошибок и retry логикой"""
    
    # Агрессивная очистка перед созданием
    for _ in range(2):
        try:
            subprocess.run(['pkill', '-9', '-f', 'chrome'], timeout=3, capture_output=True)
            subprocess.run(['pkill', '-9', '-f', 'chromedriver'], timeout=3, capture_output=True)
        except Exception:
            pass
    gc.collect()
    time.sleep(0.5)
    
    if not temp_dir:
        temp_dir = tempfile.mkdtemp(prefix=f"chrome_{uuid.uuid4().hex[:8]}_")
    
    with _ChromeCreateLock():
        for attempt in range(DRIVER_CREATION_RETRIES):
            try:
                chrome_options = Options()
                chrome_options.add_argument('--headless=new')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                # ===== НОВЫЕ АРГУМЕНТЫ ДЛЯ СТАБИЛЬНОСТИ =====
                chrome_options.add_argument('--disable-software-rasterizer')
                chrome_options.add_argument('--disable-features=VizDisplayCompositor')
                chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
                chrome_options.add_argument('--disable-background-timer-throttling')
                chrome_options.add_argument('--disable-backgrounding-occluded-windows')
                chrome_options.add_argument('--disable-renderer-backgrounding')
                chrome_options.add_argument('--disable-features=TranslateUI')
                chrome_options.add_argument('--disable-ipc-flooding-protection')
                chrome_options.add_argument('--disable-logging')
                chrome_options.add_argument('--disable-crash-reporter')
                chrome_options.add_argument('--disable-in-process-stack-traces')
                chrome_options.add_argument('--log-level=3')
                chrome_options.add_argument('--silent')
                chrome_options.add_argument('--disable-dev-tools')
                chrome_options.add_argument('--no-first-run')
                chrome_options.add_argument('--no-default-browser-check')
                
                # ===== ВАЖНО: ограничиваем память для Chrome =====
                chrome_options.add_argument('--memory-pressure-off')
                chrome_options.add_argument('--max_old_space_size=2048')
                
                # ===== ВАЖНО: ограничиваем количество процессов =====
                chrome_options.add_argument('--renderer-process-limit=2')
                
                # ===== ВАЖНО: отключаем ненужные фичи =====
                chrome_options.add_argument('--disable-extensions')
                chrome_options.add_argument('--disable-plugins')
                chrome_options.add_argument('--disable-images')
                chrome_options.add_argument('--disable-web-security')
                
                # ===== НОВОЕ: игнорируем прокси с авторизацией =====
                effective_proxy = None
                if proxy and '@' in str(proxy):
                    log_debug(f"Прокси с авторизацией не используется для Selenium, работаем без прокси")
                else:
                    effective_proxy = proxy

                proxy_extension_loaded = _configure_chrome_proxy(chrome_options, effective_proxy)
                if not proxy_extension_loaded:
                    chrome_options.add_argument('--disable-extensions')
                
                chrome_options.add_argument(f'--user-data-dir={temp_dir}')
                chrome_options.add_argument('--allow-running-insecure-content')

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
                    service = Service()

                chrome_options.page_load_strategy = 'eager'
                driver = webdriver.Chrome(service=service, options=chrome_options)
                _set_selenium_remote_command_timeout(driver, _selenium_remote_http_timeout_seconds())

                driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
                driver.set_script_timeout(max(20, PAGE_LOAD_TIMEOUT))
                driver.implicitly_wait(1)

                return driver

            except Exception as e:
                log_debug(f"Попытка {attempt + 1} создания Chrome драйвера: {str(e)}")
                if _is_chrome_resource_error(e):
                    cleanup_chrome_processes()
                    time.sleep(3 + attempt * 2)
                    break
                if attempt < DRIVER_CREATION_RETRIES - 1:
                    time.sleep(2 ** (attempt + 1))  # экспоненциальная задержка
                else:
                    log_debug(f"Не удалось создать Chrome драйвер после {DRIVER_CREATION_RETRIES} попыток")
                    return None

    return None


def parse_autopiter_selenium(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """Selenium для Autopiter отключён (используется только HTTP)."""
    log_debug(f"Autopiter Selenium отключён, пропускаем {artikul}")
    return []


def parse_autopiter_selenium_fallback(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """Selenium-фолбэк для нажатия кнопки 'Я не робот' и повторного сбора данных."""
    driver = None
    temp_dir = None
    try:
        # Создаем уникальный профиль Chrome
        temp_dir = tempfile.mkdtemp(prefix=f"chrome_autopiter_{uuid.uuid4().hex[:8]}_")
        # Используем вашу функцию создания драйвера
        driver = _create_chrome_driver_robust(temp_dir, proxy)
        if not driver:
            return []

        url = f"https://autopiter.ru/goods/{quote(artikul)}"
        driver.get(url)

        # Ждем появления кнопки "Я не робот" (CSS селектор с вашего скриншота)
        try:
            button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".Button__inner___ZjJiMW"))
            )
            # Имитация человеческого клика (двигаем мышь и ждем)
            actions = ActionChains(driver)
            actions.move_to_element(button).pause(0.5).click().perform()
            log_debug(f"Autopiter: нажата кнопка 'Я не робот' для {artikul}")

            # Ждем исчезновения экрана блокировки
            WebDriverWait(driver, 15).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, ".ErrorPage__textCol___ODE4M2"))
            )
            time.sleep(1) # Даем странице обновиться
            
            # Забираем обновленный HTML и парсим его вашей штатной функцией
            html = driver.page_source
            return parse_autopiter_response(html, artikul)

        except TimeoutException:
            # Если кнопка не появилась (блокировки нет или она уже снята)
            log_debug(f"Autopiter: кнопка не найдена, просто считываем страницу для {artikul}")
            html = driver.page_source
            return parse_autopiter_response(html, artikul)

    except Exception as e:
        log_debug(f"Autopiter Selenium fallback ошибка для {artikul}: {e}")
        return []
    finally:
        # Аккуратно закрываем браузер и чистим папку
        if driver:
            try: driver.quit()
            except: pass
        if temp_dir:
            try: shutil.rmtree(temp_dir, ignore_errors=True)
            except: pass

def get_brands_by_artikul(
    artikul: str,
    proxy: Optional[str] = None,
    force_http: bool = False,
) -> List[str]:
    """Получает бренды с Autopiter по артикулу (только HTTP)."""
    global AUTOPITER_SELENIUM_DISABLED
    
    try:
        log_debug(f"АвтоПитер: начинаем парсинг {artikul}")
        
        url = f"https://autopiter.ru/goods/{quote(artikul)}"
        
        session = _get_thread_requests_session()
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
        session.proxies.clear()
        
        if proxy:
            proxy_dict = _session_set_proxy(session, proxy)
            if proxy_dict:
                log_debug(f"АвтоПитер: использование прокси {_proxy_url_to_host_port(proxy_dict.get('http', ''))}")
        else:
            new_proxy_dict = get_next_proxy()
            if new_proxy_dict:
                session.proxies.clear()
                session.proxies.update(new_proxy_dict)
                log_debug(f"АвтоПитер: использование прокси {_proxy_url_to_host_port(new_proxy_dict.get('http', ''))}")

        max_attempts = 3
        request_timeout = 30
        
        for attempt in range(max_attempts):
            _global_autopiter_throttle_wait()
            _AUTOPITER_LIMITER.wait()

            try:
                with _AUTOPITER_REQUEST_LOCK:
                     response = session.get(url, timeout=request_timeout, allow_redirects=True)
            except requests.exceptions.Timeout as e:
                backoff = max(0.4, min(5.0, 0.6 * (2 ** attempt)))
                log_debug(f"АвтоПитер: timeout для {artikul}, backoff {backoff:.1f}s (attempt {attempt + 1}/{max_attempts})")
                _AUTOPITER_LIMITER.penalize(backoff)
                if attempt == max_attempts - 1:
                    return []
                time.sleep(backoff)
                continue
            except requests.exceptions.RequestException as e:
                err_text = str(e).lower()
                if '407' in err_text or 'proxy authentication required' in err_text:
                    if proxy:
                        mark_proxy_bad(str(proxy))
                        log_debug(f"АвтоПитер: 407 на прокси, меняем")
                    continue
                if attempt == max_attempts - 1:
                    return []
                time.sleep(0.5)
                continue
            
            if response.status_code == 200:
                # Проверяем, не заблокирована ли страница
                if _autopiter_page_blocked(response.text):
                    log_debug(f"Autopiter: обнаружена блокировка, включаем Selenium fallback для {artikul}")
                    brands = parse_autopiter_selenium_fallback(artikul, proxy)
                    if brands:
                        return brands
                    # Если Selenium тоже не помог, возвращаем пусто
                    log_debug("Autopiter: Selenium fallback не помог, пропускаем")
                    return []
                
                # Если блокировки нет, парсим как обычно
                brands = parse_autopiter_response(response.text, artikul)
                log_debug(f"АвтоПитер requests: найдено {len(brands)} брендов (attempt {attempt + 1})")
                _AUTOPITER_LIMITER.reward()
                return brands

            if response.status_code in (429, 403):
                # Жестко помечаем текущий IP как плохой и меняем его
                current_proxy_dict = session.proxies.get('http')
                if current_proxy_dict:
                    try:
                        mark_proxy_bad(current_proxy_dict.replace('http://', ''))
                        log_debug(f"АвтоПитер: прокси {_proxy_url_to_host_port(current_proxy_dict)} помечен как BAD из-за {response.status_code}")
                    except Exception:
                        pass
                
                # Мгновенно достаем новый IP из пула и обновляем сессию
                new_proxy_dict = get_next_proxy()
                if new_proxy_dict:
                    session.proxies.clear()
                    session.proxies.update(new_proxy_dict)
                    log_debug(f"АвтоПитер: СМЕНА ПРОКСИ на {_proxy_url_to_host_port(new_proxy_dict.get('http', ''))} для {artikul}")
                    # Небольшая пауза, чтобы не создавать мгновенный залп
                    time.sleep(3)
                    continue # Повторяем запрос немедленно
                
                # Если новых прокси нет — используем старую логику с ожиданием
                backoff = max(1.0, min(10.0, 2.0 * (2 ** attempt)))
                log_debug(f"АвтоПитер: HTTP {response.status_code}, нет нового прокси, backoff {backoff:.1f}s")
                _AUTOPITER_LIMITER.penalize(backoff)
                if attempt == max_attempts - 1:
                    return []
                time.sleep(backoff)
                continue

            log_debug(f"АвтоПитер: HTTP {response.status_code} для {artikul}")
            break

        return []
        
    except Exception as e:
        log_debug(f"Ошибка АвтоПитер для {artikul}: {str(e)}")
        return []
        
    except (AutopiterRateLimitException, AutopiterForbiddenException, AutopiterBlockedException):
        raise
    except AutopiterNetworkException:
        raise
    except Exception as e:
        log_debug(f"Ошибка АвтоПитер для {artikul}: {str(e)}")
        return []


def parse_autopiter_response(html_content: str, artikul: str) -> List[str]:
    """Парсит ответ Autopiter и извлекает бренды используя точный селектор"""
    brands = set()
    
    try:
        if _autopiter_page_blocked(html_content):
            log_debug(f"Autopiter: страница заблокирована (captcha/ошибка) для {artikul}")
            return []

        soup = BeautifulSoup(html_content, 'html.parser')
        from .brand_config import get_autopiter_blacklist
        brand_exclude_tokens = list(get_autopiter_blacklist())

        logged_pairs = set()

        def _source_group(source_text: str) -> str:
            if source_text.startswith("fallback-link"):
                return "fallback-link"
            return source_text

        def register_brand(value: Optional[str], source: str = '') -> None:
            brand = (value or '').strip()
            if not brand or len(brand) <= 1 or len(brand) >= 50:
                return
            brand_lower = brand.lower()

            if looks_like_analytics_garbage_token(brand):
                return
            
            if brand_lower.isdigit():
                return
            
            if brand_lower in brand_exclude_tokens:
                return
            if 'diesel' in brand_lower and ('part' in brand_lower or 'parts' in brand_lower):
                return
            if any(exclude in brand_lower for exclude in brand_exclude_tokens):
                return
            if any(brand_lower in exclude for exclude in brand_exclude_tokens if len(exclude) > len(brand_lower)):
                return
            
            if brand_lower.startswith('12643') or brand_lower.startswith('d-') or brand_lower.startswith('dz'):
                return
            
            if brand[0].isdigit():
                return
            
            digit_and_separator_count = sum(1 for c in brand if c.isdigit() or c in '-./')
            if digit_and_separator_count > len(brand) * 0.5:
                return
            
            if len(brand) <= 10 and re.match(r'^[A-Z]{2,3}[-]?\d+[A-Z]?$', brand, re.IGNORECASE):
                return
            
            if re.match(r'^[A-Z0-9]{2,}[-/][A-Z0-9]{2,}', brand, re.IGNORECASE):
                digit_count = sum(1 for c in brand if c.isdigit())
                if digit_count > len(brand) * 0.4:
                    return
            
            if any(char.isdigit() for char in brand[:3]):
                return
            
            if len(brand) < 2 or len(brand) > 50:
                return
            
            if re.match(r'^\d+[A-Z]+\d+', brand, re.IGNORECASE) or re.match(r'^[A-Z]+\d+[A-Z]+\d+', brand, re.IGNORECASE):
                return
            
            if re.match(r'^\d{6,}[A-Z]{1,3}$', brand, re.IGNORECASE):
                return
            
            if re.match(r'^[A-Z]{1,4}\d{4,}$', brand, re.IGNORECASE):
                return
            
            if brand.isupper() and not ' ' in brand and any(c.isdigit() for c in brand) and len(brand) > 5:
                digit_ratio = sum(1 for c in brand if c.isdigit()) / len(brand)
                if digit_ratio > 0.3:
                    return
                
            digit_count = sum(1 for c in brand if c.isdigit())
            if digit_count > len(brand) * 0.6:
                return
            
            if ' ' in brand:
                russian_chars = sum(1 for c in brand if 'а' <= c.lower() <= 'я' or c.lower() == 'ё')
                total_chars = sum(1 for c in brand if c.isalpha())
                if total_chars > 0 and russian_chars / total_chars > 0.7:
                    return
            
            if brand[0].isupper() and all('а' <= c.lower() <= 'я' or c.lower() == 'ё' or c == ' ' for c in brand):
                known_russian_brands = {'автокомпонент', 'автокомпонент плюс', 'автодеталь'}
                if brand_lower not in known_russian_brands:
                    return
            
            split_brands = _split_comma_separated_brands(brand)
            for split_brand in split_brands:
                split_brand = split_brand.lstrip('_').strip()
                if split_brand and len(split_brand) >= 2:
                    brands.add(split_brand)
                    if source:
                        key = (split_brand, _source_group(source))
                        if key not in logged_pairs:
                            logged_pairs.add(key)
                            log_debug(f"Autopiter: найден бренд '{split_brand}' ({source}) для {artikul} (из '{brand}')")
        
        main_content = soup.select_one('#main-content')
        if not main_content:
            log_debug(f"Autopiter: не найден #main-content для {artikul}")
            main_content = soup

        # ========== ОСНОВНОЙ ПУТЬ ==========
        table = main_content.select_one('div[class*="Table__table"]')
        rows = table.select('div[class*="IndividualTableRow"]') if table else []
        
        if table and rows:
            log_debug(f"Autopiter: найдено {len(rows)} строк IndividualTableRow для {artikul}")

            for row_idx, row in enumerate(rows):
                found_brand = None
                source_desc = None

                brand_link = row.select_one('span[class*="IndividualTableRow__brandLink"] a[href*="/brands/"]')
                if not brand_link:
                    info_column = row.select_one('div[class*="IndividualTableRow__infoColumn"]')
                    if info_column:
                        for _ in range(2):
                            brand_link = info_column.select_one('span a[href*="/brands/"]')
                            if brand_link:
                                break
                            time.sleep(0.4)

                if brand_link:
                    found_brand = brand_link.get_text(strip=True)
                    source_desc = f"строка {row_idx + 1} brandLink (или infoLink)"
                else:
                    info_column = row.select_one('div[class*="IndividualTableRow__infoColumn"]')
                    if info_column and not found_brand:
                        title_span = info_column.select_one('span[title]')
                        if title_span and title_span.get('title'):
                            found_brand = title_span.get('title')
                            source_desc = f"строка {row_idx + 1} info-title"
                        else:
                            direct_text = info_column.get_text(strip=True)
                            if direct_text:
                                first_part = direct_text.split('—')[0].strip()
                                if first_part and len(first_part) > 1:
                                    found_brand = first_part
                                    source_desc = f"строка {row_idx + 1} info-text"

                if not found_brand:
                    brand_elements = row.select('[class*="brand"]')
                    for el in brand_elements:
                        text = el.get_text(strip=True)
                        if text and len(text) > 1:
                            found_brand = text
                            source_desc = f"строка {row_idx + 1} brand-class"
                            break

                if found_brand:
                    register_brand(found_brand, source_desc or f"строка {row_idx + 1}")

        else:
            if not table:
                log_debug(f"Autopiter: не найдена таблица Table__table для {artikul}")
            else:
                log_debug(f"Autopiter: не найдены строки IndividualTableRow для {artikul}")

        if not brands:
            for a_tag in soup.select('a[href*="/brands/"]'):
                brand_text = a_tag.get_text(strip=True)
                if brand_text and len(brand_text) > 1:
                    register_brand(brand_text, "fallback-link")

            for el in soup.select('[data-brand]'):
                brand_text = el.get('data-brand', '').strip()
                if brand_text:
                    register_brand(brand_text, "fallback-data-brand")

        brand_chip_selectors = [
            "div[class*='Brands_root'] span[class*='ModalButton__button']",
            "div[class*='Brands_root'] span[title]",
            "div[class*='Brands_root'] a",
            "div[class*='Brands_root'] button",
        ]
        for selector in brand_chip_selectors:
            for element in soup.select(selector):
                text = element.get('title') or element.get_text(strip=True)
                if text:
                    register_brand(text, "блок производителей")
        
        log_debug(f"Autopiter: итого найдено {len(brands)} брендов для {artikul}")
        
    except Exception as e:
        log_debug(f"Ошибка при парсинге брендов Autopiter для {artikul}: {e}")
    
    return sorted(list(brands))


def _split_comma_separated_brands(brand_str: str) -> List[str]:
    """Разбивает бренды, разделенные запятыми, на отдельные бренды."""
    if not brand_str or not brand_str.strip():
        return []
    
    parts = [part.strip() for part in brand_str.split(',')]
    return [part for part in parts if part]


def split_combined_brands(brands: List[str]) -> List[str]:
    """Разделяет объединенные бренды на отдельные"""
    result = set()
    
    for brand in brands:
        brand_clean = brand.strip()
        if not brand_clean:
            continue
            
        separators = [', ', ',', ' / ', '/', ' & ', '&', ' + ', '+', ' | ', '|']
        
        has_separator = False
        if ' - ' in brand_clean:
            has_separator = True
            parts = brand_clean.split(' - ')
            for part in parts:
                part_clean = part.strip()
                if part_clean and len(part_clean) > 2:
                    result.add(part_clean)
        else:
            for sep in separators:
                if sep in brand_clean:
                    has_separator = True
                    parts = brand_clean.split(sep)
                    for part in parts:
                        part_clean = part.strip()
                        if part_clean and len(part_clean) > 2:
                            result.add(part_clean)
                    break
        
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

def get_brands_by_artikul_armtek(artikul: str, proxy: Optional[Union[str, Dict[str, str]]] = None, logger=None) -> List[str]:
	"""Получает бренды с Armtek по артикулу (Selenium + HTTP fallback)."""
	try:
		log_debug(f"Armtek: начало обработки артикула {artikul}")
		proxy_str = _normalize_proxy_arg(proxy)

		if not ARMTEK_SELENIUM_DISABLED:
			# 1) Selenium без прокси — одна попытка (+ повтор только если Chrome жив, но брендов нет)
			driver_failed = False
			for selenium_attempt in range(2):
				brands_sel = parse_armtek_selenium(artikul, None)
				if brands_sel is None:
					driver_failed = True
					_note_armtek_selenium_driver_failure()
					log_debug(f"Armtek: Chrome недоступен для {artikul}, очистка процессов")
					cleanup_chrome_processes()
					time.sleep(3 + selenium_attempt * 2)
					break
				if brands_sel:
					return filter_armtek_brands(split_combined_brands(brands_sel))
				if selenium_attempt == 0:
					log_debug(f"Armtek: повтор Selenium для {artikul} после пустого результата")
					cleanup_driver_pool()
					time.sleep(0.5)

			# 2) Selenium с прокси — только если Chrome жив
			if not driver_failed and not ARMTEK_SELENIUM_DISABLED:
				if not proxy_str:
					proxy_dict = get_next_proxy()
					proxy_str = _normalize_proxy_arg(proxy_dict)
					if proxy_str:
						log_debug(f"Armtek: автоматически получен прокси: {proxy_str}")
				if proxy_str:
					brands_sel = parse_armtek_selenium(artikul, proxy_str)
					if brands_sel is None:
						_note_armtek_selenium_driver_failure()
						cleanup_chrome_processes()
					elif brands_sel:
						return filter_armtek_brands(split_combined_brands(brands_sel))

		# 3) HTTP / API fallback — когда Selenium не поднял Chrome или страница пустая
		for fallback_name, fallback_fn in (
			("HTTP", lambda: parse_armtek_http(artikul, proxy_str)),
			("API", lambda: parse_armtek_api_fallback(artikul, [proxy_str] if proxy_str else None)),
		):
			try:
				fallback_brands = fallback_fn()
				if fallback_brands:
					filtered = filter_armtek_brands(split_combined_brands(fallback_brands))
					if filtered:
						log_debug(
							f"Armtek {fallback_name} fallback: найдено {len(filtered)} брендов для {artikul}"
						)
						return filtered
			except Exception as e:
				log_debug(f"Armtek {fallback_name} fallback ошибка для {artikul}: {e}")

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


def _armtek_wait_for_results(driver, timeout: float = 15.0) -> bool:
	"""Ждём появления списка результатов, заголовка секции или блока «ничего не найдено»."""
	def _ready(d):
		try:
			return d.execute_script(
				"""
				if (document.querySelector('div.not-found__title')) return true;
				const root = document.querySelector('.results-list__items');
				if (!root) return false;
				if (root.querySelector('div.results-list__divider p.font__headline6')) return true;
				if (root.querySelector('app-article-card-tile, project-ui-article-card')) return true;
				if (root.querySelector('span.font__caption1.brand--selectable, span.font__body2.brand--selecting')) {
					return true;
				}
				return false;
				"""
			)
		except Exception:
			return False

	try:
		WebDriverWait(driver, timeout).until(_ready)
		return True
	except Exception:
		return False


_ARMTEK_UI_GARBAGE = frozenset({
	'гараж', 'подбор', 'выбор', 'корзина', 'каталог', 'поиск', 'войти', 'главная',
	'искомый товар', 'возможные замены', 'нет в наличии', 'в корзину', 'бренды',
	'результаты', 'сортировать', 'фильтры', 'фильтр', 'armtek', 'armtek.ru',
})


def _get_armtek_ui_garbage() -> frozenset:
	from .brand_config import get_armtek_ui_garbage
	return get_armtek_ui_garbage()


def _armtek_brand_text_is_valid(text: str) -> bool:
	"""Проверка, что строка похожа на бренд, а не на UI/артикул."""
	brand = (text or '').strip()
	if not brand or len(brand) < 2 or len(brand) > 50:
		return False
	low = brand.lower()
	if low in _get_armtek_ui_garbage():
		return False
	if brand.isdigit():
		return False
	if re.fullmatch(r'[\d\s\-./]+', brand):
		return False
	digits = sum(1 for c in brand if c.isdigit())
	if digits >= 3 and digits / max(len(brand), 1) > 0.55:
		return False
	if brand[0].isdigit() and len(brand) > 4:
		return False
	return True


def _armtek_parse_results_sections(driver) -> Dict[str, object]:
	"""Состояние секций Armtek: только заголовки внутри .results-list__items."""
	default: Dict[str, object] = {
		"has_target": False,
		"has_replacements": False,
		"only_replacements": False,
		"driver_crashed": False,
		"brands": [],
	}
	try:
		raw = driver.execute_script(
			"""
			const brandSelector = arguments[0];
			const garbageList = arguments[1] || [];
			const root = document.querySelector('.results-list__items');
			if (!root) {
				return {hasTarget: false, hasReplacements: false, onlyReplacements: false, brands: []};
			}
			const garbage = new Set(garbageList.map(s => String(s).toLowerCase()));
			function isBrandText(text) {
				if (!text) return false;
				const t = text.trim();
				if (t.length < 2 || t.length > 50) return false;
				const low = t.toLowerCase();
				if (garbage.has(low)) return false;
				if (/^\\d+$/.test(t)) return false;
				if (/^[\\d\\s\\-./]+$/.test(t)) return false;
				const digits = (t.match(/\\d/g) || []).length;
				if (digits >= 3 && digits / t.length > 0.55) return false;
				if (/^\\d/.test(t) && t.length > 4) return false;
				return true;
			}
			function isBetween(el, start, end) {
				if (start && !(start.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) return false;
				if (end && !(end.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) return false;
				return true;
			}
			function collectBrands(container, start, end) {
				const brands = [];
				const cardSelectors = [
					'app-article-card-tile',
					'project-ui-article-card',
					'project-ui-article-card-with-suggestions',
				];
				for (const cardSel of cardSelectors) {
					for (const card of container.querySelectorAll(cardSel)) {
						if (start !== null || end !== null) {
							if (!isBetween(card, start, end)) continue;
						}
						for (const span of card.querySelectorAll(brandSelector)) {
							const text = (span.textContent || '').trim();
							if (isBrandText(text)) brands.push(text);
						}
					}
				}
				for (const span of container.querySelectorAll(
					'div.item.item-mobile span.brand--selecting, div.item.item-mobile span.brand--selectable'
				)) {
					if (start !== null || end !== null) {
						if (!isBetween(span, start, end)) continue;
					}
					const text = (span.textContent || '').trim();
					if (isBrandText(text)) brands.push(text);
				}
				return brands;
			}
			const headers = [...root.querySelectorAll('div.results-list__divider p.font__headline6')];
			let targetHeader = null;
			let replHeader = null;
			for (const h of headers) {
				const t = (h.textContent || '').trim().toLowerCase();
				if (t.includes('искомый товар')) targetHeader = h;
				if (t.includes('возможные замены')) replHeader = h;
			}
			const hasTarget = !!targetHeader;
			const hasReplacements = !!replHeader;
			if (!hasTarget) {
				const brands = collectBrands(root, null, null);
				return {
					hasTarget: false,
					hasReplacements,
					onlyReplacements: hasReplacements && brands.length === 0,
					brands: [...new Set(brands)],
				};
			}
			const brands = collectBrands(root, targetHeader, replHeader);
			return {
				hasTarget: true,
				hasReplacements,
				onlyReplacements: false,
				brands: [...new Set(brands)],
			};
			""",
			_ARMTEK_BRAND_SPAN_SELECTOR,
			list(_get_armtek_ui_garbage()),
		)
		if not isinstance(raw, dict):
			return default
		return {
			"has_target": bool(raw.get("hasTarget")),
			"has_replacements": bool(raw.get("hasReplacements")),
			"only_replacements": bool(raw.get("onlyReplacements")),
			"brands": list(raw.get("brands") or []),
		}
	except Exception as e:
		log_debug(f"Armtek Selenium: ошибка чтения секций результатов: {e}")
		if _is_selenium_fatal_error(e):
			return {**default, "driver_crashed": True}
		return default


def parse_armtek_selenium(artikul: str, proxy: Optional[Union[str, Dict[str, str]]] = None, logger=None) -> Optional[List[str]]:
    """Selenium-парсинг Armtek (всегда новый драйвер). None — не удалось запустить Chrome; [] — бренды не найдены."""
    global ARMTEK_SELENIUM_FAILURES, ARMTEK_SELENIUM_DISABLED
    
    brands: Set[str] = set()
    driver = None
    driver_broken = False
    proxy_str = _normalize_proxy_arg(proxy)
    temp_dir = None
    
    try:
        log_debug(f"Armtek Selenium: запуск для артикула {artikul}")

        effective_proxy = None if (proxy_str and '@' in proxy_str) else proxy_str

        # 2) Всегда создаём новый драйвер (не используем пул)
        temp_dir = tempfile.mkdtemp(prefix=f"chrome_armtek_{uuid.uuid4().hex[:8]}_")
        log_debug("Armtek Selenium: создаём новый драйвер")
        driver = _create_chrome_driver_robust(temp_dir, effective_proxy)
        if driver is None:
            log_debug("Armtek Selenium: не удалось создать драйвер")
            _note_armtek_selenium_driver_failure()
            return None

        url = f"https://armtek.ru/search?text={artikul}"
        log_debug(f"Armtek Selenium: загружаем URL {url}")

        # 3) Загрузка страницы с retry
        for page_attempt in range(DRIVER_TIMEOUT_RETRIES):
            try:
                driver.get(url)
                log_debug(f"Armtek Selenium: страница загружена, попытка {page_attempt + 1}")
                break
            except Exception as e:
                error_msg = str(e)
                log_debug(f"Попытка {page_attempt + 1} загрузки страницы: {error_msg}")
                lower_msg = error_msg.lower()
                if (
                    "tab crashed" in lower_msg
                    or "chrome not reachable" in lower_msg
                    or "connection refused" in lower_msg
                    or "timed out receiving message from renderer" in lower_msg
                    or "script timeout" in lower_msg
                    or "httpconnectionpool" in lower_msg
                    or "read timed out" in lower_msg
                ):
                    log_debug("Критическая ошибка Chrome, пересоздаём драйвер")
                    driver_broken = True
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    # Создаём новый драйвер
                    if temp_dir:
                        try:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                        except Exception:
                            pass
                    temp_dir = tempfile.mkdtemp(prefix=f"chrome_armtek_{uuid.uuid4().hex[:8]}_")
                    driver = _create_chrome_driver_robust(temp_dir, effective_proxy)
                    if driver is None:
                        log_debug("Не удалось пересоздать драйвер")
                        return None
                    log_debug("Создан новый драйвер после критической ошибки")
                    driver_broken = False
                    driver.get(url)
                    break
                if page_attempt < DRIVER_TIMEOUT_RETRIES - 1:
                    time.sleep(2)
                else:
                    log_debug("Не удалось загрузить страницу после всех попыток")
                    return []

        # 4) Ожидание загрузки результатов (код остаётся без изменений)
        wait = WebDriverWait(driver, SELENIUM_TIMEOUT)
        selectors_to_wait = [
            (By.CSS_SELECTOR, '.results'),
            (By.CSS_SELECTOR, '.search-results'),
            (By.CSS_SELECTOR, '.results-list__items'),
            (By.CSS_SELECTOR, 'span.font__body2.brand--selecting'),
            (By.CSS_SELECTOR, 'span.font_body2.brand--selecting'),
            (By.CSS_SELECTOR, '.brand--selecting'),
            (By.CSS_SELECTOR, '.font__caption1.brand--selectable'),
            (By.CSS_SELECTOR, '.product-card'),
            (By.CSS_SELECTOR, '.catalog-item'),
            (By.CSS_SELECTOR, 'project-ui-article-card'),
            (By.CSS_SELECTOR, '[class*="result"]'),
            (By.CSS_SELECTOR, '[class*="item"]'),
        ]
        page_loaded = False
        max_attempts = min(5, len(selectors_to_wait))
        for i, (by, sel) in enumerate(selectors_to_wait[:max_attempts]):
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
                html_content = driver.page_source
                debug_file = f"/tmp/armtek_debug_{artikul}.html"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                log_debug(f"Armtek Selenium: HTML сохранен в {debug_file}")
            except Exception as e:
                log_debug(f"Armtek Selenium: не удалось сохранить HTML: {str(e)}")
            try:
                WebDriverWait(driver, 2).until(lambda d: d.execute_script("return document.readyState") == "complete")
                log_debug("Armtek Selenium: страница загружена, но нет ожидаемых элементов")
            except Exception:
                log_debug("Armtek Selenium: страница не загрузилась полностью")
                return []

        # 5) Быстрая прокрутка
        try:
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight/2);')
            time.sleep(0.05)
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
            time.sleep(0.05)
        except Exception:
            pass

        # 6) Проверка "ничего не найдено"
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

        # 7) Секции «Искомый товар» / «Возможные замены»
        try:
            _armtek_wait_for_results(driver, max(12.0, float(SELENIUM_TIMEOUT) + 4.0))
        except Exception:
            pass

        section_state = _armtek_parse_results_sections(driver)
        if section_state.get("driver_crashed"):
            log_debug(f"Armtek Selenium: Chrome упал при чтении секций для {artikul}, пересоздаём драйвер")
            driver_broken = True
            try:
                driver.quit()
            except Exception:
                pass
                # Создаём новый
            if temp_dir:
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass
            temp_dir = tempfile.mkdtemp(prefix=f"chrome_armtek_{uuid.uuid4().hex[:8]}_")
            driver = _create_chrome_driver_robust(temp_dir, effective_proxy)
            if driver is None:
                return None
            driver_broken = False
            driver.get(url)
            _armtek_wait_for_results(driver, max(8.0, float(SELENIUM_TIMEOUT) + 4.0))
            section_state = _armtek_parse_results_sections(driver)

        if not section_state.get("brands") and section_state.get("has_target"):
            time.sleep(0.4)
            section_state = _armtek_parse_results_sections(driver)

        if section_state.get("only_replacements"):
            msg = f"Armtek Selenium: для {artikul} есть только 'Возможные замены' — пропускаем"
            log_debug(msg)
            if logger:
                try:
                    logger(msg)
                except Exception:
                    pass
            return []

        # 8) Сбор брендов из секции "Искомый товар"
        for brand_text in section_state.get("brands") or []:
            text = str(brand_text).strip()
            if _armtek_brand_text_is_valid(text):
                brands.add(text)

        filtered_early = filter_armtek_brands(list(brands))
        if filtered_early:
            log_debug(f"Armtek Selenium: в секции 'Искомый товар' найдено {len(filtered_early)} брендов")
            ARMTEK_SELENIUM_FAILURES = 0
            return filtered_early

        has_target_section = bool(section_state.get("has_target"))
        if has_target_section:
            log_debug(f"Armtek Selenium: секция 'Искомый товар' есть, но валидные бренды не найдены")
            return []

        # 9) Fallback: поиск по точным селекторам
        exact_selectors = [
            'app-article-card-tile span.font__caption1.brand--selectable',
            'app-article-card-tile span.font__body2.brand--selecting',
            'project-ui-article-card span.font__body2.brand--selecting',
            'project-ui-article-card-with-suggestions span.font__body2.brand--selecting',
            '.pin-brand-name span.font__caption1.brand--selectable',
        ]
        log_debug(f"Armtek Selenium: поиск брендов по {len(exact_selectors)} селекторам")
        for selector in exact_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                log_debug(f"Armtek Selenium: найдено {len(elements)} элементов по '{selector}'")
                for el in elements:
                    text = el.text.strip()
                    if text and _armtek_brand_text_is_valid(text):
                        brands.add(text)
                        log_debug(f"Armtek Selenium: найден бренд '{text}'")
                if len(brands) >= 3:
                    break
            except Exception as e:
                log_debug(f"Armtek Selenium: ошибка селектора {selector}: {str(e)}")
                if _is_selenium_fatal_error(e):
                    driver_broken = True
                    break

        # 10) Упрощённый поиск и HTML-эвристика (оставляем как было)
        if not brands and not driver_broken:
            log_debug("Armtek Selenium: точные селекторы не дали результатов, пробуем упрощённый поиск")
            simple_selectors = [
                'app-article-card-tile span.font__caption1.brand--selectable',
                'project-ui-article-card span.font__body2.brand--selecting',
            ]
            for selector in simple_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for el in elements:
                        text = el.text.strip()
                        if text and _armtek_brand_text_is_valid(text):
                            if text.isalpha() or (len(text) <= 15 and any(c.isalpha() for c in text)):
                                brands.add(text)
                    if brands:
                        break
                except Exception:
                    pass

        if not brands:
            log_debug("Armtek Selenium: пробуем XPath и HTML-эвристику")
            try:
                xpath_elems = driver.find_elements(
                    By.XPATH,
                    "//app-article-card-tile//span[contains(@class,'brand--selectable')]"
                    " | //project-ui-article-card//span[contains(@class,'brand--selecting')]"
                    " | //project-ui-article-card-with-suggestions//span[contains(@class,'brand--selecting')]",
                )
                for el in xpath_elems:
                    text = (el.text or '').strip()
                    if _armtek_brand_text_is_valid(text):
                        brands.add(text)
            except Exception:
                pass

            if not brands:
                try:
                    page_source = driver.page_source
                    html_brands = parse_armtek_page_text(page_source, artikul)
                    if html_brands:
                        brands.update(html_brands)
                        log_debug(f"Armtek Selenium: найдено {len(html_brands)} брендов из HTML")
                except Exception:
                    pass

        if brands:
            ARMTEK_SELENIUM_FAILURES = 0

        filtered_result = filter_armtek_brands(list(brands))
        if filtered_result:
            log_debug(f"Armtek Selenium: итого найдено {len(filtered_result)} брендов")
        else:
            log_debug(f"Armtek Selenium: бренды не найдены")
        return filtered_result

    except Exception as e:
        log_debug(f"Ошибка в parse_armtek_selenium для {artikul}: {str(e)}")
        if _is_selenium_fatal_error(e) or _is_chrome_resource_error(e):
            driver_broken = True
            _note_armtek_selenium_driver_failure()
        return None

    finally:
        # Просто закрываем драйвер, игнорируя все ошибки
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
            # Удаляем из учёта, если есть
            try:
                driver_id = id(driver)
                DRIVER_LAST_USED.pop(driver_id, None)
                DRIVER_USAGE_COUNT.pop(driver_id, None)
            except Exception:
                pass
        # Очищаем временную директорию
        if temp_dir:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

def _create_chrome_driver_robust(temp_dir: Optional[str] = None, proxy: Optional[str] = None) -> Optional[webdriver.Chrome]:
    """Создает Chrome драйвер с улучшенной обработкой ошибок и retry логикой"""
    
    try:
        subprocess.run(['pkill', '-9', '-f', 'chrome'], timeout=3, capture_output=True)
        subprocess.run(['pkill', '-9', '-f', 'chromedriver'], timeout=3, capture_output=True)
    except Exception:
        pass
    
    if not temp_dir:
        temp_dir = tempfile.mkdtemp(prefix=f"chrome_{uuid.uuid4().hex[:8]}_")
    
    with _ChromeCreateLock():
        for attempt in range(DRIVER_CREATION_RETRIES):
            try:
                chrome_options = Options()
                chrome_options.add_argument('--headless=new')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('--disable-blink-features=AutomationControlled')
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                # ===== НОВЫЕ АРГУМЕНТЫ ДЛЯ СТАБИЛЬНОСТИ =====
                chrome_options.add_argument('--disable-software-rasterizer')
                chrome_options.add_argument('--disable-features=VizDisplayCompositor')
                chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
                chrome_options.add_argument('--disable-background-timer-throttling')
                chrome_options.add_argument('--disable-backgrounding-occluded-windows')
                chrome_options.add_argument('--disable-renderer-backgrounding')
                chrome_options.add_argument('--disable-features=TranslateUI')
                chrome_options.add_argument('--disable-ipc-flooding-protection')
                chrome_options.add_argument('--disable-logging')
                chrome_options.add_argument('--disable-crash-reporter')
                chrome_options.add_argument('--disable-in-process-stack-traces')
                chrome_options.add_argument('--log-level=3')
                chrome_options.add_argument('--silent')
                chrome_options.add_argument('--disable-dev-tools')
                chrome_options.add_argument('--no-first-run')
                chrome_options.add_argument('--no-default-browser-check')
                
                # ===== ВАЖНО: ограничиваем память для Chrome =====
                chrome_options.add_argument('--memory-pressure-off')
                chrome_options.add_argument('--max_old_space_size=2048')
                
                # ===== ВАЖНО: ограничиваем количество процессов =====
                chrome_options.add_argument('--renderer-process-limit=2')
                
                # ===== ВАЖНО: отключаем ненужные фичи =====
                chrome_options.add_argument('--disable-extensions')
                chrome_options.add_argument('--disable-plugins')
                chrome_options.add_argument('--disable-images')
                chrome_options.add_argument('--disable-web-security')

                # ===== ДОПОЛНИТЕЛЬНЫЕ ФЛАГИ ДЛЯ СТАБИЛЬНОСТИ В DOCKER =====
                chrome_options.add_argument('--disable-setuid-sandbox')
                chrome_options.add_argument('--disable-background-networking')
                chrome_options.add_argument('--disable-default-apps')
                chrome_options.add_argument('--disable-sync')
                chrome_options.add_argument('--disable-translate')
                chrome_options.add_argument('--disable-ipv6')
                chrome_options.add_argument('--disable-session-crashed-bubble')
                chrome_options.add_argument('--disable-component-update')
                chrome_options.add_argument('--disable-domain-reliability')
                chrome_options.add_argument('--disable-client-side-phishing-detection')
                chrome_options.add_argument('--disable-prompt-on-repost')
                chrome_options.add_argument('--disable-hang-monitor')
                chrome_options.add_argument('--disable-popup-blocking')
                chrome_options.add_argument('--disable-webgl')
                chrome_options.add_argument('--disable-3d-apis')

                proxy_extension_loaded = _configure_chrome_proxy(chrome_options, proxy)
                if not proxy_extension_loaded:
                    chrome_options.add_argument('--disable-extensions')
                
                chrome_options.add_argument(f'--user-data-dir={temp_dir}')
                chrome_options.add_argument('--allow-running-insecure-content')

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
                    service = Service()

                chrome_options.page_load_strategy = 'eager'
                driver = webdriver.Chrome(service=service, options=chrome_options)
                _set_selenium_remote_command_timeout(driver, _selenium_remote_http_timeout_seconds())

                driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT + 10)
                driver.set_script_timeout(max(20, PAGE_LOAD_TIMEOUT))
                driver.implicitly_wait(1)

                return driver

            except Exception as e:
                log_debug(f"Попытка {attempt + 1} создания Chrome драйвера: {str(e)}")
                if _is_chrome_resource_error(e):
                    cleanup_chrome_processes()
                    time.sleep(3 + attempt * 2)
                    break
                if attempt < DRIVER_CREATION_RETRIES - 1:
                    time.sleep(2 ** attempt)
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
        
        proxy_extension_loaded = _configure_chrome_proxy(chrome_options, proxy)
        if not proxy_extension_loaded:
            chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        _set_selenium_remote_command_timeout(driver, _selenium_remote_http_timeout_seconds())
        
        # Устанавливаем таймауты
        driver.set_page_load_timeout(15)
        driver.implicitly_wait(5)
        
        return driver
        
    except Exception as e:
        log_debug(f"Ошибка создания минимального Chrome драйвера: {str(e)}")
        return None

def parse_armtek_page_text(page_text: str, artikul: str) -> set:
    """Парсит бренды из текста страницы Armtek с улучшенной фильтрацией"""
    from .brand_config import get_armtek_ui_garbage, get_armtek_extra_garbage
    brands = set()
    garbage_words = get_armtek_ui_garbage() | get_armtek_extra_garbage()
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
        # Список результатов (list view) — L-5800 и подобные
        'span.font__body2.brand--selecting',
        'span.font_body2.brand--selecting',
        'div.item.item-mobile span.brand--selecting',
        'project-ui-article-card-with-suggestions span.brand--selecting',
        'project-ui-article-card span.brand--selecting',
        # Плиточный вид / pin-brand
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
                r'class=\"font__body2\s+brand--selecting\"[^>]*>([^<]+)</span>',
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
	from .brand_config import get_armtek_extra_garbage, get_armtek_whitelist
	filtered: List[str] = []
	extra_garbage = get_armtek_extra_garbage()
	whitelist = get_armtek_whitelist()

	for b in brands:
		brand = b.strip()
		if not brand or not _armtek_brand_text_is_valid(brand):
			continue
		brand_lower = brand.lower()
		if whitelist and brand_lower in whitelist:
			filtered.append(brand)
			continue
		if brand_lower in extra_garbage:
			continue

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


def _emex_apply_xsrf(session) -> None:
	"""XSRF-TOKEN в cookie URL-encoded; в заголовок нужно декодированное значение."""
	xsrf_token = (
		session.cookies.get("XSRF-TOKEN")
		or session.cookies.get("xsrf-token")
		or session.cookies.get("X_XSRF_TOKEN")
		or session.cookies.get("csrf-token")
	)
	if xsrf_token:
		session.headers["X-XSRF-TOKEN"] = unquote(xsrf_token)


def _emex_warmup_session(session, artikul: str, proxies=None) -> None:
	"""Прогрев: главная + страница поиска (cookies для API)."""
	encoded_artikul = quote(artikul)
	search_url = f"https://emex.ru/search?detailNum={encoded_artikul}"
	try:
		session.get("https://emex.ru/", timeout=6, proxies=proxies)
	except Exception as e:
		log_debug(f"Emex: ошибка прогрева главной: {e}")
	try:
		session.get(search_url, timeout=8, proxies=proxies)
	except Exception as e:
		log_debug(f"Emex: ошибка прогрева search: {e}")
	for name, val in (("regionId", "263"), ("locationId", "263")):
		if not session.cookies.get(name):
			try:
				session.cookies.set(name, val, domain="emex.ru")
			except Exception:
				pass
	_emex_apply_xsrf(session)


def _emex_extract_brands_from_json(data: object) -> List[str]:
	brands: Set[str] = set()
	if not isinstance(data, dict):
		return []
	search_result = data.get("searchResult", {})
	if not isinstance(search_result, dict):
		return []
	makes = search_result.get("makes", {})
	if isinstance(makes, dict):
		for item in makes.get("list", []) or []:
			if isinstance(item, dict):
				brand = item.get("make")
				if brand and str(brand).strip():
					for split_brand in _split_comma_separated_brands(str(brand).strip()):
						brands.add(split_brand)
	sr_make = search_result.get("make")
	if isinstance(sr_make, str) and sr_make.strip():
		for split_brand in _split_comma_separated_brands(sr_make.strip()):
			brands.add(split_brand)
	return sorted(brands)


def get_brands_by_artikul_emex(artikul: str, proxy: Optional[str] = None) -> List[str]:
    """Получает бренды с Emex по артикулу.
    
    Selenium для Emex НЕ убираем, но:
    - ограничиваем число неудачных API‑попыток;
    - отключаем Selenium fallback после нескольких критических ошибок,
      чтобы один артикул не зависал на минуты и не создавал тысячи процессов Chrome.
    """
    global EMEX_SELENIUM_FAILURES, EMEX_SELENIUM_DISABLED
    try:
        if not _emex_use_proxy_enabled():
            proxy = None

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

        # Сессия с пулом соединений (переиспользование TCP на потоке)
        session = _get_thread_requests_session()
        session.proxies.clear()
        try:
            session.cookies.clear()
        except Exception:
            pass
        session.headers.update(headers)
        
        # Настройка прокси - принудительно используем прокси для Emex
        proxies = None
        if proxy:
            try:
                if isinstance(proxy, dict):
                    proxies = proxy
                    session.proxies.update(proxies)
                    log_debug(f"Emex: использование прокси {_proxy_url_to_host_port(proxies.get('http', ''))}")
                elif isinstance(proxy, str):
                    proxy_value = proxy.strip()
                    if proxy_value.startswith('http://'):
                        proxy_value = proxy_value[7:]
                    elif proxy_value.startswith('https://'):
                        proxy_value = proxy_value[8:]
                    proxies = parse_proxy_line(proxy_value)
                    if not proxies:
                        proxies = {
                            'http': f'http://{proxy_value}',
                            'https': f'http://{proxy_value}',
                        }
                    session.proxies.update(proxies)
                    log_debug(f"Emex: использование прокси {_proxy_url_to_host_port(proxies.get('http', ''))}")
            except Exception as e:
                log_debug(f"Emex: ошибка настройки прокси {proxy}: {str(e)}")
        elif _emex_use_proxy_enabled():
            try:
                proxy_dict = get_next_proxy()
                if proxy_dict:
                    session.proxies.update(proxy_dict)
                    proxies = proxy_dict
                    log_debug(f"Emex: автоматически получен прокси")
                else:
                    log_debug(f"Emex: прокси недоступен, пробуем без прокси")
            except Exception as e:
                log_debug(f"Emex: ошибка получения прокси: {str(e)}")
        else:
            log_debug("Emex: прямое соединение без прокси (EMEX_USE_PROXY=0)")
        
        # Устанавливаем куки и прогреваем сессию
        _emex_warmup_session(session, artikul, proxies)
        direct_fallback_used = False

        # Основные попытки с разными параметрами (сокращенный список)
        api_variants = [
            {"showAll": "false", "isHeaderSearch": "true"},
            {"showAll": "true", "isHeaderSearch": "true"},
        ]
        
        # Счетчик попыток и общий лимит времени на один артикул,
        # чтобы избежать многоминутных зависаний при недоступном Emex.
        total_attempts = 0
        max_total_attempts = 3
        api_start_ts = time.time()
        max_api_time_seconds = 25
        
        for num in candidate_nums:
            num_enc = quote(num)
            
            for params in api_variants:
                if total_attempts >= max_total_attempts:
                    log_debug(f"Emex API: достигнут лимит попыток для {artikul}, пропускаем")
                    break
                if time.time() - api_start_ts > max_api_time_seconds:
                    log_debug(f"Emex API: превышен общий лимит времени для {artikul}, прекращаем попытки")
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
                                        brands_list = _emex_extract_brands_from_json(data)
                                        if brands_list:
                                            global EMEX_SELENIUM_FAILURES
                                            EMEX_SELENIUM_FAILURES = 0
                                            log_debug(f"Emex API: найдено {len(brands_list)} брендов для {artikul}")
                                            return brands_list
                                    except json.JSONDecodeError as e:
                                        log_debug(f"Emex API: ошибка JSON для {artikul}: {str(e)}")
                                        continue
                            
                            elif response.status_code == 429:  # Rate limit
                                log_debug(f"Emex API: Rate limit для {artikul}, пропускаем")
                                break  # Выходим из цикла при rate limit
                            elif response.status_code == 403:  # Forbidden
                                log_debug(f"Emex API: 403 Forbidden для {artikul}")
                                if proxies is not None and not direct_fallback_used:
                                    log_debug("Emex API: 403 через прокси, пробуем прямое соединение без прокси")
                                    session.proxies.clear()
                                    proxies = None
                                    direct_fallback_used = True
                                    total_attempts = max(0, total_attempts - 1)
                                    _emex_warmup_session(session, artikul, None)
                                    continue
                                break
                            
                        except requests.exceptions.Timeout as e:
                            total_attempts += 1
                            log_debug(f"Emex API: таймаут для {artikul} (попытка {total_attempts}): {str(e)}")
                            # Если таймаут с прокси — считаем прокси проблемным и пробуем без прокси
                            if proxies is not None:
                                try:
                                    current_http = session.proxies.get('http') or ''
                                    if current_http:
                                        mark_proxy_bad(current_http.replace('http://', ''))
                                        log_debug(f"Emex API: помечаем прокси как проблемный из-за таймаута: {current_http}")
                                except Exception:
                                    pass
                                # очищаем прокси и пробуем прямое соединение
                                session.proxies.clear()
                                proxies = None
                                log_debug("Emex API: переключаемся на прямое соединение без прокси после таймаута")
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
                            total_attempts += 1
                            log_debug(f"Emex API: ошибка запроса для {artikul}: {str(e)} (попытка {total_attempts})")
                            # Если ошибка похожа на проблему прокси — помечаем и пробуем без прокси
                            from requests.exceptions import ProxyError as _ProxyError
                            is_proxy_error = isinstance(e, _ProxyError) or '502 Bad Gateway' in str(e) or 'Failed to establish a new connection' in str(e)
                            if proxies is not None and is_proxy_error:
                                try:
                                    current_http = session.proxies.get('http') or ''
                                    if current_http:
                                        mark_proxy_bad(current_http.replace('http://', ''))
                                        log_debug(f"Emex API: помечаем прокси как проблемный из-за ошибки запроса: {current_http}")
                                except Exception:
                                    pass
                                session.proxies.clear()
                                proxies = None
                                log_debug("Emex API: переключаемся на прямое соединение без прокси после ошибки прокси")
                            # Если прокси явно не используются и Emex недоступен напрямую — пробуем получить новый прокси
                            elif proxies is None and not proxy:
                                try:
                                    new_proxy_dict = get_next_proxy()
                                    if new_proxy_dict:
                                        session.proxies.update(new_proxy_dict)
                                        proxies = new_proxy_dict
                                        log_debug(f"Emex API: пробуем новый прокси после ошибки: {new_proxy_dict}")
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
        # Если Selenium уже несколько раз «падал», больше не пытаемся его запускать
        if EMEX_SELENIUM_DISABLED:
            log_debug("Emex Selenium fallback: отключён из-за предыдущих ошибок, пропускаем")
            return []

        try:
            from selenium.webdriver.common.by import By as _By
            brands = set()
            opts = Options()
            opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--blink-settings=imagesEnabled=false')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            tmp_dir = tempfile.mkdtemp(prefix=f"chrome_emex_{uuid.uuid4().hex[:8]}_")
            opts.add_argument(f'--user-data-dir={tmp_dir}')
            drv = webdriver.Chrome(options=opts)
            _set_selenium_remote_command_timeout(drv, _selenium_remote_http_timeout_seconds())
            drv.set_page_load_timeout(20)
            try:
                search_url = f"https://emex.ru/search?detailNum={quote(artikul)}"
                drv.get(search_url)
                WebDriverWait(drv, 12).until(lambda d: d.execute_script('return document.readyState') == 'complete')
                time.sleep(1.5)
                api_url = (
                    f"https://emex.ru/api/search/search?detailNum={quote(artikul)}"
                    "&locationId=263&showAll=false&isHeaderSearch=true"
                )
                try:
                    raw = drv.execute_async_script(
                        """
                        const url = arguments[0];
                        const cb = arguments[arguments.length - 1];
                        fetch(url, {
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'X-Requested-With': 'XMLHttpRequest',
                            },
                        })
                            .then(r => r.json())
                            .then(d => cb(d))
                            .catch(() => cb(null));
                        """,
                        api_url,
                    )
                    for brand in _emex_extract_brands_from_json(raw):
                        brands.add(brand)
                except Exception as e:
                    log_debug(f"Emex Selenium fetch API: {e}")
                if not brands:
                    possible_selectors = [
                        'div.makes-list span',
                        '[data-qa="makes-filter"] span',
                        'div[data-qa="brand-name"]',
                        '[class*="MakeFilter"] span',
                        '[class*="make"] span',
                    ]
                    for sel in possible_selectors:
                        try:
                            elems = drv.find_elements(_By.CSS_SELECTOR, sel)
                            for el in elems:
                                txt = el.text.strip()
                                if txt and len(txt) > 1 and not txt.isdigit():
                                    for split_brand in _split_comma_separated_brands(txt):
                                        brands.add(split_brand)
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
                EMEX_SELENIUM_FAILURES = 0
                log_debug(f"Emex Selenium fallback: найдено {len(brands)} брендов для {artikul}")
                return sorted(list(brands))
        except Exception as _e:
            EMEX_SELENIUM_FAILURES += 1
            log_debug(f"Emex Selenium fallback ошибка: {str(_e)} (ошибок подряд: {EMEX_SELENIUM_FAILURES})")
            if EMEX_SELENIUM_FAILURES >= MAX_EMEX_SELENIUM_FAILURES:
                EMEX_SELENIUM_DISABLED = True
                log_debug("Emex Selenium fallback: достигнут лимит ошибок, дальнейшие попытки будут пропускаться")
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
        _set_selenium_remote_command_timeout(driver, _selenium_remote_http_timeout_seconds())
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