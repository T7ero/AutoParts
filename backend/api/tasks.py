import pandas as pd
from celery import shared_task
from django.core.files import File
from core.models import ParsingTask
from .autopiter_parser import (
    get_brands_by_artikul, 
    get_brands_by_artikul_armtek, 
    get_brands_by_artikul_emex, 
    cleanup_chrome_processes,
    get_next_proxy,
    load_proxies_from_file
)
import re
import concurrent.futures
import time
import gc
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from typing import List, Dict, Optional

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

@shared_task(bind=True, time_limit=10800, soft_time_limit=9000)  # 3 часа максимум, 2.5 часа мягкий лимит
def process_parsing_task(self, task_id):
    task = ParsingTask.objects.get(id=task_id)
    log_messages = []
    task.status = 'in_progress'
    task.progress = 0
    task.save()
    channel_layer = get_channel_layer()
    
    def ws_send():
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
    
    try:
        # Загружаем прокси при старте задачи
        load_proxies_from_file()
        
        df = pd.read_excel(task.file.path)
        # Очищаем DataFrame от пустых строк
        df.dropna(how='all', inplace=True)
        
        # Инициализируем таймаут
        task._timeout_check = time.time()
        
        total_rows = len(df)
        results_autopiter = []
        results_armtek = []
        results_emex = []
        
        def log(msg):
            log_messages.append(msg)
            print(msg)
        
        # Оптимизированная функция для параллельного парсинга с таймаутами и прокси
        def parse_all_parallel(numbers, brand, part_number, name):
            results = {'autopiter': [], 'emex': []}
            
            def parse_one(site, parser_func, max_retries=2):  # Уменьшаем количество попыток
                def inner(num, proxy=None):
                    for attempt in range(max_retries):
                        try:
                            if attempt == 0:
                                proxy = None
                                log(f"{site.capitalize()}: попытка {attempt+1} без прокси для {num}")
                            else:
                                proxy = get_next_proxy()
                                log(f"{site.capitalize()}: попытка {attempt+1} с прокси для {num}")
                            
                            time.sleep(0.2)  # Уменьшаем задержку
                            brands = parser_func(num, proxy)
                            log(f"{site}: {num} → {brands}")
                            return [(brand, part_number, name, b, num, site) for b in brands]
                        except Exception as e:
                            log(f"Error parsing {site} for {num} (attempt {attempt + 1}): {str(e)}")
                            if attempt < max_retries - 1:
                                time.sleep(1)  # Уменьшаем время ожидания
                            else:
                                log(f"Failed to parse {site} for {num} after {max_retries} attempts")
                                return []
                return inner
            
            # Увеличиваем количество потоков для лучшей производительности
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:  # Увеличиваем количество потоков
                # Autopiter
                fut_autopiter = {executor.submit(parse_one('autopiter', get_brands_by_artikul), num): num for num in numbers}
                
                # Обрабатываем результаты с таймаутом
                for fut in concurrent.futures.as_completed(fut_autopiter, timeout=60):  # Уменьшаем таймаут
                    try:
                        for res in fut.result():
                            results['autopiter'].append(res)
                    except Exception as e:
                        log(f"Ошибка обработки Autopiter: {str(e)}")
                
                # Emex
                fut_emex = {executor.submit(parse_one('emex', get_brands_by_artikul_emex), num): num for num in numbers}
                
                for fut in concurrent.futures.as_completed(fut_emex, timeout=60):  # Уменьшаем таймаут
                    try:
                        for res in fut.result():
                            results['emex'].append(res)
                    except Exception as e:
                        log(f"Ошибка обработки Emex: {str(e)}")
            
            return results
        
        # Основной цикл с оптимизацией памяти
        for index, row in df.iterrows():
            try:
                # Проверка таймаута каждые 20 строк
                if index % 20 == 0:
                    if time.time() - task._timeout_check > 2700:  # 45 минут
                        log("Task timeout approaching, finishing up...")
                        break
                
                # Правильное чтение данных из Excel согласно требованиям
                # A1: "Бренд № 1" - данные из колонки E входного файла (индекс 4)
                brand_from_e = str(row.iloc[4]).strip() if len(row) > 4 else ''
                # B1: "Артикул по Бренду № 1" - данные из колонки F входного файла (индекс 5)
                part_number_from_f = str(row.iloc[5]).strip() if len(row) > 5 else ''
                # C1: "Наименование" - данные из колонки B входного файла (индекс 1)
                name_from_b = str(row.iloc[1]).strip() if len(row) > 1 else ''
                # E1: "Артикул по Бренду № 2" - данные из колонки G входного файла (индекс 6)
                cross_number_from_g = str(row.iloc[6]).strip() if len(row) > 6 else ''
                # Основной артикул для парсинга - из колонки F (индекс 5)
                part_number = part_number_from_f
                
                if not part_number:
                    continue
                
                numbers = [part_number]
                if cross_number_from_g:
                    numbers.extend([n.strip() for n in cross_number_from_g.split(';') if n.strip()])
                
                used_pairs = set()
                
                # Параллельно Autopiter, Emex
                parallel_results = parse_all_parallel(numbers, brand_from_e, part_number_from_f, name_from_b)
                
                # Обрабатываем результаты Autopiter
                for (b1, pn1, n1, b2, pn2, src) in parallel_results['autopiter']:
                    key = (b1, pn1, n1, b2, pn2, src)
                    if key not in used_pairs:
                        d = {
                            'Бренд № 1': clean_excel_string(brand_from_e),  # Из колонки E входного файла
                            'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),  # Из колонки F входного файла
                            'Наименование': clean_excel_string(name_from_b),  # Из колонки B входного файла
                            'Бренд № 2': clean_excel_string(b2),  # Результат парсинга
                            'Артикул по Бренду № 2': clean_excel_string(cross_number_from_g),  # Из колонки G входного файла
                            'Источник': src
                        }
                        results_autopiter.append(d)
                        used_pairs.add(key)
                
                # Обрабатываем результаты Emex
                for (b1, pn1, n1, b2, pn2, src) in parallel_results['emex']:
                    key = (b1, pn1, n1, b2, pn2, src)
                    if key not in used_pairs:
                        d = {
                            'Бренд № 1': clean_excel_string(brand_from_e),  # Из колонки E входного файла
                            'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),  # Из колонки F входного файла
                            'Наименование': clean_excel_string(name_from_b),  # Из колонки B входного файла
                            'Бренд № 2': clean_excel_string(b2),  # Результат парсинга
                            'Артикул по Бренду № 2': clean_excel_string(cross_number_from_g),  # Из колонки G входного файла
                            'Источник': src
                        }
                        results_emex.append(d)
                        used_pairs.add(key)
                
                # Armtek (Selenium) - с прокси
                def parse_armtek_parallel(numbers, brand_from_e, part_number_from_f, name_from_b):
                    results = []
                    log(f"Armtek: начало обработки {len(numbers)} артикулов")
                    
                    def parse_one(num):
                        max_retries = 2  # Уменьшаем количество попыток
                        for attempt in range(max_retries):
                            try:
                                # Сначала пробуем без прокси, потом с прокси
                                if attempt == 0:
                                    proxy = None  # Первая попытка без прокси
                                    log(f"Armtek: попытка {attempt+1} без прокси для {num}")
                                else:
                                    proxy = get_next_proxy()
                                    log(f"Armtek: попытка {attempt+1} с прокси для {num}")
                                
                                # Добавляем задержку для Selenium
                                time.sleep(0.2)  # Уменьшаем задержку
                                brands = get_brands_by_artikul_armtek(num, proxy)
                                log(f"armtek: {num} → {brands}")
                                return [(brand_from_e, part_number_from_f, name_from_b, b, num, 'armtek') for b in brands]
                            except Exception as e:
                                log(f"Error parsing armtek for {num} (attempt {attempt + 1}): {str(e)}")
                                if attempt < max_retries - 1:
                                    time.sleep(1)  # Уменьшаем время ожидания
                                else:
                                    log(f"Failed to parse armtek for {num} after {max_retries} attempts")
                                    return []
                    
                    # Используем 1 поток для Selenium
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        futs = {executor.submit(parse_one, num): num for num in numbers}
                        for fut in concurrent.futures.as_completed(futs, timeout=60):  # Уменьшаем таймаут
                            try:
                                for res in fut.result():
                                    results.append(res)
                            except Exception as e:
                                log(f"Error processing armtek result: {str(e)}")
                    
                    log(f"Armtek: завершена обработка, найдено {len(results)} результатов")
                    return results
                
                armtek_results = parse_armtek_parallel(numbers, brand_from_e, part_number_from_f, name_from_b)
                
                for (b1, pn1, n1, b2, pn2, src) in armtek_results:
                    key = (b1, pn1, n1, b2, pn2, src)
                    if key not in used_pairs:
                        results_armtek.append({
                            'Бренд № 1': clean_excel_string(brand_from_e),  # Из колонки E входного файла
                            'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),  # Из колонки F входного файла
                            'Наименование': clean_excel_string(name_from_b),  # Из колонки B входного файла
                            'Бренд № 2': clean_excel_string(b2),  # Результат парсинга
                            'Артикул по Бренду № 2': clean_excel_string(cross_number_from_g),  # Из колонки G входного файла
                            'Источник': src
                        })
                        used_pairs.add(key)
                
                # Создаем файл Armtek даже если нет результатов
                if results_armtek:
                    log(f"Armtek: найдено {len(results_armtek)} результатов")
                else:
                    log("Armtek: результатов не найдено, создаем пустой файл")
                    # Создаем пустой результат для отображения файла
                    results_armtek.append({
                        'Бренд № 1': '',
                        'Артикул по Бренду № 1': '',
                        'Наименование': '',
                        'Бренд № 2': '',
                        'Артикул по Бренду № 2': '',
                        'Источник': 'armtek'
                    })
                
                # Обновляем прогресс каждые 10 строк для экономии ресурсов
                if (index + 1) % 10 == 0 or index == total_rows - 1:
                    progress = int((index + 1) / total_rows * 100)
                    task.progress = progress
                    task.log = '\n'.join(log_messages[-100:])  # Ограничиваем лог
                    task.status = 'in_progress'
                    task.save()
                    ws_send()
                    
                    # Принудительная очистка памяти
                    gc.collect()
                    
                    # Периодическая очистка процессов Chrome каждые 30 строк
                    if (index + 1) % 30 == 0:
                        try:
                            cleanup_chrome_processes()
                            log("Performed periodic Chrome cleanup")
                        except Exception as e:
                            log(f"Error during Chrome cleanup: {str(e)}")
                    
            except Exception as e:
                log(f"Error processing row {index}: {str(e)}")
                continue
        
        # Создаем результаты с улучшенной обработкой ошибок
        try:
            if results_autopiter:
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
        
        # Очистка Chrome процессов
        cleanup_chrome_processes()
        
    except Exception as e:
        task.status = 'error'
        task.error_message = str(e)
        task.save()
        ws_send()
        cleanup_chrome_processes()
        raise