from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
import os

from core.models import PriceListTask, PriceListItem
from .price_list_tasks import process_price_list_task

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_price_list_task(request):
    """Создает новую задачу анализа прайс-листа"""
    try:
        # Получаем данные из запроса
        file = request.FILES.get('file')
        platform = request.data.get('platform')
        competitor_brand_filter = request.data.get('competitor_brand_filter', '')
        include_price_analysis = request.data.get('include_price_analysis', True)
        
        if not file:
            return Response({'error': 'Файл не предоставлен'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not platform or platform not in ['autopiter', 'emex', 'armtek']:
            return Response({'error': 'Неверная площадка'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Создаем задачу
        task = PriceListTask.objects.create(
            user=request.user,
            file=file,
            platform=platform,
            competitor_brand_filter=competitor_brand_filter,
            include_price_analysis=include_price_analysis
        )
        
        # Запускаем Celery задачу
        process_price_list_task.delay(task.id)
        
        return Response({
            'id': task.id,
            'status': task.status,
            'platform': task.get_platform_display(),
            'created_at': task.created_at
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_price_list_tasks(request):
    """Получает список задач анализа прайс-листа пользователя"""
    try:
        tasks = PriceListTask.objects.filter(user=request.user).order_by('-created_at')
        
        tasks_data = []
        for task in tasks:
            tasks_data.append({
                'id': task.id,
                'platform': task.get_platform_display(),
                'status': task.get_status_display(),
                'created_at': task.created_at,
                'completed_at': task.completed_at,
                'total_items': task.total_items,
                'processed_items': task.processed_items,
                'found_items': task.found_items,
                'not_found_items': task.not_found_items,
                'has_result_file': bool(task.result_file),
                'competitor_brand_filter': task.competitor_brand_filter,
                'include_price_analysis': task.include_price_analysis
            })
        
        return Response(tasks_data)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_price_list_task_details(request, task_id):
    """Получает детальную информацию о задаче"""
    try:
        task = get_object_or_404(PriceListTask, id=task_id, user=request.user)
        
        # Получаем статистику по позициям
        items = PriceListItem.objects.filter(task=task)
        
        task_data = {
            'id': task.id,
            'platform': task.get_platform_display(),
            'status': task.get_status_display(),
            'created_at': task.created_at,
            'completed_at': task.completed_at,
            'total_items': task.total_items,
            'processed_items': task.processed_items,
            'found_items': task.found_items,
            'not_found_items': task.not_found_items,
            'competitor_brand_filter': task.competitor_brand_filter,
            'include_price_analysis': task.include_price_analysis,
            'log': task.log,
            'has_result_file': bool(task.result_file),
            'statistics': {
                'total': items.count(),
                'found': items.filter(is_found=True).count(),
                'not_found': items.filter(is_found=False).count(),
                'with_errors': items.exclude(error_message='').count()
            }
        }
        
        return Response(task_data)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_price_list_items(request, task_id):
    """Получает список позиций задачи с пагинацией"""
    try:
        task = get_object_or_404(PriceListTask, id=task_id, user=request.user)
        
        # Параметры пагинации
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))
        offset = (page - 1) * page_size
        
        # Фильтры
        status_filter = request.GET.get('status')
        search = request.GET.get('search', '')
        
        items = PriceListItem.objects.filter(task=task)
        
        # Применяем фильтры
        if status_filter == 'found':
            items = items.filter(is_found=True)
        elif status_filter == 'not_found':
            items = items.filter(is_found=False)
        elif status_filter == 'errors':
            items = items.exclude(error_message='')
        
        if search:
            items = items.filter(
                models.Q(manufacturer__icontains=search) |
                models.Q(article__icontains=search) |
                models.Q(nomenclature__icontains=search)
            )
        
        # Общее количество
        total_count = items.count()
        
        # Пагинация
        items = items[offset:offset + page_size]
        
        items_data = []
        for item in items:
            items_data.append({
                'id': item.id,
                'supplier_code': item.supplier_code,
                'manufacturer': item.manufacturer,
                'article': item.article,
                'nomenclature': item.nomenclature,
                'quantity': item.quantity,
                'our_price': float(item.our_price) if item.our_price else None,
                'is_found': item.is_found,
                'marketplace_price': float(item.marketplace_price) if item.marketplace_price else None,
                'min_competitor_price': float(item.min_competitor_price) if item.min_competitor_price else None,
                'competitor_brand': item.competitor_brand,
                'error_message': item.error_message
            })
        
        return Response({
            'items': items_data,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': (total_count + page_size - 1) // page_size
            }
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_price_list_result(request, task_id):
    """Скачивает файл результата задачи"""
    try:
        task = get_object_or_404(PriceListTask, id=task_id, user=request.user)
        
        if not task.result_file:
            return Response({'error': 'Файл результата не найден'}, status=status.HTTP_404_NOT_FOUND)
        
        if not os.path.exists(task.result_file.path):
            return Response({'error': 'Файл не существует на сервере'}, status=status.HTTP_404_NOT_FOUND)
        
        # Отправляем файл
        response = FileResponse(open(task.result_file.path, 'rb'))
        response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(task.result_file.name)}"'
        
        return response
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_price_list_task(request, task_id):
    """Удаляет задачу анализа прайс-листа"""
    try:
        task = get_object_or_404(PriceListTask, id=task_id, user=request.user)
        
        # Удаляем файлы
        if task.file and os.path.exists(task.file.path):
            os.remove(task.file.path)
        
        if task.result_file and os.path.exists(task.result_file.path):
            os.remove(task.result_file.path)
        
        # Удаляем задачу (связанные записи удалятся автоматически)
        task.delete()
        
        return Response({'message': 'Задача удалена'}, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
