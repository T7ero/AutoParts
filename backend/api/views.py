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
from core.models import ParsingTask
from .serializers import ParsingTaskSerializer
from .tasks import process_parsing_task
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
            progress=0,
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
        from .autopiter_parser import PROXY_INDEX
        global PROXY_INDEX
        PROXY_INDEX = 0
        
        return Response({'message': 'Индекс прокси сброшен'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
def delete_task(request, task_id):
    """Удалить задачу"""
    try:
        task = ParsingTask.objects.get(id=task_id)
        task.delete()
        return Response({'message': 'Задача удалена'}, status=status.HTTP_200_OK)
    except ParsingTask.DoesNotExist:
        return Response({'error': 'Задача не найдена'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['DELETE'])
def clear_all_tasks(request):
    """Очистить все задачи и сбросить счетчик ID"""
    try:
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
                'message': f"Задача в процессе выполнения. Прогресс: {task.progress}%"
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
        
        # Сортируем логи по времени
        logs.sort(key=lambda x: x['timestamp'])
        
        return Response({
            'task_id': task_id,
            'status': task.status,
            'progress': task.progress,
            'logs': logs,
            'created_at': task.created_at.isoformat(),
            'updated_at': task.updated_at.isoformat(),
            'file_name': task.file.name if task.file else None
        })
        
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
def test_api(request):
    """Тестовый endpoint для проверки работы API"""
    return Response({'message': 'API работает!', 'timestamp': '2025-08-14'})

@api_view(['GET'])
@permission_classes([AllowAny])
def download_site_result(request, task_id, site):
    """Скачать результат задачи по конкретному сайту"""
    print(f"DEBUG: download_site_result вызвана с task_id={task_id}, site={site}")
    
    try:
        task = ParsingTask.objects.get(id=task_id)
        print(f"DEBUG: Задача найдена: {task.id}, статус: {task.status}")
        
        if task.status != 'completed':
            print(f"DEBUG: Задача не завершена: {task.status}")
            return Response({'error': 'Задача не завершена'}, status=status.HTTP_400_BAD_REQUEST)
        
        print(f"DEBUG: result_files: {task.result_files}")
        
        if not task.result_files or site not in task.result_files:
            print(f"DEBUG: Файл для сайта {site} не найден в result_files")
            return Response({'error': f'Файл для сайта {site} не найден'}, status=status.HTTP_404_NOT_FOUND)
        
        file_path = task.result_files[site]
        print(f"DEBUG: Путь к файлу: {file_path}")
        
        # Проверяем, что файл существует
        import os
        from django.conf import settings
        
        # Если file_path это относительный путь, добавляем MEDIA_ROOT
        if not os.path.isabs(file_path):
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)
        else:
            full_path = file_path
        
        print(f"DEBUG: Полный путь к файлу: {full_path}")
        print(f"DEBUG: MEDIA_ROOT: {settings.MEDIA_ROOT}")
        print(f"DEBUG: Файл существует: {os.path.exists(full_path)}")
        
        if not os.path.exists(full_path):
            print(f"DEBUG: Файл не найден на диске: {full_path}")
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
        
        print(f"DEBUG: Отправляем файл: {full_path}")
        
        response = FileResponse(open(full_path, 'rb'))
        response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response['Content-Disposition'] = f'attachment; filename="{site_name}_result_{task_id}.xlsx"'
        
        return response
        
    except ParsingTask.DoesNotExist:
        print(f"DEBUG: Задача {task_id} не найдена")
        return Response({'error': 'Задача не найдена'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"DEBUG: Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
