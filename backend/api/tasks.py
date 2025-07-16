import pandas as pd
from celery import shared_task
from django.core.files import File
from core.models import ParsingTask
from .autopiter_parser import get_brands_by_artikul, get_brands_by_artikul_armtek, get_brands_by_artikul_emex
import re
import concurrent.futures
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

def clean_excel_string(s):
    if not isinstance(s, str):
        return s
    # Удаляем все управляющие символы, кроме табуляции и перевода строки
    return re.sub(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]', '', s)

@shared_task
def process_parsing_task(task_id):
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
        df = pd.read_excel(task.file.path)
        # Пропускаем первые несколько строк, если они пустые или содержат ненужные заголовки.
        # На основе вашего скриншота, данные начинаются со строки 2 (индекс 1 в Python, если 0 - это заголовки)
        # Предполагаем, что первая строка содержит заголовки. Если нет - нужно будет донастроить `header`
        # df = pd.read_excel(task.file.path, header=0) # Если заголовки в первой строке (индекс 0)
        # df = pd.read_excel(task.file.path, header=1) # Если заголовки во второй строке (индекс 1)

        # Очищаем DataFrame от пустых строк, которые могут быть в начале или конце файла
        df.dropna(how='all', inplace=True)

        total_rows = len(df)
        results_autopiter = []
        results_armtek = []
        results_emex = []
        # --- Параллельный парсинг для Autopiter, Emex ---
        def log(msg):
            log_messages.append(msg)
            print(msg)
        def parse_all_parallel(numbers, brand, part_number, name):
            results = {'autopiter': [], 'emex': []}
            def parse_one(site, func):
                def inner(num):
                    brands = func(num)
                    log(f"{site}: {num} → {brands}")
                    return [(brand, part_number, name, b, num, site) for b in brands]
                return inner
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                # Autopiter
                fut_autopiter = {executor.submit(parse_one('autopiter', get_brands_by_artikul), num): num for num in numbers}
                # Emex
                fut_emex = {executor.submit(parse_one('emex', get_brands_by_artikul_emex), num): num for num in numbers}
                for fut in concurrent.futures.as_completed(fut_autopiter):
                    for res in fut.result():
                        results['autopiter'].append(res)
                for fut in concurrent.futures.as_completed(fut_emex):
                    for res in fut.result():
                        results['emex'].append(res)
            return results
        # --- Основной цикл ---
        for index, row in df.iterrows():
            try:
                brand = str(row.get('Бренд', '')).strip()
                part_number = str(row.get('Артикул', '')).strip()
                if 'Наименование' in row:
                    name = str(row['Наименование']).strip()
                else:
                    name = str(row.iloc[1]).strip() if 1 < len(row) else '' 
                cross_numbers_raw = str(row.get('Кросс-номера', '')).strip()
                if not brand or not part_number or not name:
                    continue
                numbers = [part_number]
                if cross_numbers_raw:
                    numbers.extend([n.strip() for n in cross_numbers_raw.split(';') if n.strip()])
                used_pairs = set()
                # Параллельно Autopiter, Emex
                parallel_results = parse_all_parallel(numbers, brand, part_number, name)
                for site, result_list in parallel_results.items():
                    for (b1, pn1, n1, b2, pn2, src) in result_list:
                        key = (b1, pn1, n1, b2, pn2, src)
                        if key not in used_pairs:
                            d = {
                                'Бренд № 1': clean_excel_string(b1),
                                'Артикул по Бренду № 1': clean_excel_string(pn1),
                                'Наименование': clean_excel_string(n1),
                                'Бренд № 2': clean_excel_string(b2),
                                'Артикул по Бренду № 2': clean_excel_string(pn2),
                                'Источник': src
                            }
                            if src == 'autopiter':
                                results_autopiter.append(d)
                            elif src == 'emex':
                                results_emex.append(d)
                            used_pairs.add(key)
                # Armtek (Selenium, теперь параллельно)
                def parse_armtek_parallel(numbers, brand, part_number, name):
                    results = []
                    def parse_one(num):
                        brands = get_brands_by_artikul_armtek(num)
                        log(f"armtek: {num} → {brands}")
                        return [(brand, part_number, name, b, num, 'armtek') for b in brands]
                    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                        futs = {executor.submit(parse_one, num): num for num in numbers}
                        for fut in concurrent.futures.as_completed(futs):
                            for res in fut.result():
                                results.append(res)
                    return results
                armtek_results = parse_armtek_parallel(numbers, brand, part_number, name)
                for (b1, pn1, n1, b2, pn2, src) in armtek_results:
                    key = (b1, pn1, n1, b2, pn2, src)
                    if key not in used_pairs:
                        results_armtek.append({
                            'Бренд № 1': clean_excel_string(b1),
                            'Артикул по Бренду № 1': clean_excel_string(pn1),
                            'Наименование': clean_excel_string(n1),
                            'Бренд № 2': clean_excel_string(b2),
                            'Артикул по Бренду № 2': clean_excel_string(pn2),
                            'Источник': src
                        })
                        used_pairs.add(key)
                progress = int((index + 1) / total_rows * 100)
                task.progress = progress
                task.log = '\n'.join(log_messages)
                task.status = 'in_progress'
                task.save()
                ws_send()
            except Exception as e:
                log(f"Error processing row {index}: {str(e)}")
                continue
        # Сохраняем отдельные Excel-файлы для каждого сайта
        result_paths = {}
        if results_autopiter:
            df_autopiter = pd.DataFrame(results_autopiter)
            path_autopiter = f'media/results/result_autopiter_{task_id}.xlsx'
            df_autopiter.to_excel(path_autopiter, index=False)
            result_paths['autopiter'] = path_autopiter
        if results_armtek:
            df_armtek = pd.DataFrame(results_armtek)
            path_armtek = f'media/results/result_armtek_{task_id}.xlsx'
            df_armtek.to_excel(path_armtek, index=False)
            result_paths['armtek'] = path_armtek
        if results_emex:
            df_emex = pd.DataFrame(results_emex)
            path_emex = f'media/results/result_emex_{task_id}.xlsx'
            df_emex.to_excel(path_emex, index=False)
            result_paths['emex'] = path_emex
        # Сохраняем только первый из файлов как основной результат задачи (для обратной совместимости)
        main_file = next(iter(result_paths.values()), None)
        if main_file:
            with open(main_file, 'rb') as f:
                task.result_file.save(main_file.split('/')[-1], File(f))
        task.result_files = result_paths
        task.status = 'completed'
        task.progress = 100
        task.error_message = ''
        task.log = '\n'.join(log_messages)
        ws_send()
    except Exception as e:
        task.status = 'failed'
        task.error_message = str(e)
        log_messages.append(f"Ошибка: {str(e)}")
        task.log = '\n'.join(log_messages)
        ws_send()
        raise
    finally:
        if task.status not in ['completed', 'failed']:
            task.status = 'failed'
        task.save()
        ws_send()