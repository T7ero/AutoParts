from celery import shared_task
from django.utils import timezone
from django.db import IntegrityError
from datetime import datetime
import pandas as pd
import os
import time
import concurrent.futures
from typing import List, Dict
from decimal import Decimal

from core.models import PriceListTask, PriceListItem
from .price_list_parser import (
    parse_price_list_file,
    check_autopiter_item,
    check_emex_item,
    check_armtek_item,
    create_result_excel
)

@shared_task(bind=True, time_limit=86400, soft_time_limit=82800)  # 24 часа
def process_price_list_task(self, task_id: int):
    """Основная задача для анализа прайс-листа на площадках"""
    
    try:
        # Получаем задачу
        task = PriceListTask.objects.get(id=task_id)
        task.status = 'processing'
        task.processed_items = 0  # Сбрасываем счетчик обработанных элементов
        task.save()
        
        def log(msg):
            """Логирование"""
            timestamp = datetime.now().strftime('%d.%m.%Y, %H:%M:%S')
            log_message = f"[{timestamp}] {msg}"
            print(log_message)
            
            # Сохраняем в поле log задачи
            if task.log:
                task.log += '\n' + log_message
            else:
                task.log = log_message
            task.save()
        
        log(f"Начинаем анализ прайс-листа на площадке {task.get_platform_display()}")
        
        # Парсим файл прайс-листа
        log(f"Парсим файл: {task.file.name}")
        items_data = parse_price_list_file(task.file.path)
        
        if not items_data:
            log("Ошибка: не удалось распарсить файл прайс-листа")
            task.status = 'failed'
            task.save()
            return
        
        log(f"Найдено {len(items_data)} позиций в файле")
        
        # Удаляем старые записи для этой задачи (если была повторная загрузка)
        old_items_count = PriceListItem.objects.filter(task=task).count()
        if old_items_count > 0:
            log(f"Удаляем {old_items_count} старых записей для этой задачи")
            PriceListItem.objects.filter(task=task).delete()
        
        # Дедуплицируем данные из файла (на случай дубликатов в самом файле)
        # Используем комбинацию (manufacturer, article) как ключ
        seen_items = {}
        unique_items_data = []
        duplicates_count = 0
        for item_data in items_data:
            key = (str(item_data.get('manufacturer', '')).strip(), str(item_data.get('article', '')).strip())
            if key not in seen_items:
                seen_items[key] = item_data
                unique_items_data.append(item_data)
            else:
                duplicates_count += 1
                # Если новая запись имеет более полные данные (например, есть цена), обновляем
                old_item = seen_items[key]
                if item_data.get('our_price') and not old_item.get('our_price'):
                    seen_items[key] = item_data
                    # Заменяем в списке
                    idx = unique_items_data.index(old_item)
                    unique_items_data[idx] = item_data
        
        if duplicates_count > 0:
            log(f"Найдено и удалено {duplicates_count} дубликатов из файла")
        
        # Создаем записи в базе данных с защитой от дубликатов
        db_items = []
        created_count = 0
        updated_count = 0
        for item_data in unique_items_data:
            try:
                db_item, created = PriceListItem.objects.get_or_create(
                    task=task,
                    manufacturer=item_data['manufacturer'],
                    article=item_data['article'],
                    defaults={
                        'supplier_code': item_data.get('supplier_code', ''),
                        'nomenclature': item_data.get('nomenclature', ''),
                        'quantity': item_data.get('quantity', 0),
                        'our_price': Decimal(str(item_data['our_price'])) if item_data.get('our_price') else None
                    }
                )
                if not created:
                    # Если запись уже существует, обновляем поля
                    db_item.supplier_code = item_data.get('supplier_code', '') or db_item.supplier_code
                    db_item.nomenclature = item_data.get('nomenclature', '') or db_item.nomenclature
                    if item_data.get('quantity'):
                        db_item.quantity = item_data['quantity']
                    if item_data.get('our_price'):
                        db_item.our_price = Decimal(str(item_data['our_price']))
                    db_item.save()
                    updated_count += 1
                else:
                    created_count += 1
                db_items.append(db_item)
            except IntegrityError as e:
                # Дополнительная защита на случай гонки условий
                log(f"Предупреждение: попытка создать дубликат {item_data.get('manufacturer')} {item_data.get('article')}: {str(e)}")
                try:
                    db_item = PriceListItem.objects.get(
                        task=task,
                        manufacturer=item_data['manufacturer'],
                        article=item_data['article']
                    )
                    db_items.append(db_item)
                except PriceListItem.DoesNotExist:
                    log(f"Ошибка: не удалось найти или создать запись для {item_data.get('manufacturer')} {item_data.get('article')}")
        
        # Обновляем total_items на реальное количество уникальных элементов для обработки
        task.total_items = len(db_items)
        task.save()
        
        log(f"Создано {created_count} новых записей, обновлено {updated_count} существующих. Всего уникальных позиций для обработки: {len(db_items)}")
        
        # Функция для анализа одной позиции
        def analyze_item(item: PriceListItem) -> Dict:
            """Анализирует одну позицию на выбранной площадке"""
            try:
                log(f"Анализируем: {item.manufacturer} {item.article}")
                
                # Выбираем функцию анализа в зависимости от площадки
                if task.platform == 'autopiter':
                    result = check_autopiter_item(
                        item.supplier_code,
                        item.manufacturer,
                        item.article,
                        task.competitor_brand_filter
                    )
                elif task.platform == 'emex':
                    result = check_emex_item(
                        item.supplier_code,
                        item.manufacturer,
                        item.article,
                        task.competitor_brand_filter
                    )
                elif task.platform == 'armtek':
                    result = check_armtek_item(
                        item.supplier_code,
                        item.manufacturer,
                        item.article,
                        task.competitor_brand_filter
                    )
                else:
                    result = {
                        'is_found': False,
                        'marketplace_price': None,
                        'min_competitor_price': None,
                        'competitor_brand': None,
                        'error_message': f'Неизвестная площадка: {task.platform}'
                    }
                
                # Обновляем запись в базе
                item.is_found = bool(result.get('is_found'))
                item.marketplace_price = Decimal(str(result['marketplace_price'])) if result.get('marketplace_price') else None
                item.min_competitor_price = Decimal(str(result['min_competitor_price'])) if result.get('min_competitor_price') else None
                # полю competitor_brand разрешим быть пустым строковым значением
                item.competitor_brand = result.get('competitor_brand') or ''
                item.error_message = result.get('error_message') or ''
                
                # Сохраняем количество товара
                if 'quantity_in_stock' in result:
                    item.quantity_in_stock = result['quantity_in_stock']
                if 'competitor_quantity' in result:
                    item.competitor_quantity = result['competitor_quantity']
                
                item.save()
                
                # Обновляем счетчик обработанных
                task.processed_items += 1
                task.save()
                
                log(f"Обработано {task.processed_items}/{task.total_items}: {'найдено' if result['is_found'] else 'не найдено'}")
                
                return result
                
            except Exception as e:
                log(f"Ошибка анализа позиции {item.manufacturer} {item.article}: {str(e)}")
                item.error_message = str(e)
                item.save()
                
                task.processed_items += 1
                task.save()
                
                return {
                    'is_found': False,
                    'marketplace_price': None,
                    'min_competitor_price': None,
                    'competitor_brand': None,
                    'error_message': str(e)
                }
        
        # Параллельная обработка позиций
        max_workers = 1  # Устанавливаем в 1 для устранения 429 Rate Limit ошибок
        
        # Защита от повторной обработки: создаем множество обработанных ID
        processed_item_ids = set()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Запускаем анализ всех позиций
            futures = {executor.submit(analyze_item, item): item.id for item in db_items}
            
            # Обрабатываем результаты по мере завершения
            for future in concurrent.futures.as_completed(futures, timeout=82800):  # 23 часа таймаут
                item_id = None
                try:
                    item_id = futures[future]
                    # Проверяем, не обработан ли уже этот элемент (защита от дубликатов)
                    if item_id in processed_item_ids:
                        log(f"Предупреждение: элемент {item_id} уже обработан, пропускаем")
                        continue
                    
                    # Помечаем элемент как обработанный до получения результата
                    processed_item_ids.add(item_id)
                    
                    result = future.result(timeout=300)  # 5 минут на позицию
                    
                    # Проверяем, все ли элементы обработаны
                    if len(processed_item_ids) >= len(db_items):
                        log(f"Все {len(db_items)} элементов обработаны, завершаем обработку")
                        break
                        
                except Exception as e:
                    item_id_str = str(item_id) if item_id is not None else 'unknown'
                    log(f"Ошибка получения результата для элемента {item_id_str}: {str(e)}")
                    # Элемент уже помечен как обработанный, продолжаем
        
        # Создаем файл результата
        log("Создаем файл результата...")
        
        # Подготавливаем данные для Excel
        result_data = []
        for item in db_items:
            result_data.append({
                'manufacturer': item.manufacturer,
                'article': item.article,
                'nomenclature': item.nomenclature,
                'is_found': item.is_found,
                'platform': task.get_platform_display(),
                'marketplace_price': float(item.marketplace_price) if item.marketplace_price else None,
                'min_competitor_price': float(item.min_competitor_price) if item.min_competitor_price else None,
                'competitor_brand': item.competitor_brand,
                'quantity_in_stock': getattr(item, 'quantity_in_stock', None),
                'competitor_quantity': getattr(item, 'competitor_quantity', None)
            })
        
        # Создаем файл результата
        result_filename = f"price_list_results_{task_id}_{int(time.time())}.xlsx"
        result_dir = os.path.join('media', 'results')
        os.makedirs(result_dir, exist_ok=True)
        result_path = os.path.join(result_dir, result_filename)
        
        if create_result_excel(result_data, result_path):
            # сохраняем относительный путь в FileField через name
            try:
                from django.core.files.base import File
                # открываем и присваиваем name, чтобы download эндпоинт видел файл
                with open(result_path, 'rb') as f:
                    task.result_file.save(result_filename, File(f), save=False)
            except Exception:
                # fallback: просто путь
                task.result_file = result_path
            log(f"Файл результата создан: {result_filename}")
        else:
            log("Ошибка создания файла результата")
        
        # Завершаем задачу
        task.status = 'completed'
        task.save()
        
        # Считаем найденные/не найденные по позициям задачи
        found_cnt = sum(1 for it in db_items if it.is_found)
        not_found_cnt = len(db_items) - found_cnt
        
        # Обновляем поля задачи
        task.found_items = found_cnt
        task.not_found_items = not_found_cnt
        task.status = 'completed'
        task.save()
        
        log(f"Анализ завершен. Обработано: {task.processed_items}, Найдено: {found_cnt}, Не найдено: {not_found_cnt}")
        
        return {
            'status': 'completed',
            'task_id': task_id,
            'processed_items': task.processed_items,
            'found_items': found_cnt,
            'not_found_items': not_found_cnt,
            'result_file': task.result_file.name if task.result_file else None
        }
        
    except Exception as e:
        log(f"Критическая ошибка: {str(e)}")
        task.status = 'failed'
        task.error_message = str(e)
        task.save()
        
        return {
            'status': 'failed',
            'task_id': task_id,
            'error': str(e)
        }
