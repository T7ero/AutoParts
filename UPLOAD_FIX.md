# Исправление ошибки 400 при загрузке файлов

## Проблема
При попытке загрузить Excel файл через веб-интерфейс возникает ошибка 400 Bad Request.

## Причина
Проблемы с валидацией файлов и обработкой запросов в API.

## Внесенные исправления

### 1. Исправлен сериализатор ParsingTaskSerializer
```python
# backend/api/serializers.py
class ParsingTaskSerializer(serializers.ModelSerializer):
    def validate_file(self, value):
        """Валидация загружаемого файла"""
        if not value:
            raise serializers.ValidationError("Файл не был загружен")
        
        if not value.name.endswith('.xlsx'):
            raise serializers.ValidationError("Поддерживаются только файлы Excel (.xlsx)")
        
        if value.size > 10 * 1024 * 1024:  # 10MB
            raise serializers.ValidationError("Размер файла не должен превышать 10MB")
        
        return value
```

### 2. Улучшен ParsingTaskViewSet
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
        return Response(
            {'error': f'Ошибка при создании задачи: {str(e)}'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
```

### 3. Добавлены настройки для загрузки файлов
```python
# backend/backend/settings.py
# Настройки для загрузки файлов
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_TEMP_DIR = os.path.join(BASE_DIR, 'media', 'temp')

# Создаем директории если их нет
os.makedirs(MEDIA_ROOT, exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'uploads'), exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'results'), exist_ok=True)
os.makedirs(FILE_UPLOAD_TEMP_DIR, exist_ok=True)
```

## Проверка исправления

### 1. Перезапуск сервисов
```bash
docker compose down
docker compose up -d
```

### 2. Тестирование загрузки
```bash
python test_upload.py
```

### 3. Проверка через веб-интерфейс
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
backend-1   | 2025-07-30 06:22:49,257 INFO     POST /api/parsing-tasks/ 201 1234
nginx-1     | 2.63.200.228 - - [30/Jul/2025:06:22:49 +0000] "POST /api/parsing-tasks/ HTTP/1.1" 201 1234
```

## Дополнительные улучшения

### 1. Тестовый скрипт
Создан `test_upload.py` для автоматического тестирования загрузки файлов.

### 2. Улучшенная обработка ошибок
- Более информативные сообщения об ошибках
- Проверка типа файла
- Проверка размера файла
- Создание необходимых директорий

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
docker compose up -d
``` 