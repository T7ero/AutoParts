from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission
from django.shortcuts import get_object_or_404
from core.models import Part, CrossReference, ParsingTask
from .serializers import PartSerializer, CrossReferenceSerializer, ParsingTaskSerializer
from .tasks import process_parsing_task
import os
from rest_framework import serializers
from rest_framework.views import APIView
from .autopiter_parser import get_brands_by_artikul
import pandas as pd
from django.utils.dateparse import parse_datetime

# Create your views here.

class IsInAllowedGroup(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.groups.filter(name='allowed_users').exists()

class PartViewSet(viewsets.ModelViewSet):
    queryset = Part.objects.all()
    serializer_class = PartSerializer
    permission_classes = [IsInAllowedGroup]

class CrossReferenceViewSet(viewsets.ModelViewSet):
    queryset = CrossReference.objects.all()
    serializer_class = CrossReferenceSerializer
    permission_classes = [IsInAllowedGroup]

    def get_queryset(self):
        queryset = CrossReference.objects.all()
        part_id = self.request.query_params.get('part_id', None)
        if part_id is not None:
            queryset = queryset.filter(part_id=part_id)
        return queryset

class ParsingTaskViewSet(viewsets.ModelViewSet):
    queryset = ParsingTask.objects.all()
    serializer_class = ParsingTaskSerializer
    permission_classes = [IsInAllowedGroup]
    @action(detail=False, methods=['delete'])
    def clear(self, request):
        ParsingTask.objects.all().delete()
        return Response({'status': 'ok'})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        try:
            if 'file' not in self.request.FILES:
                raise ValueError('Файл не был загружен')
            file = self.request.FILES['file']
            if not file.name.endswith('.xlsx'):
                raise ValueError('Поддерживаются только файлы Excel (.xlsx)')
            if file.size > 10 * 1024 * 1024:
                raise ValueError('Размер файла не должен превышать 10MB')
            task = serializer.save(user=self.request.user)
            process_parsing_task.delay(task.id)
        except Exception as e:
            raise serializers.ValidationError({'error': str(e)})

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        task = get_object_or_404(ParsingTask, pk=pk)
        return Response({
            'status': task.status,
            'progress': task.progress,
            'error_message': task.error_message,
            'result_files': task.result_files,
        })

    @action(detail=True, methods=['get'])
    def log(self, request, pk=None):
        task = get_object_or_404(ParsingTask, pk=pk)
        return Response({'log': task.log or ''})

    @action(detail=True, methods=['get'])
    def preview(self, request, pk=None):
        """Возвращает первые 10 строк Excel-файла задачи для предпросмотра"""
        task = get_object_or_404(ParsingTask, pk=pk)
        try:
            df = pd.read_excel(task.file.path)
            preview = df.head(10).fillna('').to_dict(orient='records')
            columns = list(df.columns)
            return Response({'columns': columns, 'rows': preview})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        status = request.query_params.get('status')
        user_id = request.query_params.get('user_id')
        created_after = request.query_params.get('created_after')
        created_before = request.query_params.get('created_before')
        if status:
            queryset = queryset.filter(status=status)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if created_after:
            queryset = queryset.filter(created_at__gte=parse_datetime(created_after))
        if created_before:
            queryset = queryset.filter(created_at__lte=parse_datetime(created_before))
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class AutopiterParseView(APIView):
    permission_classes = [IsInAllowedGroup]

    def post(self, request):
        artikul = request.data.get('artikul')
        if not artikul:
            return Response({'error': 'Не передан артикул'}, status=400)
        brands = get_brands_by_artikul(artikul)
        return Response({'brands': brands})
