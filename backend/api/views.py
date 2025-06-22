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
            'error_message': task.error_message
        })

class AutopiterParseView(APIView):
    permission_classes = [IsInAllowedGroup]

    def post(self, request):
        artikul = request.data.get('artikul')
        if not artikul:
            return Response({'error': 'Не передан артикул'}, status=400)
        brands = get_brands_by_artikul(artikul)
        return Response({'brands': brands})
