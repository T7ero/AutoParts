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
    class Meta:
        model = ParsingTask
        fields = ['id', 'user', 'file', 'status', 'progress', 'result_file', 'result_files', 'log',
                 'created_at', 'updated_at', 'error_message']
        read_only_fields = ['user', 'status', 'progress', 'result_file', 'result_files', 'log', 'error_message']
    
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