# Исправление проблем с таймаутами и Selenium

## Проблемы
1. **Selenium ошибки:** `user data directory is already in use`
2. **Таймауты задач:** `TimeLimitExceeded(3600)`
3. **Нестабильная работа:** Задачи падают после обработки 60 артикулов

## Решение

### 1. Исправление Selenium
- Убрана опция `--user-data-dir` полностью
- Удалены временные директории
- Добавлены дополнительные стабилизирующие опции

### 2. Оптимизация таймаутов
- Установлен лимит задачи: 30 минут (1800 сек)
- Мягкий лимит: 25 минут (1500 сек)
- Уменьшены таймауты для отдельных операций

### 3. Улучшение производительности
- Уменьшено количество потоков с 3 до 2
- Добавлена периодическая очистка процессов Chrome
- Оптимизирована обработка памяти

## Внесенные изменения

### 1. Исправленный Selenium
```python
def parse_armtek_selenium(artikul):
    """Парсинг через Selenium с оптимизацией ресурсов"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    # ... другие опции без --user-data-dir
```

### 2. Таймауты задач
```python
@shared_task(time_limit=1800, soft_time_limit=1500)  # 30 минут максимум, 25 минут мягкий лимит
def process_parsing_task(task_id):
    # Инициализация таймаута
    task._timeout_check = time.time()
    
    # Проверка таймаута в цикле
    if hasattr(task, '_timeout_check'):
        if time.time() - task._timeout_check > 1500:  # 25 минут
            log("Task timeout approaching, finishing up...")
            break
```

### 3. Оптимизация потоков
```python
# Уменьшено количество потоков
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
    # Уменьшены таймауты
    for fut in concurrent.futures.as_completed(fut_autopiter, timeout=20):
```

### 4. Периодическая очистка
```python
# Периодическая очистка процессов Chrome каждые 50 строк
if (index + 1) % 50 == 0:
    try:
        cleanup_chrome_processes()
        log("Performed periodic Chrome cleanup")
    except Exception as e:
        log(f"Error during Chrome cleanup: {str(e)}")
```

## Проверка исправления

### 1. Перезапуск сервисов
```bash
docker compose restart celery
```

### 2. Мониторинг логов
```bash
docker compose logs -f celery
```

### 3. Проверка процессов
```bash
docker exec -it autoparts-celery-1 ps aux | grep chrome
```

## Ожидаемые результаты

### После исправления
- Отсутствие ошибок `user data directory is already in use`
- Стабильная работа без таймаутов
- Успешная обработка больших файлов
- Эффективная очистка ресурсов

### Логи успешной работы
```
armtek: test123 → ['Brand1', 'Brand2']
autopiter: test123 → ['Brand3', 'Brand4']
emex: test123 → ['Brand5']
Performed periodic Chrome cleanup
```

## Дополнительные рекомендации

### 1. Мониторинг ресурсов
```bash
# Проверить использование памяти
docker stats autoparts-celery-1

# Проверить процессы
docker exec -it autoparts-celery-1 top
```

### 2. Настройка Celery
```yaml
# В docker-compose.yml
celery:
  command: celery -A backend worker -l info --concurrency=1 --max-tasks-per-child=5 --prefetch-multiplier=1
```

### 3. Очистка при проблемах
```bash
# Принудительная очистка
docker exec -it autoparts-celery-1 pkill -f chrome
docker exec -it autoparts-celery-1 pkill -f chromedriver

# Перезапуск
docker compose restart celery
```

## Если проблемы продолжаются

### 1. Уменьшение нагрузки
- Обрабатывать файлы меньшего размера
- Увеличить интервалы между запросами
- Использовать меньше потоков

### 2. Альтернативные методы
- Использовать HTTP парсинг вместо Selenium
- Разбить большие задачи на части
- Использовать очередь задач

### 3. Мониторинг
```bash
# Просмотр логов в реальном времени
docker compose logs -f celery

# Проверка статуса задач
docker exec -it autoparts-celery-1 celery -A backend inspect active
```

## Быстрое решение

Если нужно быстро исправить проблему:

```bash
# Остановить все
docker compose down

# Очистить процессы
docker system prune -f

# Перезапустить с новой конфигурацией
docker compose up -d

# Проверить логи
docker compose logs -f celery
```