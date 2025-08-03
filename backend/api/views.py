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
        
        task = ParsingTask.objects.create(
            file=file,
            status='pending',
            progress=0
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
