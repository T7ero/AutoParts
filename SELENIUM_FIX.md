# Исправление проблем с Selenium

## Проблема
```
Selenium error: Message: session not created: probably user data directory is already in use, please specify a unique value for --user-data-dir argument, or don't use --user-data-dir
```

## Причина
Конфликт с `--user-data-dir` при создании сессий Chrome в многопоточной среде.

## Решение

### 1. Убрать --user-data-dir
Удалена опция `--user-data-dir` из ChromeOptions, которая вызывала конфликты.

### 2. Улучшена очистка процессов
Добавлена более эффективная очистка процессов Chrome:
- Очистка всех вариантов имен процессов
- Дополнительная очистка через `ps` и `kill`
- Увеличенное время ожидания

### 3. Добавлены дополнительные опции Chrome
Добавлены опции для стабильности:
- `--disable-dev-shm-usage`
- `--disable-application-cache`
- `--disk-cache-size=0`
- `--media-cache-size=0`
- И другие оптимизации

### 4. Альтернативный метод парсинга
Добавлен метод `parse_armtek_http()` для парсинга без Selenium.

## Внесенные изменения

### 1. Удалена проблемная опция
```python
# Удалено:
# options.add_argument(f'--user-data-dir={temp_dir}')
```

### 2. Улучшена очистка процессов
```python
def cleanup_chrome_processes():
    try:
        subprocess.run(['pkill', '-f', 'chrome'], capture_output=True)
        subprocess.run(['pkill', '-f', 'chromedriver'], capture_output=True)
        subprocess.run(['pkill', '-f', 'google-chrome'], capture_output=True)
        subprocess.run(['pkill', '-f', 'chromium'], capture_output=True)
        
        # Дополнительная очистка через ps и kill
        try:
            ps_output = subprocess.check_output(['ps', 'aux'], text=True)
            for line in ps_output.split('\n'):
                if 'chrome' in line.lower() or 'chromedriver' in line.lower():
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        try:
                            subprocess.run(['kill', '-9', pid], capture_output=True)
                        except:
                            pass
        except:
            pass
        
        time.sleep(2)  # Увеличено время ожидания
    except Exception as e:
        log_debug(f"Error cleaning up Chrome processes: {e}")
```

### 3. Добавлены стабилизирующие опции
```python
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-application-cache')
options.add_argument('--disable-offline-load-stale-cache')
options.add_argument('--disk-cache-size=0')
options.add_argument('--media-cache-size=0')
options.add_argument('--disable-background-networking')
options.add_argument('--disable-sync')
options.add_argument('--disable-translate')
options.add_argument('--disable-default-apps')
# ... и другие
```

### 4. Альтернативный HTTP парсинг
```python
def parse_armtek_http(artikul, proxies=None):
    """Парсинг Armtek через простой HTTP запрос"""
    url = f"https://armtek.ru/search?text={quote(artikul)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            brands = set()
            
            # Ищем бренды в различных селекторах
            selectors = [
                'span.font__body2.brand--selecting',
                '.product-card .brand-name',
                '.product-card__brand',
                '[itemprop="brand"]',
                '.catalog-item__brand',
                '.brand-name',
                '.product-brand',
                'span[data-brand]',
                '.item-brand'
            ]
            
            for selector in selectors:
                for tag in soup.select(selector):
                    brand = tag.get_text(strip=True)
                    if brand and len(brand) > 2 and not brand.isdigit():
                        brands.add(brand)
            
            return sorted(brands) if brands else []
            
    except Exception as e:
        log_debug(f"HTTP parsing error: {str(e)}")
        return []
```

## Проверка исправления

### 1. Проверка логов
```bash
docker compose logs celery
```

### 2. Тестирование парсинга
```bash
# Проверить работу парсера
curl -X POST http://localhost/api/parse/ \
  -H "Content-Type: application/json" \
  -d '{"artikul": "test123"}'
```

### 3. Мониторинг процессов
```bash
# Проверить процессы Chrome
docker exec -it autoparts-celery-1 ps aux | grep chrome
```

## Ожидаемые результаты

### После исправления
- Отсутствие ошибок `user data directory is already in use`
- Стабильная работа Selenium
- Успешный парсинг Armtek
- Эффективная очистка процессов

### Логи успешной работы
```
armtek: test123 → ['Brand1', 'Brand2', 'Brand3']
```

## Если проблемы продолжаются

### 1. Принудительная очистка
```bash
docker exec -it autoparts-celery-1 pkill -f chrome
docker exec -it autoparts-celery-1 pkill -f chromedriver
```

### 2. Перезапуск сервисов
```bash
docker compose restart celery
```

### 3. Использование HTTP парсинга
Если Selenium продолжает работать нестабильно, система автоматически переключится на HTTP парсинг.

## Дополнительные рекомендации

### 1. Мониторинг ресурсов
```bash
# Проверить использование памяти
docker stats autoparts-celery-1
```

### 2. Логирование
```bash
# Просмотр логов в реальном времени
docker compose logs -f celery
```

### 3. Настройка Celery
Убедитесь, что Celery настроен с правильными лимитами:
```python
# В docker-compose.yml
celery:
  command: celery -A backend worker -l info --concurrency=1 --max-tasks-per-child=10 --prefetch-multiplier=1
```

## Быстрое решение

Если нужно быстро исправить проблему:

```bash
# Перезапустить Celery
docker compose restart celery

# Проверить логи
docker compose logs -f celery
``` 