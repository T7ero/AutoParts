#!/usr/bin/env python3
"""
Скрипт для мониторинга ресурсов и автоматического перезапуска Celery при необходимости
"""
import psutil
import subprocess
import time
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('resource_monitor.log'),
        logging.StreamHandler()
    ]
)

def get_celery_memory_usage():
    """Получает использование памяти процессами Celery"""
    total_memory = 0
    celery_processes = []
    
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            if 'celery' in proc.info['name'].lower():
                memory_mb = proc.info['memory_info'].rss / 1024 / 1024
                total_memory += memory_mb
                celery_processes.append({
                    'pid': proc.info['pid'],
                    'memory_mb': memory_mb
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    return total_memory, celery_processes

def get_system_memory():
    """Получает общую информацию о памяти системы"""
    memory = psutil.virtual_memory()
    return {
        'total_gb': memory.total / 1024 / 1024 / 1024,
        'available_gb': memory.available / 1024 / 1024 / 1024,
        'used_gb': memory.used / 1024 / 1024 / 1024,
        'percent': memory.percent
    }

def restart_celery():
    """Перезапускает Celery контейнер"""
    try:
        logging.info("Перезапуск Celery контейнера...")
        subprocess.run([
            'docker', 'compose', 'restart', 'celery'
        ], check=True, capture_output=True, text=True)
        logging.info("Celery контейнер перезапущен успешно")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Ошибка при перезапуске Celery: {e}")
        return False

def monitor_resources():
    """Основная функция мониторинга"""
    while True:
        try:
            # Получаем информацию о памяти
            system_memory = get_system_memory()
            celery_memory, celery_processes = get_celery_memory_usage()
            
            logging.info(f"Системная память: {system_memory['used_gb']:.2f}GB / {system_memory['total_gb']:.2f}GB ({system_memory['percent']:.1f}%)")
            logging.info(f"Celery память: {celery_memory:.2f}MB")
            
            # Проверяем условия для перезапуска
            should_restart = False
            
            # Если Celery использует больше 800MB
            if celery_memory > 800:
                logging.warning(f"Celery использует слишком много памяти: {celery_memory:.2f}MB")
                should_restart = True
            
            # Если системная память используется больше 90%
            if system_memory['percent'] > 90:
                logging.warning(f"Системная память критически заполнена: {system_memory['percent']:.1f}%")
                should_restart = True
            
            # Если доступно меньше 200MB
            if system_memory['available_gb'] < 0.2:
                logging.warning(f"Мало доступной памяти: {system_memory['available_gb']:.2f}GB")
                should_restart = True
            
            if should_restart:
                logging.warning("Условия для перезапуска выполнены. Перезапускаем Celery...")
                if restart_celery():
                    logging.info("Ожидание 30 секунд после перезапуска...")
                    time.sleep(30)
                else:
                    logging.error("Не удалось перезапустить Celery")
            
            # Ждем 60 секунд перед следующей проверкой
            time.sleep(60)
            
        except Exception as e:
            logging.error(f"Ошибка в мониторинге: {e}")
            time.sleep(60)

if __name__ == "__main__":
    logging.info("Запуск мониторинга ресурсов...")
    monitor_resources() 