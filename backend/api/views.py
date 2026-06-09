import json
import os

from django.contrib.auth import authenticate
from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from core.models import ParsingTask
from .serializers import ParsingTaskSerializer
from .tasks import process_parsing_task, mark_parsing_task_cancelled
from .autopiter_parser import load_proxies_from_file, get_next_proxy
from .permissions import user_can_access_task


def _get_task_or_404(task_id, user):
    try:
        task = ParsingTask.objects.get(id=task_id)
    except ParsingTask.DoesNotExist:
        return None, Response({'error': 'Задача не найдена'}, status=status.HTTP_404_NOT_FOUND)
    if not user_can_access_task(user, task):
        return None, Response({'error': 'Доступ запрещён'}, status=status.HTTP_403_FORBIDDEN)
    return task, None


def _resolve_media_path(relative_path: str) -> str:
    normalized = os.path.normpath(relative_path).lstrip(os.sep)
    if normalized.startswith('..') or os.path.isabs(normalized):
        raise Http404('Invalid path')
    full_path = os.path.join(settings.MEDIA_ROOT, normalized)
    if not full_path.startswith(os.path.abspath(settings.MEDIA_ROOT)):
        raise Http404('Invalid path')
    if not os.path.isfile(full_path):
        raise Http404('File not found')
    return full_path


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def parsing_tasks(request):
    """Получить список задач парсинга"""
    if request.user.is_staff:
        tasks = ParsingTask.objects.all().order_by('-created_at')
    else:
        tasks = ParsingTask.objects.filter(user=request.user).order_by('-created_at')
    serializer = ParsingTaskSerializer(tasks, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_parsing_task(request):
    """Создать новую задачу парсинга"""
    try:
        if 'file' not in request.FILES:
            return Response({'error': 'Файл не найден'}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES['file']
        if not file.name.endswith('.xlsx'):
            return Response({'error': 'Поддерживаются только файлы .xlsx'}, status=status.HTTP_400_BAD_REQUEST)

        sources = request.POST.get('sources')
        if sources:
            try:
                parsed_sources = json.loads(sources)
            except json.JSONDecodeError:
                parsed_sources = [s.strip() for s in sources.split(',') if s.strip()]
        else:
            parsed_sources = ['autopiter', 'emex', 'armtek']

        if isinstance(parsed_sources, (list, tuple, set)):
            normalized_sources = [str(s).strip().lower() for s in parsed_sources if str(s).strip()]
        else:
            normalized_sources = []

        sources_data = {
            'sources': normalized_sources or ['autopiter', 'emex', 'armtek']
        }

        task = ParsingTask.objects.create(
            user=request.user,
            file=file,
            status='pending',
            sources=sources_data
        )

        process_parsing_task.delay(task.id)

        serializer = ParsingTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def task_status(request, task_id):
    """Получить статус задачи"""
    task, err = _get_task_or_404(task_id, request.user)
    if err:
        return err
    serializer = ParsingTaskSerializer(task)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_proxies(request):
    """Загрузить новый список прокси"""
    if not request.user.is_staff:
        return Response({'error': 'Доступ запрещён'}, status=status.HTTP_403_FORBIDDEN)
    try:
        if 'file' not in request.FILES:
            return Response({'error': 'Файл прокси не найден'}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES['file']
        if not file.name.endswith('.txt'):
            return Response({'error': 'Поддерживаются только файлы .txt'}, status=status.HTTP_400_BAD_REQUEST)

        with open('proxies.txt', 'wb') as f:
            for chunk in file.chunks():
                f.write(chunk)

        load_proxies_from_file()
        return Response({'message': 'Прокси успешно загружены'}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def proxy_status(request):
    """Получить статус прокси (без паролей)"""
    if not request.user.is_staff:
        return Response({'error': 'Доступ запрещён'}, status=status.HTTP_403_FORBIDDEN)
    try:
        from .autopiter_parser import PROXY_LIST, PROXY_INDEX

        next_proxy = get_next_proxy() if PROXY_LIST else None
        if isinstance(next_proxy, dict):
            masked = {}
            for key, val in next_proxy.items():
                if key in ('http', 'https') and val and '@' in str(val):
                    host_part = str(val).split('@', 1)[-1]
                    masked[key] = f'***@{host_part}'
                else:
                    masked[key] = val
            next_proxy = masked

        return Response({
            'total_proxies': len(PROXY_LIST),
            'current_index': PROXY_INDEX,
            'next_proxy': next_proxy,
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reset_proxy_index(request):
    """Сбросить индекс прокси"""
    if not request.user.is_staff:
        return Response({'error': 'Доступ запрещён'}, status=status.HTTP_403_FORBIDDEN)
    try:
        from . import autopiter_parser as ap
        ap.PROXY_INDEX = 0
        return Response({'message': 'Индекс прокси сброшен'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_task(request, task_id):
    """Удалить задачу"""
    task, err = _get_task_or_404(task_id, request.user)
    if err:
        return err
    try:
        mark_parsing_task_cancelled(task_id)
        task.delete()
        return Response({'message': 'Задача удалена'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def clear_all_tasks(request):
    """Очистить все задачи и сбросить счетчик ID"""
    if not request.user.is_staff:
        return Response({'error': 'Доступ запрещён'}, status=status.HTTP_403_FORBIDDEN)
    try:
        for task in ParsingTask.objects.all().only('id'):
            mark_parsing_task_cancelled(task.id)
        ParsingTask.objects.all().delete()

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
            token, _created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user_id': user.pk,
                'username': user.username,
                'is_staff': user.is_staff,
            })
        return Response({'error': 'Неверные учетные данные'}, status=status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def task_logs(request, task_id):
    """Получить логи задачи"""
    task, err = _get_task_or_404(task_id, request.user)
    if err:
        return err
    try:
        from celery.result import AsyncResult
        celery_result = AsyncResult(str(task_id))

        logs = []
        logs.append({
            'timestamp': task.created_at.isoformat(),
            'message': f"Задача #{task_id} создана. Файл: {task.file.name if task.file else 'Не указан'}"
        })

        if task.status == 'pending':
            logs.append({
                'timestamp': task.created_at.isoformat(),
                'message': "Задача поставлена в очередь на выполнение"
            })
        elif task.status == 'processing':
            logs.append({
                'timestamp': task.updated_at.isoformat(),
                'message': "Задача в процессе выполнения"
            })
        elif task.status == 'completed':
            logs.append({
                'timestamp': task.updated_at.isoformat(),
                'message': "Задача завершена успешно. Прогресс: 100%"
            })
        elif task.status == 'failed':
            logs.append({
                'timestamp': task.updated_at.isoformat(),
                'message': f"Задача завершена с ошибкой: {task.error_message or 'Неизвестная ошибка'}"
            })

        try:
            import re
            log_file_path = os.path.join(settings.MEDIA_ROOT, 'results', f'parsing_task_{task_id}.log')
            if os.path.exists(log_file_path):
                with open(log_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        m = re.match(r"^\[(\d{2}\.\d{2}\.\d{4}), (\d{2}:\d{2}:\d{2})\]\s*(.*)$", line)
                        if m:
                            dt = f"{m.group(1).split('.')[2]}-{m.group(1).split('.')[1]}-{m.group(1).split('.')[0]}T{m.group(2)}"
                            logs.append({'timestamp': dt, 'message': m.group(3)})
                        else:
                            logs.append({'timestamp': task.updated_at.isoformat(), 'message': line})
        except Exception:
            pass

        if celery_result.info and isinstance(celery_result.info, dict):
            if 'detailed_logs' in celery_result.info:
                for log_entry in celery_result.info['detailed_logs']:
                    logs.append({
                        'timestamp': log_entry.get('timestamp', task.updated_at.isoformat()),
                        'message': log_entry.get('message', 'Лог записи')
                    })

        if task.status in ['completed', 'failed']:
            duration = task.updated_at - task.created_at
            logs.append({
                'timestamp': task.updated_at.isoformat(),
                'message': f"Время выполнения: {duration.total_seconds():.1f} секунд"
            })

        meta = {}
        if task.sources and isinstance(task.sources, dict):
            meta = task.sources.get('_meta', {})
        response_payload = {
            'task_id': task_id,
            'status': task.status,
            'logs': logs,
            'created_at': task.created_at.isoformat(),
            'updated_at': task.updated_at.isoformat(),
            'file_name': task.file.name if task.file else None,
        }
        if meta:
            response_payload['meta'] = meta

        return Response(response_payload)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_result(request, task_id):
    """Скачать результат задачи"""
    task, err = _get_task_or_404(task_id, request.user)
    if err:
        return err
    try:
        if task.status != 'completed':
            return Response({'error': 'Задача не завершена'}, status=status.HTTP_400_BAD_REQUEST)

        result_file_path = None
        if task.result_file:
            result_file_path = task.result_file.path
        else:
            results_dir = os.path.join(settings.MEDIA_ROOT, 'results')
            for filename in os.listdir(results_dir):
                if filename.startswith(f'result_{task_id}') and filename.endswith('.xlsx'):
                    result_file_path = os.path.join(results_dir, filename)
                    break

        if not result_file_path or not os.path.exists(result_file_path):
            return Response({'error': 'Файл результата не найден'}, status=status.HTTP_404_NOT_FOUND)

        filename = os.path.basename(result_file_path)
        response = FileResponse(open(result_file_path, 'rb'))
        response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_site_result(request, task_id, site):
    """Скачать результат задачи по конкретному сайту"""
    task, err = _get_task_or_404(task_id, request.user)
    if err:
        return err
    try:
        if task.status != 'completed':
            return Response({'error': 'Задача не завершена'}, status=status.HTTP_400_BAD_REQUEST)

        if not task.result_files or site not in task.result_files:
            return Response({'error': f'Файл для сайта {site} не найден'}, status=status.HTTP_404_NOT_FOUND)

        file_path = task.result_files[site]
        if file_path.startswith('media/'):
            full_path = os.path.join(settings.MEDIA_ROOT, file_path[6:])
        elif file_path.startswith('/'):
            full_path = file_path
        else:
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)

        if not os.path.exists(full_path):
            return Response({'error': 'Файл не найден на диске'}, status=status.HTTP_404_NOT_FOUND)

        site_names = {'autopiter': 'Autopiter', 'emex': 'Emex', 'armtek': 'Armtek'}
        site_name = site_names.get(site, site)

        response = FileResponse(open(full_path, 'rb'))
        response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response['Content-Disposition'] = f'attachment; filename="{site_name}_result_{task_id}.xlsx"'
        return response

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_stats(request, task_id):
    """Скачать файлы статистики (summary / unique_brands)."""
    task, err = _get_task_or_404(task_id, request.user)
    if err:
        return err
    try:
        if task.status != 'completed':
            return Response({'error': 'Задача не завершена'}, status=status.HTTP_400_BAD_REQUEST)

        stats_type = request.GET.get('type', 'summary')
        if not task.result_files or stats_type not in task.result_files:
            return Response({'error': f'Файл статистики {stats_type} не найден'}, status=status.HTTP_404_NOT_FOUND)

        file_path = task.result_files[stats_type]
        if file_path.startswith('media/'):
            full_path = os.path.join(settings.MEDIA_ROOT, file_path[6:])
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

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def serve_media_file(request, file_path):
    """Защищённая отдача файлов из MEDIA_ROOT (только uploads/results)."""
    normalized = os.path.normpath(file_path).replace('\\', '/')
    allowed_prefixes = ('uploads/', 'results/')
    if not any(normalized.startswith(p) for p in allowed_prefixes):
        return Response({'error': 'Доступ запрещён'}, status=status.HTTP_403_FORBIDDEN)

    try:
        full_path = _resolve_media_path(normalized)
    except Http404:
        return Response({'error': 'Файл не найден'}, status=status.HTTP_404_NOT_FOUND)

    if normalized.startswith('uploads/') and not request.user.is_staff:
        return Response({'error': 'Доступ запрещён'}, status=status.HTTP_403_FORBIDDEN)

    if normalized.startswith('results/'):
        parts = normalized.split('_')
        for part in parts:
            if part.isdigit():
                task_id = int(part)
                task, err = _get_task_or_404(task_id, request.user)
                if err:
                    return err
                break

    response = FileResponse(open(full_path, 'rb'))
    response['Content-Disposition'] = f'inline; filename="{os.path.basename(full_path)}"'
    return response
