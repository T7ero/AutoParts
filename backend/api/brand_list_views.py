import os

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .brand_config import (
    LIST_META,
    load_list_items,
    save_list,
    parse_file_content,
    list_all_metadata,
    ensure_defaults,
)


def _staff_required(user):
    if not user.is_staff:
        return Response({'error': 'Доступ запрещён'}, status=status.HTTP_403_FORBIDDEN)
    return None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def brand_lists_overview(request):
    """Список всех доступных конфигурационных списков."""
    denied = _staff_required(request.user)
    if denied:
        return denied
    ensure_defaults()
    return Response(list_all_metadata())


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def brand_list_detail(request, list_id):
    """Получить или сохранить содержимое списка."""
    denied = _staff_required(request.user)
    if denied:
        return denied

    if list_id not in LIST_META:
        return Response({'error': 'Список не найден'}, status=status.HTTP_404_NOT_FOUND)

    meta = LIST_META[list_id]

    if request.method == 'GET':
        items = load_list_items(list_id)
        return Response({
            'id': list_id,
            'title': meta['title'],
            'description': meta['description'],
            'group': meta['group'],
            'items': items,
            'count': len(items),
            'file': f'config/lists/{list_id}.txt',
        })

    items = request.data.get('items')
    if items is None:
        text = request.data.get('text', '')
        items = parse_file_content(text)
    elif not isinstance(items, list):
        return Response({'error': 'Поле items должно быть массивом строк'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        count = save_list(list_id, [str(i) for i in items])
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'message': 'Список сохранён',
        'id': list_id,
        'count': count,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def brand_list_upload(request, list_id):
    """Загрузить список из файла (.txt, .csv)."""
    denied = _staff_required(request.user)
    if denied:
        return denied

    if list_id not in LIST_META:
        return Response({'error': 'Список не найден'}, status=status.HTTP_404_NOT_FOUND)

    if 'file' not in request.FILES:
        return Response({'error': 'Файл не найден'}, status=status.HTTP_400_BAD_REQUEST)

    file = request.FILES['file']
    allowed_ext = ('.txt', '.csv', '.list')
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in allowed_ext:
        return Response(
            {'error': f'Поддерживаются файлы: {", ".join(allowed_ext)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        content = file.read().decode('utf-8-sig')
        items = parse_file_content(content)
        count = save_list(list_id, items)
    except UnicodeDecodeError:
        return Response({'error': 'Файл должен быть в кодировке UTF-8'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'message': 'Файл успешно загружен',
        'id': list_id,
        'count': count,
    })
