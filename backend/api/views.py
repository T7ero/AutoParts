from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.views import ObtainAuthToken
from django.contrib.auth import authenticate
from django.conf import settings
from core.models import ParsingTask
from .serializers import ParsingTaskSerializer
from .tasks import process_parsing_task, mark_parsing_task_cancelled
from .autopiter_parser import load_proxies_from_file, get_next_proxy
import json
import os

@api_view(['GET'])
def parsing_tasks(request):
    """Получить список задач парсинга"""
    tasks = ParsingTask.objects.all().order_by('-created_at')
    serializer = ParsingTaskSerializer(tasks, many=True)
    return Response(serializer.data)

@api_view(['POST'])
def create_parsing_task(request):
    """Создать новую задачу парсинга"""
    try:
        if 'file' not in request.FILES:
            return Response({'error': 'Файл не найден'}, status=status.HTTP_400_BAD_REQUEST)
        
        file = request.FILES['file']
        if not file.name.endswith('.xlsx'):
            return Response({'error': 'Поддерживаются только файлы .xlsx'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Получаем пользователя из токена аутентификации
        from rest_framework.authtoken.models import Token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Token '):
            token_key = auth_header.split(' ')[1]
            try:
                token = Token.objects.get(key=token_key)
                user = token.user
            except Token.DoesNotExist:
                return Response({'error': 'Неверный токен аутентификации'}, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({'error': 'Требуется токен аутентификации'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Получаем выбранные источники из POST данных
        sources = request.POST.get('sources')
        if sources:
            try:
                # Пытаемся распарсить JSON
                sources_data = json.loads(sources)
            except json.JSONDecodeError:
                # Если не JSON, то это строка с разделителями
                sources_data = [s.strip() for s in sources.split(',') if s.strip()]
        else:
            # По умолчанию все источники
            sources_data = ['autopiter', 'emex', 'armtek']
        
        task = ParsingTask.objects.create(
            user=user,
            file=file,
            status='pending',
            sources=sources_data
        )
        
        # Запускаем задачу в фоне
        process_parsing_task.delay(task.id)
        
        serializer = ParsingTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def task_status(request, task_id):
    """Получить статус задачи"""
    try:
        task = ParsingTask.objects.get(id=task_id)
        serializer = ParsingTaskSerializer(task)
        return Response(serializer.data)
    except ParsingTask.DoesNotExist:
        return Response({'error': 'Задача не найдена'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([AllowAny])
def upload_proxies(request):
    """Загрузить новый список прокси"""
    try:
        if 'file' not in request.FILES:
            return Response({'error': 'Файл прокси не найден'}, status=status.HTTP_400_BAD_REQUEST)
        
        file = request.FILES['file']
        if not file.name.endswith('.txt'):
            return Response({'error': 'Поддерживаются только файлы .txt'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Сохраняем файл прокси
        with open('proxies.txt', 'wb') as f:
            for chunk in file.chunks():
                f.write(chunk)
        
        # Перезагружаем прокси
        load_proxies_from_file()
        
        return Response({'message': 'Прокси успешно загружены'}, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def proxy_status(request):
    """Получить статус прокси"""
    try:
        from .autopiter_parser import PROXY_LIST, PROXY_INDEX
        
        return Response({
            'total_proxies': len(PROXY_LIST),
            'current_index': PROXY_INDEX,
            'next_proxy': get_next_proxy() if PROXY_LIST else None
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def reset_proxy_index(request):
    """Сбросить индекс прокси"""
    try:
        # Меняем значение в модуле напрямую, без global
        from . import autopiter_parser as ap
        ap.PROXY_INDEX = 0
        
        return Response({'message': 'Индекс прокси сброшен'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
def delete_task(request, task_id):
    """Удалить задачу"""
    try:
        task = ParsingTask.objects.get(id=task_id)
        mark_parsing_task_cancelled(task_id)
        task.delete()
        return Response({'message': 'Задача удалена'}, status=status.HTTP_200_OK)
    except ParsingTask.DoesNotExist:
        return Response({'error': 'Задача не найдена'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['DELETE'])
def clear_all_tasks(request):
    """Очистить все задачи и сбросить счетчик ID"""
    try:
        for task in ParsingTask.objects.all().only('id'):
            mark_parsing_task_cancelled(task.id)
        # Удаляем все задачи
        ParsingTask.objects.all().delete()
        
        # Сбрасываем автоинкремент ID в базе данных
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("ALTER SEQUENCE core_parsingtask_id_seq RESTART WITH 1")
        
        return Response({'message': 'Все задачи очищены, счетчик ID сброшен'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def auth_token(request):
    """Получить токен аутентификации"""
    try:
        username = request.data.get('username')
        password = request.data.get('password')
        
        if not username or not password:
            return Response({'error': 'Необходимы username и password'}, status=status.HTTP_400_BAD_REQUEST)
        
        user = authenticate(username=username, password=password)
        
        if user:
            from rest_framework.authtoken.models import Token
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user_id': user.pk,
                'username': user.username
            })
        else:
            return Response({'error': 'Неверные учетные данные'}, status=status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def task_logs(request, task_id):
    """Получить логи задачи"""
    try:
        task = ParsingTask.objects.get(id=task_id)
        
        # Получаем логи из Celery result backend
        from celery.result import AsyncResult
        celery_result = AsyncResult(str(task_id))
        
        logs = []
        
        # Добавляем базовую информацию о задаче
        logs.append({
            'timestamp': task.created_at.isoformat(),
            'message': f"Задача #{task_id} создана. Файл: {task.file.name if task.file else 'Не указан'}"
        })
        
        # Добавляем информацию о статусе
        if task.status == 'pending':
            logs.append({
                'timestamp': task.created_at.isoformat(),
                'message': "Задача поставлена в очередь на выполнение"
            })
        elif task.status == 'processing':
            logs.append({
                'timestamp': task.updated_at.isoformat(),
                'message': f"Задача в процессе выполнения"
            })
        elif task.status == 'completed':
            logs.append({
                'timestamp': task.updated_at.isoformat(),
                'message': f"Задача завершена успешно. Прогресс: 100%"
            })
            if hasattr(task, '_processed_rows') and task._processed_rows:
                logs.append({
                    'timestamp': task.updated_at.isoformat(),
                    'message': f"Обработано строк: {task._processed_rows}"
                })
        elif task.status == 'failed':
            logs.append({
                'timestamp': task.updated_at.isoformat(),
                'message': f"Задача завершена с ошибкой: {task.error_message or 'Неизвестная ошибка'}"
            })
        
        # Добавляем накопленные логи из файлового лога задачи (parsing_task_<id>.log)
        # Это даёт детальную информацию: какие бренды найдены, какая строка/артикул обрабатывается.
        try:
            import re
            log_file_path = os.path.join(settings.MEDIA_ROOT, 'results', f'parsing_task_{task_id}.log')
            if os.path.exists(log_file_path):
                with open(log_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        # Парсим время в формате [dd.mm.yyyy, HH:MM:SS]
                        m = re.match(r"^\[(\d{2}\.\d{2}\.\d{4}), (\d{2}:\d{2}:\d{2})\]\s*(.*)$", line)
                        if m:
                            dt = f"{m.group(1).split('.')[2]}-{m.group(1).split('.')[1]}-{m.group(1).split('.')[0]}T{m.group(2)}"
                            msg = m.group(3)
                            logs.append({'timestamp': dt, 'message': msg})
                        else:
                            logs.append({'timestamp': task.updated_at.isoformat(), 'message': line})
        except Exception:
            # В случае любой ошибки просто пропускаем файловые логи
            pass

        # Пытаемся получить дополнительную информацию из Celery
        if celery_result.info:
            if isinstance(celery_result.info, dict):
                # Добавляем информацию о результатах парсинга
                if 'autopiter_results' in celery_result.info:
                    logs.append({
                        'timestamp': task.updated_at.isoformat(),
                        'message': f"Autopiter: найдено {len(celery_result.info['autopiter_results'])} результатов"
                    })
                if 'emex_results' in celery_result.info:
                    logs.append({
                        'timestamp': task.updated_at.isoformat(),
                        'message': f"Emex: найдено {len(celery_result.info['emex_results'])} результатов"
                    })
                if 'armtek_results' in celery_result.info:
                    logs.append({
                        'timestamp': task.updated_at.isoformat(),
                        'message': f"Armtek: найдено {len(celery_result.info['armtek_results'])} результатов"
                    })
                
                # Добавляем информацию о текущей обрабатываемой строке
                if 'current_row' in celery_result.info:
                    current_row = celery_result.info['current_row']
                    total_rows = celery_result.info.get('total_rows', 'неизвестно')
                    logs.append({
                        'timestamp': task.updated_at.isoformat(),
                        'message': f"Обрабатывается строка {current_row} из {total_rows}"
                    })
        
        # Добавляем информацию о текущей строке из метаданных задачи
        if task.sources and isinstance(task.sources, dict) and '_meta' in task.sources:
            meta = task.sources['_meta']
            current_row = meta.get('current_row', 0)
            total_rows = meta.get('total_rows', 0)
            processed_rows = meta.get('processed_rows', 0)
            if current_row > 0 and total_rows > 0:
                progress = min(100, int((processed_rows / total_rows) * 100))
                logs.append({
                    'timestamp': task.updated_at.isoformat(),
                    'message': f"Обрабатывается строка {current_row} из {total_rows} (Прогресс: {progress}%)"
                })
                
                # Добавляем детальные логи если есть
                if 'detailed_logs' in celery_result.info:
                    for log_entry in celery_result.info['detailed_logs']:
                        logs.append({
                            'timestamp': log_entry.get('timestamp', task.updated_at.isoformat()),
                            'message': log_entry.get('message', 'Лог записи')
                        })
        
        # Добавляем информацию о времени выполнения
        if task.status in ['completed', 'failed']:
            duration = task.updated_at - task.created_at
            logs.append({
                'timestamp': task.updated_at.isoformat(),
                'message': f"Время выполнения: {duration.total_seconds():.1f} секунд"
            })
        
        # Сортируем логи по времени (если timestamps отсутствуют, они будут в конце)
        logs = [l for l in logs if l.get('timestamp')] + [l for l in logs if not l.get('timestamp')]
        
        # Добавляем информацию о прогрессе в ответ
        response_data = {'logs': logs}
        
        # Добавляем информацию о прогрессе из метаданных
        if task.sources and isinstance(task.sources, dict) and '_meta' in task.sources:
            meta = task.sources['_meta']
            response_data['progress'] = {
                'current_row': meta.get('current_row', 0),
                'total_rows': meta.get('total_rows', 0),
                'processed_rows': meta.get('processed_rows', 0),
                'progress_percent': min(100, int((meta.get('processed_rows', 0) / meta.get('total_rows', 1)) * 100)) if meta.get('total_rows', 0) > 0 else 0
            }
        
        # Добавляем дополнительную информацию в ответ
        response_data['task_id'] = task_id
        response_data['status'] = task.status
        response_data['created_at'] = task.created_at.isoformat()
        response_data['updated_at'] = task.updated_at.isoformat()
        response_data['file_name'] = task.file.name if task.file else None
        
        return Response(response_data)
        
    except ParsingTask.DoesNotExist:
        return Response({'error': 'Задача не найдена'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def download_result(request, task_id):
    """Скачать результат задачи"""
    try:
        task = ParsingTask.objects.get(id=task_id)
        
        if task.status != 'completed':
            return Response({'error': 'Задача не завершена'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Ищем файл результата
        result_file_path = None
        
        # Проверяем поле result_file
        if task.result_file:
            result_file_path = task.result_file.path
        else:
            # Ищем в папке results по ID задачи
            import os
            from django.conf import settings
            
            results_dir = os.path.join(settings.MEDIA_ROOT, 'results')
            for filename in os.listdir(results_dir):
                if filename.startswith(f'result_{task_id}') and filename.endswith('.xlsx'):
                    result_file_path = os.path.join(results_dir, filename)
                    break
        
        if not result_file_path or not os.path.exists(result_file_path):
            return Response({'error': 'Файл результата не найден'}, status=status.HTTP_404_NOT_FOUND)
        
        # Отправляем файл
        from django.http import FileResponse
        import os
        
        filename = os.path.basename(result_file_path)
        response = FileResponse(open(result_file_path, 'rb'))
        response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except ParsingTask.DoesNotExist:
        return Response({'error': 'Задача не найдена'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def download_site_result(request, task_id, site):
    """Скачать результат задачи по конкретному сайту"""
    try:
        task = ParsingTask.objects.get(id=task_id)
        
        if task.status != 'completed':
            return Response({'error': 'Задача не завершена'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not task.result_files or site not in task.result_files:
            return Response({'error': f'Файл для сайта {site} не найден'}, status=status.HTTP_404_NOT_FOUND)
        
        file_path = task.result_files[site]
        
        # Проверяем, что файл существует
        import os
        from django.conf import settings
        
        # Формируем правильный путь к файлу
        if file_path.startswith('media/'):
            # Если путь начинается с media/, убираем его и добавляем MEDIA_ROOT
            relative_path = file_path[6:]  # убираем 'media/'
            full_path = os.path.join(settings.MEDIA_ROOT, relative_path)
        elif file_path.startswith('/'):
            # Если абсолютный путь
            full_path = file_path
        else:
            # Если относительный путь без media/
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)
        
        if not os.path.exists(full_path):
            return Response({'error': 'Файл не найден на диске'}, status=status.HTTP_404_NOT_FOUND)
        
        # Отправляем файл
        from django.http import FileResponse
        
        # Определяем название сайта для файла
        site_names = {
            'autopiter': 'Autopiter',
            'emex': 'Emex',
            'armtek': 'Armtek'
        }
        site_name = site_names.get(site, site)
        
        response = FileResponse(open(full_path, 'rb'))
        response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response['Content-Disposition'] = f'attachment; filename="{site_name}_result_{task_id}.xlsx"'
        
        return response
        
    except ParsingTask.DoesNotExist:
        return Response({'error': 'Задача не найдена'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def download_stats(request, task_id):
    """
    Скачать файлы статистики (summary и unique_brands) для задачи.
    Возвращает один файл за запрос – summary или unique_brands,
    в зависимости от параметра ?type=summary|unique_brands.
    """
    try:
        task = ParsingTask.objects.get(id=task_id)

        if task.status != 'completed':
            return Response({'error': 'Задача не завершена'}, status=status.HTTP_400_BAD_REQUEST)

        stats_type = request.GET.get('type', 'summary')
        if not task.result_files or stats_type not in task.result_files:
            return Response({'error': f'Файл статистики {stats_type} не найден'}, status=status.HTTP_404_NOT_FOUND)

        file_path = task.result_files[stats_type]

        import os
        from django.conf import settings
        from django.http import FileResponse

        # Формируем полный путь
        if file_path.startswith('media/'):
            relative_path = file_path[6:]
            full_path = os.path.join(settings.MEDIA_ROOT, relative_path)
        elif file_path.startswith('/'):
            full_path = file_path
        else:
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)

        if not os.path.exists(full_path):
            return Response({'error': 'Файл не найден на диске'}, status=status.HTTP_404_NOT_FOUND)

        filename_map = {
            'summary': f'summary_result_{task_id}.xlsx',
            'unique_brands': f'unique_brands_result_{task_id}.xlsx',
        }
        download_name = filename_map.get(stats_type, os.path.basename(full_path))

        response = FileResponse(open(full_path, 'rb'))
        response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response['Content-Disposition'] = f'attachment; filename="{download_name}"'
        return response

    except ParsingTask.DoesNotExist:
        return Response({'error': 'Задача не найдена'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)