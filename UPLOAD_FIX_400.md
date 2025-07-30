# Исправление ошибки 400 при загрузке файлов

## Проблема
При попытке загрузить Excel файл через веб-интерфейс возникает ошибка 400 Bad Request.

## Причина
Проблемы с обработкой файлов в Django API и валидацией.

## Внесенные исправления

### 1. Улучшена обработка ошибок в ParsingTaskViewSet
```python
# backend/api/views.py
def create(self, request, *args, **kwargs):
    try:
        # Проверяем наличие файла
        if 'file' not in request.FILES:
            return Response(
                {'error': 'Файл не был загружен'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        
        # Проверяем тип файла
        if not file.name.endswith('.xlsx'):
            return Response(
                {'error': 'Поддерживаются только файлы Excel (.xlsx)'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Проверяем размер файла
        if file.size > 10 * 1024 * 1024:  # 10MB
            return Response(
                {'error': 'Размер файла не должен превышать 10MB'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Создаем задачу
        task = ParsingTask.objects.create(
            user=request.user,
            file=file,
            status='pending'
        )
        
        # Запускаем задачу парсинга
        process_parsing_task.delay(task.id)
        
        # Возвращаем данные задачи
        serializer = self.get_serializer(task)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        import traceback
        print(f"Ошибка при создании задачи: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return Response(
            {'error': f'Ошибка при создании задачи: {str(e)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
```

### 2. Улучшен сериализатор ParsingTaskSerializer
```python
# backend/api/serializers.py
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
```

### 3. Добавлены настройки для загрузки файлов
```python
# backend/backend/settings.py
# Настройки для загрузки файлов
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_TEMP_DIR = os.path.join(BASE_DIR, 'media', 'temp')

# Дополнительные настройки для отладки
FILE_UPLOAD_HANDLERS = [
    'django.core.files.uploadhandler.MemoryFileUploadHandler',
    'django.core.files.uploadhandler.TemporaryFileUploadHandler',
]
```

## Проверка исправления

### 1. Автоматическое исправление
```bash
chmod +x fix_upload.sh
./fix_upload.sh
```

### 2. Ручное исправление
```bash
# Остановить сервисы
docker compose down

# Пересобрать образы
docker compose build --no-cache backend

# Запустить сервисы
docker compose up -d
```

### 3. Тестирование загрузки
```bash
python3 test_upload_fix.py
```

### 4. Проверка через веб-интерфейс
1. Откройте http://localhost
2. Войдите с логином `admin` и паролем `admin`
3. Перейдите на страницу "Загрузка"
4. Выберите Excel файл (.xlsx)
5. Нажмите "Начать обработку"

## Ожидаемые результаты

### После исправления
- Успешная загрузка Excel файлов
- Корректная валидация файлов
- Правильные сообщения об ошибках
- Создание задач парсинга

### Логи успешной загрузки
```
backend-1   | 2025-07-30 09:56:34,824 INFO     POST /api/parsing-tasks/ 201 1234
nginx-1     | 2.63.200.228 - - [30/Jul/2025:09:56:34 +0000] "POST /api/parsing-tasks/ HTTP/1.1" 201 1234
```

## Дополнительные улучшения

### 1. Тестовый скрипт
Создан `test_upload_fix.py` для автоматического тестирования загрузки файлов.

### 2. Улучшенная обработка ошибок
- Более информативные сообщения об ошибках
- Отладочная информация в логах
- Правильная валидация файлов

### 3. Оптимизация производительности
- Увеличены лимиты загрузки файлов
- Настроены временные директории
- Улучшена обработка больших файлов

## Если проблемы продолжаются

### 1. Проверка логов
```bash
docker compose logs backend
```

### 2. Проверка прав доступа
```bash
docker compose exec backend ls -la media/
```

### 3. Ручное тестирование API
```bash
curl -X POST http://localhost/api/auth/token/ \
  -d "username=admin&password=admin"
```

### 4. Очистка и перезапуск
```bash
docker compose down
docker system prune -f
./fix_upload.sh
``` 