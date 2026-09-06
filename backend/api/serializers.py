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
    progress_autopiter = serializers.SerializerMethodField()
    progress_emex = serializers.SerializerMethodField()
    progress_armtek = serializers.SerializerMethodField()
    processed_autopiter = serializers.SerializerMethodField()
    total_autopiter = serializers.SerializerMethodField()
    processed_emex = serializers.SerializerMethodField()
    total_emex = serializers.SerializerMethodField()
    processed_armtek = serializers.SerializerMethodField()
    total_armtek = serializers.SerializerMethodField()
    current_row = serializers.SerializerMethodField()
    total_rows = serializers.SerializerMethodField()
    processed_rows = serializers.SerializerMethodField()
    current_number = serializers.SerializerMethodField()
    total_cross_numbers = serializers.SerializerMethodField()
    processed_cross_numbers = serializers.SerializerMethodField()

    
    class Meta:
        model = ParsingTask
        fields = [
            'id', 'user', 'file', 'file_name', 'status', 'result_file', 'result_files',
            'created_at', 'error_message',
            'progress', 'progress_autopiter', 'progress_emex', 'progress_armtek',
            'processed_autopiter', 'total_autopiter',
            'processed_emex', 'total_emex',
            'processed_armtek', 'total_armtek',
            'current_row', 'total_rows', 'processed_rows',
            'current_number', 'total_cross_numbers', 'processed_cross_numbers',
        ]
        read_only_fields = [
            'user', 'status', 'result_file', 'result_files', 'error_message',
            'progress', 'progress_autopiter', 'progress_emex', 'progress_armtek',
            'processed_autopiter', 'total_autopiter',
            'processed_emex', 'total_emex',
            'processed_armtek', 'total_armtek',
            'current_row', 'total_rows', 'processed_rows',
            'current_number', 'total_cross_numbers', 'processed_cross_numbers',
        ]
    
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

    def _get_meta(self, obj):
        if obj.sources and isinstance(obj.sources, dict):
            return obj.sources.get('_meta') or {}
        return {}

    def get_progress(self, obj):
        meta = self._get_meta(obj)
        # Сначала пробуем взять готовый прогресс из _meta
        if 'progress' in meta:
            return meta.get('progress', 0)
        total_cross = meta.get('total_cross_numbers') or 0
        processed_cross = meta.get('processed_cross_numbers') or 0
        if total_cross > 0:
            return min(100, int((processed_cross / total_cross) * 100))
        total_rows = meta.get('total_rows') or 0
        processed_rows = meta.get('processed_rows') or 0
        if total_rows > 0:
            return min(100, int((processed_rows / total_rows) * 100))
        if obj.status == 'completed':
            return 100
        if obj.status == 'pending':
            return 0
        return 0

    def get_progress_autopiter(self, obj):
        meta = self._get_meta(obj)
        if 'progress_autopiter' in meta:
            return meta.get('progress_autopiter', 0)
        total = meta.get('total_autopiter') or 0
        processed = meta.get('processed_autopiter') or 0
        return min(100, int((processed / total) * 100)) if total > 0 else 0

    def get_progress_emex(self, obj):
        meta = self._get_meta(obj)
        if 'progress_emex' in meta:
            return meta.get('progress_emex', 0)
        total = meta.get('total_emex') or 0
        processed = meta.get('processed_emex') or 0
        return min(100, int((processed / total) * 100)) if total > 0 else 0

    def get_progress_armtek(self, obj):
        meta = self._get_meta(obj)
        if 'progress_armtek' in meta:
            return meta.get('progress_armtek', 0)
        total = meta.get('total_armtek') or 0
        processed = meta.get('processed_armtek') or 0
        return min(100, int((processed / total) * 100)) if total > 0 else 0

    def get_processed_autopiter(self, obj):
        return self._get_meta(obj).get('processed_autopiter', 0)

    def get_total_autopiter(self, obj):
        return self._get_meta(obj).get('total_autopiter', 0)

    def get_processed_emex(self, obj):
        return self._get_meta(obj).get('processed_emex', 0)

    def get_total_emex(self, obj):
        return self._get_meta(obj).get('total_emex', 0)

    def get_processed_armtek(self, obj):
        return self._get_meta(obj).get('processed_armtek', 0)

    def get_total_armtek(self, obj):
        return self._get_meta(obj).get('total_armtek', 0)


    def get_current_row(self, obj):
        meta = self._get_meta(obj)
        return meta.get('current_row') or 0

    def get_total_rows(self, obj):
        meta = self._get_meta(obj)
        return meta.get('total_rows') or 0

    def get_processed_rows(self, obj):
        meta = self._get_meta(obj)
        return meta.get('processed_rows') or 0

    def get_current_number(self, obj):
        meta = self._get_meta(obj)
        return meta.get('current_number') or ''

    def get_total_cross_numbers(self, obj):
        meta = self._get_meta(obj)
        return meta.get('total_cross_numbers') or 0

    def get_processed_cross_numbers(self, obj):
        meta = self._get_meta(obj)
        return meta.get('processed_cross_numbers') or 0
    
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