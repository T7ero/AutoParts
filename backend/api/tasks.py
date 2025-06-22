import pandas as pd
from celery import shared_task
from django.core.files import File
from core.models import ParsingTask
from .autopiter_parser import get_brands_by_artikul
import re

def clean_excel_string(s):
    if not isinstance(s, str):
        return s
    # Удаляем все управляющие символы, кроме табуляции и перевода строки
    return re.sub(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]', '', s)

@shared_task
def process_parsing_task(task_id):
    task = ParsingTask.objects.get(id=task_id)
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
        results = []
        for index, row in df.iterrows():
            try:
                brand = str(row.get('Бренд', '')).strip()
                part_number = str(row.get('Артикул', '')).strip()
                if 'Наименование' in row:
                    name = str(row['Наименование']).strip()
                else:
                    name = str(row.iloc[1]).strip() if 1 < len(row) else '' 
                cross_numbers_raw = str(row.get('Кросс-номера', '')).strip()

                # Пропускаем строки, если Бренд, Артикул или Наименование пустые
                if not brand or not part_number or not name:
                    print(f"--- Строка {index} пропущена: Бренд, Артикул или Наименование отсутствует/пусто ---")
                    continue

                print(f"--- Обработка строки {index} ---")
                print(f"Бренд: {brand}, Артикул: {part_number}, Наименование: {name}, Кроссы: {cross_numbers_raw}")

                numbers = [part_number]
                if cross_numbers_raw:
                    numbers.extend([n.strip() for n in cross_numbers_raw.split(';') if n.strip()])

                print(f"Номера для поиска: {numbers}")

                used_pairs = set()
                for num in numbers:
                    # Пропускаем пустые артикулы/кросс-номера, чтобы избежать 404
                    if not num:
                        print(f"[DEBUG TASK] Пропущен пустой номер в списке для поиска: {num}")
                        continue

                    brands2 = get_brands_by_artikul(num)
                    print(f"Для артикула '{num}' найдены бренды: {brands2}")
                    for brand2 in brands2:
                        key = (brand, part_number, name, brand2, num)
                        if key not in used_pairs:
                            results.append({
                                'Бренд № 1': clean_excel_string(brand),
                                'Артикул по Бренду № 1': clean_excel_string(part_number),
                                'Наименование': clean_excel_string(name),
                                'Бренд № 2': clean_excel_string(brand2),
                                'Артикул по Бренду № 2': clean_excel_string(num)
                            })
                            used_pairs.add(key)
                progress = int((index + 1) / total_rows * 100)
                task.progress = progress
                task.save()
            except Exception as e:
                print(f"Error processing row {index}: {str(e)}")
                continue
        result_df = pd.DataFrame(results)
        result_path = f'media/results/result_{task_id}.xlsx'
        result_df.to_excel(result_path, index=False)
        with open(result_path, 'rb') as f:
            task.result_file.save(f'result_{task_id}.xlsx', File(f))
        task.status = 'Готово'
        task.progress = 100
        task.error_message = ''
        task.save()
    except Exception as e:
        task.status = 'Ошибка'
        task.error_message = str(e)
        task.save()
        raise