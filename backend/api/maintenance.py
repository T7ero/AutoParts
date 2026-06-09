"""Обслуживание media/results: очистка старых файлов и ротация логов."""
import logging
import os
import time
from typing import Tuple

from django.conf import settings

logger = logging.getLogger(__name__)

RESULTS_RETENTION_DAYS = int(os.getenv('RESULTS_RETENTION_DAYS', '7'))
LOG_MAX_BYTES = int(os.getenv('TASK_LOG_MAX_BYTES', str(10 * 1024 * 1024)))  # 10 MB


def cleanup_old_results(retention_days: int | None = None) -> Tuple[int, int]:
    """
    Удаляет файлы в media/results/ старше retention_days.
    Returns: (deleted_count, skipped_count)
    """
    days = retention_days if retention_days is not None else RESULTS_RETENTION_DAYS
    results_dir = os.path.join(settings.MEDIA_ROOT, 'results')
    if not os.path.isdir(results_dir):
        return 0, 0

    cutoff = time.time() - days * 86400
    deleted = 0
    skipped = 0

    for name in os.listdir(results_dir):
        path = os.path.join(results_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                deleted += 1
            else:
                skipped += 1
        except OSError as exc:
            logger.warning('Не удалось удалить %s: %s', path, exc)

    if deleted:
        logger.info('Очистка media/results: удалено %s файлов (старше %s дн.)', deleted, days)
    return deleted, skipped


def rotate_oversized_task_logs(max_bytes: int | None = None) -> int:
    """Обрезает parsing_task_*.log, если размер превышает лимит."""
    limit = max_bytes if max_bytes is not None else LOG_MAX_BYTES
    results_dir = os.path.join(settings.MEDIA_ROOT, 'results')
    if not os.path.isdir(results_dir):
        return 0

    rotated = 0
    for name in os.listdir(results_dir):
        if not name.startswith('parsing_task_') or not name.endswith('.log'):
            continue
        path = os.path.join(results_dir, name)
        try:
            size = os.path.getsize(path)
            if size <= limit:
                continue
            with open(path, 'rb') as fh:
                fh.seek(-limit // 2, os.SEEK_END)
                tail = fh.read()
            with open(path, 'wb') as fh:
                fh.write(b'...[log truncated]...\n')
                fh.write(tail)
            rotated += 1
        except OSError as exc:
            logger.warning('Не удалось ротировать лог %s: %s', path, exc)

    if rotated:
        logger.info('Ротация логов: обрезано %s файлов', rotated)
    return rotated


def run_media_maintenance() -> dict:
    deleted, kept = cleanup_old_results()
    rotated = rotate_oversized_task_logs()
    return {'deleted': deleted, 'kept': kept, 'logs_rotated': rotated}
