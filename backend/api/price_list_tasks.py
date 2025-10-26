from celery import shared_task
from django.utils import timezone
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
        
        task.total_items = len(items_data)
        task.save()
        
        log(f"Найдено {len(items_data)} позиций для анализа")
        
        # Создаем записи в базе данных
        db_items = []
        for item_data in items_data:
            db_item = PriceListItem.objects.create(
                task=task,
                supplier_code=item_data['supplier_code'],
                manufacturer=item_data['manufacturer'],
                article=item_data['article'],
                nomenclature=item_data['nomenclature'],
                quantity=item_data['quantity'],
                our_price=Decimal(str(item_data['our_price'])) if item_data['our_price'] else None
            )
            db_items.append(db_item)
        
        log(f"Создано {len(db_items)} записей в базе данных")
        
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
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Запускаем анализ всех позиций
            futures = {executor.submit(analyze_item, item): item for item in db_items}
            
            # Обрабатываем результаты по мере завершения
            for future in concurrent.futures.as_completed(futures, timeout=82800):  # 23 часа таймаут
                try:
                    result = future.result(timeout=300)  # 5 минут на позицию
                except Exception as e:
                    log(f"Ошибка получения результата: {str(e)}")
        
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
