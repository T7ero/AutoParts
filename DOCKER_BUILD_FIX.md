# Исправление проблем с Docker Build

## Проблема
Ошибка GPG при сборке Docker образа:
```
Err:1 http://deb.debian.org/debian bookworm InRelease
  At least one invalid signature was encountered.
```

## Решение

### Вариант 1: Использовать Ubuntu-based Dockerfile (рекомендуется)

Если проблемы с Debian продолжаются, используйте Ubuntu-based Dockerfile:

```bash
cd backend
mv Dockerfile Dockerfile.debian
mv Dockerfile.ubuntu Dockerfile
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Вариант 2: Использовать простой Dockerfile

Если нужен минимальный набор зависимостей:

```bash
cd backend
mv Dockerfile Dockerfile.debian
mv Dockerfile.simple Dockerfile
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Вариант 3: Использовать исправленный Debian Dockerfile

Попробуйте обновленный основной Dockerfile:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Вариант 4: Ручное исправление

Если проблемы продолжаются:

1. Очистить Docker кеш:
```bash
docker system prune -a
```

2. Обновить Docker:
```bash
# Для Ubuntu/Debian
sudo apt update && sudo apt upgrade docker.io

# Для CentOS/RHEL
sudo yum update docker
```

3. Перезапустить Docker:
```bash
sudo systemctl restart docker
```

4. Попробовать другой базовый образ:
```bash
# В Dockerfile заменить
FROM python:3.10-slim
# на
FROM python:3.10-bullseye
```

## Доступные варианты Dockerfile

### 1. Dockerfile.ubuntu (Ubuntu 22.04)
- Более стабильный базовый образ
- Меньше проблем с GPG ключами
- Полная поддержка Chrome

### 2. Dockerfile.simple (Минимальный)
- Только необходимые зависимости
- Установка Chrome через официальный репозиторий
- Быстрая сборка

### 3. Dockerfile (Debian slim)
- Обновленный основной файл
- Раздельная установка зависимостей
- Оптимизированная структура

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
docker exec -it autoparts-celery-1 google-chrome --version
docker exec -it autoparts-celery-1 chromedriver --version
```

## Ожидаемые результаты

### После исправления
- Успешная сборка Docker образа
- Стабильная работа Selenium
- Корректная установка Chrome и ChromeDriver

### Если проблемы продолжаются
1. Проверьте интернет-соединение
2. Попробуйте использовать VPN
3. Обратитесь к системному администратору

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
# Использовать Ubuntu-based образ
cd backend
mv Dockerfile Dockerfile.debian
mv Dockerfile.ubuntu Dockerfile
docker compose down
docker compose build --no-cache
docker compose up -d
``` 