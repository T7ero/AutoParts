# Исправления проблем с Selenium

## Проблемы, которые были исправлены

### 1. Конфликты сессий Chrome
**Проблема**: `session not created: probably user data directory is already in use`

**Решение**:
- Добавлены уникальные временные директории для каждого запроса
- Использование UUID для создания уникальных имен директорий
- Автоматическая очистка временных директорий после использования

### 2. Таймауты и зависания
**Проблема**: `timeout: Timed out receiving message from renderer: 20.000`

**Решение**:
- Уменьшено время ожидания с 30с до 20с
- Добавлены дополнительные опции Chrome для стабильности
- Принудительная очистка зависших процессов Chrome

### 3. Утечки памяти
**Проблема**: Накопление процессов Chrome в памяти

**Решение**:
- Периодическая очистка процессов каждые 50 строк
- Финальная очистка после завершения задачи
- Уменьшение количества потоков Selenium до 1

## Внесенные изменения

### 1. Оптимизация Selenium (`backend/api/autopiter_parser.py`)
```python
# Уникальные директории для каждого запроса
temp_dir = tempfile.mkdtemp(prefix=f'chrome_{uuid.uuid4().hex[:8]}_')

# Дополнительные опции Chrome
options.add_argument('--disable-background-timer-throttling')
options.add_argument('--disable-backgrounding-occluded-windows')
options.add_argument('--disable-renderer-backgrounding')

# Очистка процессов
cleanup_chrome_processes()
```

### 2. Улучшенная обработка ошибок (`backend/api/tasks.py`)
```python
# Повторные попытки для Selenium
max_retries = 2
for attempt in range(max_retries):
    try:
        brands = get_brands_by_artikul_armtek(num)
        return results
    except Exception as e:
        if attempt < max_retries - 1:
            time.sleep(2)  # Ждем перед повторной попыткой
```

### 3. Периодическая очистка
```python
# Каждые 50 строк
if (index + 1) % 50 == 0:
    cleanup_chrome_processes()
```

### 4. Обновленный Dockerfile
- Добавлены зависимости для Chrome
- Настроен Xvfb для headless режима
- Создан пользователь chrome для безопасности

## Как применить исправления

### 1. Пересборка контейнеров
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### 2. Проверка логов
```bash
docker compose logs celery
```

### 3. Мониторинг процессов
```bash
# Проверка процессов Chrome
docker exec -it autoparts-celery-1 ps aux | grep chrome

# Очистка процессов вручную (если нужно)
docker exec -it autoparts-celery-1 pkill -f chrome
```

## Ожидаемые результаты

### До исправлений
- Selenium зависал после нескольких запросов
- Ошибки `session not created`
- Таймауты `Timed out receiving message from renderer`
- Утечки памяти из-за накопления процессов

### После исправлений
- Стабильная работа Selenium
- Автоматическая очистка ресурсов
- Повторные попытки при ошибках
- Контролируемое использование памяти

## Дополнительные рекомендации

### Для очень больших файлов
1. **Разбивайте файлы** на части по 100-200 артикулов
2. **Используйте очередь** - загружайте файлы последовательно
3. **Мониторинг** - следите за логами и ресурсами

### Настройка для продакшена
1. **Увеличьте ресурсы сервера** до 4-8 ГБ RAM
2. **Настройте мониторинг** с автоматическими уведомлениями
3. **Добавьте кеширование** результатов парсинга
4. **Используйте CDN** для статических файлов

## Устранение проблем

### Если Selenium все еще зависает
1. Проверьте логи: `docker compose logs celery`
2. Увеличьте ресурсы сервера
3. Разбейте файл на меньшие части
4. Запустите мониторинг ресурсов

### Если медленная обработка
1. Это нормально после оптимизации
2. Увеличьте количество потоков (но не более 1 для Selenium)
3. Рассмотрите возможность увеличения ресурсов сервера 