from rest_framework import serializers
from core.models import Part, CrossReference, ParsingTask

class PartSerializer(serializers.ModelSerializer):
    class Meta:
        model = Part
        fields = ['id', 'name', 'part_number', 'brand', 'created_at', 'updated_at']

class CrossReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrossReference
        fields = ['id', 'part', 'competitor_brand', 'competitor_number', 'source_url', 'created_at']

class ParsingTaskSerializer(serializers.ModelSerializer):
    file_name = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    current_row = serializers.SerializerMethodField()
    total_rows = serializers.SerializerMethodField()
    processed_rows = serializers.SerializerMethodField()
    
    class Meta:
        model = ParsingTask
        fields = ['id', 'user', 'file', 'file_name', 'status', 'result_file', 'result_files', 'created_at', 'updated_at', 'error_message', 'progress', 'current_row', 'total_rows', 'processed_rows']
        read_only_fields = ['user', 'status', 'result_file', 'result_files', 'error_message', 'progress', 'current_row', 'total_rows', 'processed_rows']
    
    def get_file_name(self, obj):
        """Получить название файла"""
        if obj.file:
            if hasattr(obj.file, 'name'):
                return obj.file.name
            elif isinstance(obj.file, str):
                # Если file это строка с путем
                import os
                return os.path.basename(obj.file)
        return None
    
    def get_progress(self, obj):
        """Рассчитать прогресс выполнения задачи"""
        # Пытаемся получить из метаданных
        if obj.sources and isinstance(obj.sources, dict) and '_meta' in obj.sources:
            meta = obj.sources['_meta']
            total = meta.get('total_rows', 0)
            processed = meta.get('processed_rows', 0)
            if total > 0:
                return min(100, int((processed / total) * 100))
        
        # Если задача завершена, возвращаем 100%
        if obj.status == 'completed':
            return 100
        # Если задача еще не началась, возвращаем 0%
        if obj.status == 'pending':
            return 0
        
        return 0
    
    def get_current_row(self, obj):
        """Получить текущую обрабатываемую строку"""
        if obj.sources and isinstance(obj.sources, dict) and '_meta' in obj.sources:
            return obj.sources['_meta'].get('current_row', 0)
        return 0
    
    def get_total_rows(self, obj):
        """Получить общее количество строк"""
        if obj.sources and isinstance(obj.sources, dict) and '_meta' in obj.sources:
            return obj.sources['_meta'].get('total_rows', 0)
        return 0
    
    def get_processed_rows(self, obj):
        """Получить количество обработанных строк"""
        if obj.sources and isinstance(obj.sources, dict) and '_meta' in obj.sources:
            return obj.sources['_meta'].get('processed_rows', 0)
        return 0
    
    def validate_file(self, value):
        """Валидация загружаемого файла"""
        if not value:
            raise serializers.ValidationError("Файл не был загружен")
        
        if not value.name.endswith('.xlsx'):
            raise serializers.ValidationError("Поддерживаются только файлы Excel (.xlsx)")
        
        if value.size > 10 * 1024 * 1024:  # 10MB
            raise serializers.ValidationError("Размер файла не должен превышать 10MB")
        
        return value
    
    def create(self, validated_data):
        """Создание задачи с файлом"""
        try:
            task = ParsingTask.objects.create(**validated_data)
            return task
        except Exception as e:
            print(f"Ошибка создания задачи: {str(e)}")
            raise serializers.ValidationError(f"Ошибка создания задачи: {str(e)}") 