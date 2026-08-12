"""Управление списками брендов и чёрными списками через файлы конфигурации."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Dict, List, Set

from django.conf import settings

from .brand_defaults import DEFAULT_LISTS

_lock = threading.Lock()
_cache: Dict[str, Set[str]] = {}
_mtimes: Dict[str, float] = {}

LIST_META: Dict[str, dict] = {
    'armtek_ui_garbage': {
        'title': 'Armtek — UI-мусор',
        'description': 'Элементы интерфейса Armtek, которые не являются брендами.',
        'group': 'armtek',
    },
    'armtek_extra_garbage': {
        'title': 'Armtek — дополнительный мусор',
        'description': 'Дополнительные слова для фильтрации ложных брендов Armtek.',
        'group': 'armtek',
    },
    'armtek_whitelist': {
        'title': 'Armtek — известные бренды',
        'description': 'Список распознаваемых брендов Armtek. Бренды из списка всегда проходят фильтрацию.',
        'group': 'armtek',
    },
    'autopiter_blacklist': {
        'title': 'Autopiter — чёрный список',
        'description': 'Слова и фразы, исключаемые из результатов парсинга Autopiter.',
        'group': 'blacklist',
    },
    'emex_blacklist': {
        'title': 'Emex — чёрный список',
        'description': 'Слова и фразы, исключаемые из результатов парсинга Emex.',
        'group': 'blacklist',
    },
}


def get_config_dir() -> Path:
    """Каталог списков брендов. По умолчанию media/config/lists (writable в Docker)."""
    override = os.getenv('BRAND_LISTS_DIR', '').strip()
    if override:
        return Path(override)
    return Path(settings.BASE_DIR) / 'media' / 'config' / 'lists'


def get_list_path(list_id: str) -> Path:
    if list_id not in LIST_META:
        raise KeyError(f'Unknown list: {list_id}')
    return get_config_dir() / f'{list_id}.txt'


def parse_file_content(content: str) -> List[str]:
    """Разбирает текст файла: одна запись на строку, # — комментарий."""
    items: List[str] = []
    seen: Set[str] = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key = line.lower()
        if key not in seen:
            seen.add(key)
            items.append(line)
    return items


def _legacy_config_dir() -> Path:
    return Path(settings.BASE_DIR) / 'config' / 'lists'


def _migrate_legacy_lists(config_dir: Path) -> None:
    """Копирует списки из старого config/lists, если новые ещё не созданы."""
    legacy_dir = _legacy_config_dir()
    if not legacy_dir.is_dir():
        return
    for list_id in LIST_META:
        dst = config_dir / f'{list_id}.txt'
        src = legacy_dir / f'{list_id}.txt'
        if not dst.exists() and src.is_file():
            try:
                dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
            except OSError:
                pass


def ensure_defaults() -> None:
    """Создаёт файлы конфигурации с значениями по умолчанию, если их ещё нет."""
    config_dir = get_config_dir()
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Нет прав на запись — load_list() использует DEFAULT_LISTS из памяти.
        return
    _migrate_legacy_lists(config_dir)
    for list_id, defaults in DEFAULT_LISTS.items():
        path = get_list_path(list_id)
        if not path.exists():
            try:
                _write_list_file(path, defaults)
            except OSError:
                pass


def _write_list_file(path: Path, items: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ['# Одна запись на строку. Строки, начинающиеся с #, игнорируются.', '']
    lines.extend(items)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def invalidate_cache(list_id: str | None = None) -> None:
    with _lock:
        if list_id:
            _cache.pop(list_id, None)
            _mtimes.pop(list_id, None)
        else:
            _cache.clear()
            _mtimes.clear()


def _default_list_set(list_id: str) -> Set[str]:
    return {item.lower() for item in DEFAULT_LISTS.get(list_id, [])}


def load_list(list_id: str) -> Set[str]:
    """Загружает список из файла с кэшированием по mtime."""
    ensure_defaults()
    path = get_list_path(list_id)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return _default_list_set(list_id)

    with _lock:
        if list_id in _cache and _mtimes.get(list_id) == mtime:
            return _cache[list_id]

    try:
        content = path.read_text(encoding='utf-8')
    except OSError:
        return _default_list_set(list_id)
    items = {item.lower() for item in parse_file_content(content)}

    with _lock:
        _cache[list_id] = items
        _mtimes[list_id] = mtime
    return items


def load_list_items(list_id: str) -> List[str]:
    """Загружает список, сохраняя регистр записей."""
    ensure_defaults()
    path = get_list_path(list_id)
    if not path.exists():
        return list(DEFAULT_LISTS.get(list_id, []))
    try:
        return parse_file_content(path.read_text(encoding='utf-8'))
    except OSError:
        return list(DEFAULT_LISTS.get(list_id, []))


def save_list(list_id: str, items: List[str]) -> int:
    """Сохраняет список в файл. Возвращает количество записей."""
    if list_id not in LIST_META:
        raise KeyError(f'Unknown list: {list_id}')
    cleaned = parse_file_content('\n'.join(items))
    _write_list_file(get_list_path(list_id), cleaned)
    invalidate_cache(list_id)
    return len(cleaned)


def get_armtek_ui_garbage() -> frozenset:
    return frozenset(load_list('armtek_ui_garbage'))


def get_armtek_extra_garbage() -> frozenset:
    return frozenset(load_list('armtek_extra_garbage'))


def get_armtek_whitelist() -> frozenset:
    return frozenset(item.lower() for item in load_list('armtek_whitelist'))


def get_autopiter_blacklist() -> frozenset:
    return frozenset(load_list('autopiter_blacklist'))


def get_emex_blacklist() -> frozenset:
    return frozenset(load_list('emex_blacklist'))


def get_blacklist_for_source(source: str) -> frozenset:
    if source == 'autopiter':
        return get_autopiter_blacklist()
    if source == 'emex':
        return get_emex_blacklist()
    return frozenset()


def list_all_metadata() -> List[dict]:
    ensure_defaults()
    result = []
    for list_id, meta in LIST_META.items():
        path = get_list_path(list_id)
        count = len(load_list_items(list_id))
        result.append({
            'id': list_id,
            'title': meta['title'],
            'description': meta['description'],
            'group': meta['group'],
            'count': count,
            'file': str(path.relative_to(settings.BASE_DIR)).replace('\\', '/'),
        })
    return result
