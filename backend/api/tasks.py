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

@shared_task(bind=True, time_limit=14400, soft_time_limit=12000)  # 4 часа максимум, 3.3 часа мягкий лимит
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
        
        # Инициализируем таймаут и счетчик обработанных строк
        task._timeout_check = time.time()
        task._processed_rows = 0  # Добавляем счетчик обработанных строк
        
        total_rows = len(df)
        results_autopiter = []
        results_armtek = []
        results_emex = []
        
        def log(msg):
            log_messages.append(msg)
            print(msg)
        
        log(f"Начинаем обработку {total_rows} строк")
        
        # Оптимизированная функция для параллельного парсинга с таймаутами и прокси
        def parse_all_parallel(numbers, brand, part_number, name):
            results = {'autopiter': [], 'emex': []}
            
            def parse_one(site, parser_func, max_retries=1):  # Уменьшаем количество попыток для скорости
                def inner(num, proxy=None):
                    for attempt in range(max_retries):
                        try:
                            if attempt == 0:
                                proxy = None
                                log(f"{site.capitalize()}: попытка {attempt+1} без прокси для {num}")
                            else:
                                proxy = get_next_proxy()
                                log(f"{site.capitalize()}: попытка {attempt+1} с прокси для {num}")
                            
                            time.sleep(0.1)  # Уменьшаем задержку еще больше
                            brands = parser_func(num, proxy)
                            log(f"{site}: {num} → {brands}")
                            return [(brand, part_number, name, b, num, site) for b in brands]
                        except Exception as e:
                            log(f"Error parsing {site} for {num} (attempt {attempt + 1}): {str(e)}")
                            if attempt < max_retries - 1:
                                time.sleep(0.5)  # Уменьшаем время ожидания
                            else:
                                log(f"Failed to parse {site} for {num} after {max_retries} attempts")
                                return []
                return inner
            
            # Увеличиваем количество потоков для лучшей производительности
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:  # Увеличиваем количество потоков
                # Autopiter
                fut_autopiter = {executor.submit(parse_one('autopiter', get_brands_by_artikul), num): num for num in numbers}
                
                # Обрабатываем результаты с таймаутом
                for fut in concurrent.futures.as_completed(fut_autopiter, timeout=60):  # Уменьшаем таймаут для скорости
                    try:
                        for res in fut.result():
                            results['autopiter'].append(res)
                    except Exception as e:
                        log(f"Ошибка обработки Autopiter: {str(e)}")
                
                # Emex
                fut_emex = {executor.submit(parse_one('emex', get_brands_by_artikul_emex), num): num for num in numbers}
                
                for fut in concurrent.futures.as_completed(fut_emex, timeout=60):  # Уменьшаем таймаут для скорости
                    try:
                        for res in fut.result():
                            results['emex'].append(res)
                    except Exception as e:
                        log(f"Ошибка обработки Emex: {str(e)}")
            
            return results
        
        # Основной цикл с улучшенной обработкой ошибок и предотвращением бесконечного цикла
        for index, row in df.iterrows():
            try:
                # Проверка таймаута каждые 100 строк (увеличиваем интервал для больших файлов)
                if index % 100 == 0:
                    if time.time() - task._timeout_check > 3600:  # 60 минут
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
                
                # Обрабатываем строку даже если основной артикул пустой, но есть кросс-номера
                if not part_number and not cross_number_from_g:
                    log(f"Пропускаем строку {index + 1}: нет артикула и кросс-номеров")
                    task._processed_rows += 1  # Увеличиваем счетчик
                    continue
                
                # Создаем список всех артикулов для парсинга
                numbers_to_parse = []
                if part_number:
                    numbers_to_parse.append(part_number)
                if cross_number_from_g:
                    numbers_to_parse.extend([n.strip() for n in cross_number_from_g.split(';') if n.strip()])
                
                # Если нет артикулов для парсинга, пропускаем
                if not numbers_to_parse:
                    log(f"Пропускаем строку {index + 1}: нет артикулов для парсинга")
                    task._processed_rows += 1  # Увеличиваем счетчик
                    continue
                
                log(f"Обрабатываем строку {index + 1}: {len(numbers_to_parse)} артикулов")
                used_pairs = set()
                
                # Обрабатываем каждый артикул отдельно для создания отдельных строк
                for current_number in numbers_to_parse:
                    if not current_number:
                        continue
                    
                    try:
                        # Параллельно Autopiter, Emex для текущего артикула
                        parallel_results = parse_all_parallel([current_number], brand_from_e, part_number_from_f, name_from_b)
                        
                        # Обрабатываем результаты Autopiter для текущего артикула
                        for (b1, pn1, n1, b2, pn2, src) in parallel_results['autopiter']:
                            key = (b1, pn1, n1, b2, pn2, src)
                            if key not in used_pairs:
                                d = {
                                    'Бренд № 1': clean_excel_string(brand_from_e),  # Из колонки E входного файла
                                    'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),  # Из колонки F входного файла
                                    'Наименование': clean_excel_string(name_from_b),  # Из колонки B входного файла
                                    'Бренд № 2': clean_excel_string(b2),  # Результат парсинга
                                    'Артикул по Бренду № 2': clean_excel_string(pn2),  # Конкретный найденный артикул
                                    'Источник': src
                                }
                                results_autopiter.append(d)
                                used_pairs.add(key)
                        
                        # Обрабатываем результаты Emex для текущего артикула
                        for (b1, pn1, n1, b2, pn2, src) in parallel_results['emex']:
                            key = (b1, pn1, n1, b2, pn2, src)
                            if key not in used_pairs:
                                d = {
                                    'Бренд № 1': clean_excel_string(brand_from_e),  # Из колонки E входного файла
                                    'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),  # Из колонки F входного файла
                                    'Наименование': clean_excel_string(name_from_b),  # Из колонки B входного файла
                                    'Бренд № 2': clean_excel_string(b2),  # Результат парсинга
                                    'Артикул по Бренду № 2': clean_excel_string(pn2),  # Конкретный найденный артикул
                                    'Источник': src
                                }
                                results_emex.append(d)
                                used_pairs.add(key)
                        
                        # Armtek (Selenium) - с прокси для текущего артикула
                        def parse_armtek_parallel(numbers, brand_from_e, part_number_from_f, name_from_b):
                            results = []
                            log(f"Armtek: начало обработки {len(numbers)} артикулов")
                            
                            def parse_one(num):
                                max_retries = 3  # Уменьшаем количество попыток для скорости
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
                                        time.sleep(0.1)  # Уменьшаем задержку еще больше
                                        brands = get_brands_by_artikul_armtek(num, proxy)
                                        log(f"armtek: {num} → {brands}")
                                        return [(brand_from_e, part_number_from_f, name_from_b, b, num, 'armtek') for b in brands]
                                    except Exception as e:
                                        log(f"Error parsing armtek for {num} (attempt {attempt + 1}): {str(e)}")
                                        if attempt < max_retries - 1:
                                            time.sleep(0.5)  # Уменьшаем время ожидания
                                        else:
                                            log(f"Failed to parse armtek for {num} after {max_retries} attempts")
                                            return []
                            
                            # Используем 1 поток для Selenium
                            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                                futs = {executor.submit(parse_one, num): num for num in numbers}
                                for fut in concurrent.futures.as_completed(futs, timeout=180):  # Уменьшаем таймаут до 180с
                                    try:
                                        for res in fut.result():
                                            results.append(res)
                                    except Exception as e:
                                        log(f"Error processing armtek result: {str(e)}")
                            
                            log(f"Armtek: завершена обработка, найдено {len(results)} результатов")
                            return results
                        
                        armtek_results = parse_armtek_parallel([current_number], brand_from_e, part_number_from_f, name_from_b)
                        
                        for (b1, pn1, n1, b2, pn2, src) in armtek_results:
                            key = (b1, pn1, n1, b2, pn2, src)
                            if key not in used_pairs:
                                results_armtek.append({
                                    'Бренд № 1': clean_excel_string(brand_from_e),  # Из колонки E входного файла
                                    'Артикул по Бренду № 1': clean_excel_string(part_number_from_f),  # Из колонки F входного файла
                                    'Наименование': clean_excel_string(name_from_b),  # Из колонки B входного файла
                                    'Бренд № 2': clean_excel_string(b2),  # Результат парсинга
                                    'Артикул по Бренду № 2': clean_excel_string(pn2),  # Конкретный найденный артикул
                                    'Источник': src
                                })
                                used_pairs.add(key)
                    
                    except Exception as e:
                        log(f"Ошибка при обработке артикула {current_number} в строке {index + 1}: {str(e)}")
                        continue
                
                # Увеличиваем счетчик обработанных строк
                task._processed_rows += 1
                
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
                
                # Обновляем прогресс каждые 10 строк для более частого обновления
                if (index + 1) % 10 == 0 or index == total_rows - 1:
                    progress = int((index + 1) / total_rows * 100)
                    task.progress = progress
                    task.log = '\n'.join(log_messages[-100:])  # Ограничиваем лог
                    task.status = 'in_progress'
                    task.save()
                    ws_send()
                    
                    # Принудительная очистка памяти
                    gc.collect()
                    
                    # Периодическая очистка процессов Chrome каждые 50 строк
                    if (index + 1) % 50 == 0:
                        try:
                            cleanup_chrome_processes()
                            log("Performed periodic Chrome cleanup")
                        except Exception as e:
                            log(f"Error during Chrome cleanup: {str(e)}")
                
            except Exception as e:
                log(f"Error processing row {index + 1}: {str(e)}")
                task._processed_rows += 1  # Увеличиваем счетчик даже при ошибке
                continue
        
        log(f"Обработка завершена. Обработано строк: {task._processed_rows} из {total_rows}")
        
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