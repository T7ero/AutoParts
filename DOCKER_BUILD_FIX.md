# Исправление проблем с Docker Build

## Проблема
Ошибка при установке ChromeDriver:
```
unzip: cannot find or open chromedriver_linux64.zip
```

## Быстрое решение

### Вариант 1: Использовать фиксированную версию ChromeDriver
```bash
cd backend
mv Dockerfile Dockerfile.google
mv Dockerfile.fixed Dockerfile
cd ..
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Вариант 2: Использовать Chromium
```bash
cd backend
mv Dockerfile Dockerfile.google
mv Dockerfile.chromium Dockerfile
cd ..
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Вариант 3: Использовать исправленный основной Dockerfile
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

## Решение

### Вариант 1: Использовать исправленный Dockerfile (рекомендуется)

Используйте обновленный `backend/Dockerfile` который уже исправлен:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Вариант 2: Использовать Chromium-based Dockerfile

Если проблемы с Google Chrome продолжаются, используйте Chromium:

```bash
cd backend
mv Dockerfile Dockerfile.google
mv Dockerfile.chromium Dockerfile
cd ..
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Вариант 3: Использовать фиксированную версию ChromeDriver

```bash
cd backend
mv Dockerfile Dockerfile.google
mv Dockerfile.fixed Dockerfile
cd ..
docker compose down
docker compose build --no-cache
docker compose up -d
```

## Доступные варианты Dockerfile

### 1. Dockerfile (Google Chrome) - РЕКОМЕНДУЕТСЯ
- Исправлен с добавлением `gnupg`
- Использует современный способ установки GPG ключей
- Улучшенная установка ChromeDriver с отладкой
- Полная поддержка Google Chrome

### 2. Dockerfile.fixed (Фиксированная версия)
- Использует фиксированную версию ChromeDriver (120.0.6099.109)
- Стабильная и предсказуемая сборка
- Не зависит от динамического определения версии

### 3. Dockerfile.chromium (Chromium)
- Использует Chromium вместо Google Chrome
- Меньше зависимостей
- Более стабильная установка

### 4. Dockerfile.simple (Минимальный)
- Только необходимые зависимости
- Установка Chrome через официальный репозиторий
- Быстрая сборка

## Внесенные исправления

### 1. Добавлен gnupg
```dockerfile
RUN apt-get install -y --no-install-recommends \
    # ... другие пакеты ...
    gnupg \
    # ... остальные пакеты ...
```

### 2. Современный способ установки GPG ключей
```dockerfile
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list
```

### 3. Улучшенная установка ChromeDriver
```dockerfile
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | awk -F'.' '{print $1}') && \
    echo "Chrome version: $CHROME_VERSION" && \
    LATEST_RELEASE=$(wget -qO- "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION") && \
    echo "Latest ChromeDriver release: $LATEST_RELEASE" && \
    wget -q "https://chromedriver.storage.googleapis.com/$LATEST_RELEASE/chromedriver_linux64.zip" -O chromedriver.zip && \
    ls -la chromedriver.zip && \
    unzip chromedriver.zip && \
    mv chromedriver /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver && \
    rm chromedriver.zip && \
    chromedriver --version
```

### 4. Фиксированная версия ChromeDriver
```dockerfile
RUN wget -q "https://chromedriver.storage.googleapis.com/120.0.6099.109/chromedriver_linux64.zip" -O chromedriver.zip && \
    unzip chromedriver.zip && \
    mv chromedriver /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver && \
    rm chromedriver.zip && \
    chromedriver --version
```

### 5. Обновленный парсер
- Поддержка как Google Chrome, так и Chromium
- Автоматическое определение ChromeDriver
- Улучшенная обработка ошибок

## Проверка работоспособности

### 1. Проверка сборки
```bash
docker compose build --no-cache
```

### 2. Проверка запуска
```bash
docker compose up -d
docker compose logs
```

### 3. Проверка Selenium
```bash
# Для Google Chrome
docker exec -it autoparts-celery-1 google-chrome --version
docker exec -it autoparts-celery-1 chromedriver --version

# Для Chromium
docker exec -it autoparts-celery-1 chromium-browser --version
docker exec -it autoparts-celery-1 chromedriver --version
```

## Ожидаемые результаты

### После исправления
- Успешная сборка Docker образа
- Стабильная работа Selenium
- Корректная установка Chrome/Chromium и ChromeDriver

### Если проблемы продолжаются
1. Используйте фиксированную версию ChromeDriver
2. Используйте Chromium-based Dockerfile
3. Проверьте интернет-соединение
4. Попробуйте использовать VPN

## Дополнительные рекомендации

### Для продакшена
1. Используйте фиксированные версии образов
2. Настройте локальный репозиторий пакетов
3. Используйте multi-stage builds для оптимизации

### Для разработки
1. Используйте volume mounts для быстрой разработки
2. Настройте hot reload для изменений кода
3. Используйте Docker Compose override для локальных настроек

## Быстрое решение

Если нужно быстро запустить проект:

```bash
# Использовать фиксированную версию ChromeDriver
cd backend
mv Dockerfile Dockerfile.google
mv Dockerfile.fixed Dockerfile
cd ..
docker compose down
docker compose build --no-cache
docker compose up -d
``` 