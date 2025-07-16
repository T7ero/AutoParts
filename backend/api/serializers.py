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