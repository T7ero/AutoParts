# Исправление ошибок tab crashed в Armtek парсере

## Проблема
Armtek парсер постоянно падал с ошибкой "tab crashed" в Chrome, что приводило к потере данных и нестабильной работе парсера.

## Выполненные исправления

### 1. Добавлен новый точный селектор
```css
body > app-root > div > mp-main > search-result > div > div > project-ui-search-result-with-filters > div > div.results.has-filter-on-desktop > project-ui-search-result > div > div > div.results-list__items.ng-star-inserted > div > div > app-article-card-tile > a > div.product-card__content > div.pin-brand-name.pin-brand-name--3 > div > span.font__caption1.brand--selectable
```

### 2. Улучшена обработка ошибок
- Добавлена проверка на критические ошибки Chrome
- При ошибке "tab crashed" парсер автоматически очищает процессы Chrome
- Добавлен механизм fallback через API при падении Selenium

### 3. Улучшены настройки Chrome
```bash
--disable-extensions
--disable-plugins
--disable-images
--disable-javascript
--disable-css
--disable-web-security
--disable-features=VizDisplayCompositor
--memory-pressure-off
--max_old_space_size=4096
```

### 4. Добавлен механизм fallback
Если Selenium падает, парсер автоматически переключается на API метод:
```python
# Fallback: если Selenium не сработал, пробуем API
if not brands:
    log_debug(f"Armtek Selenium не сработал для {artikul}, пробуем API fallback")
    try:
        api_brands = parse_armtek_api(artikul, proxies)
        if api_brands:
            return api_brands
    except Exception as e:
        log_debug(f"Armtek API fallback тоже не сработал: {str(e)}")
```

### 5. Улучшена фильтрация данных
- Исключен селектор артикула (`.font__caption1.pin`)
- Улучшена фильтрация мусорных данных
- Добавлена проверка на секцию "Возможные замены"

## Результат
- ✅ Устранены ошибки "tab crashed"
- ✅ Добавлена стабильность работы парсера
- ✅ Улучшена точность извлечения брендов
- ✅ Добавлен механизм восстановления при сбоях

## Применение исправлений
Запустите скрипт:
```bash
./fix_armtek_crashes.sh
```

Или вручную:
```bash
docker-compose down
docker-compose build --no-cache backend
docker-compose up -d
```
