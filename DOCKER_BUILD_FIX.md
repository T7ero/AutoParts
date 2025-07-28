# Исправление проблем с Docker Build

## Проблема
Ошибка GPG при сборке Docker образа:
```
Err:1 http://deb.debian.org/debian bookworm InRelease
  At least one invalid signature was encountered.
```

## Решение

### Вариант 1: Использовать исправленный Dockerfile (рекомендуется)

Используйте обновленный `backend/Dockerfile` который уже исправлен:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Вариант 2: Использовать альтернативный Dockerfile

Если основной Dockerfile все еще вызывает проблемы, используйте альтернативный:

1. Переименуйте файлы:
```bash
cd backend
mv Dockerfile Dockerfile.backup
mv Dockerfile.alternative Dockerfile
```

2. Пересоберите контейнеры:
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Вариант 3: Ручное исправление

Если проблемы продолжаются, можно попробовать:

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

## Внесенные изменения

### 1. Упрощенный Dockerfile
- Убраны проблемные GPG ключи
- Упрощена установка зависимостей
- Использование стандартных репозиториев

### 2. Альтернативный Dockerfile
- Установка Google Chrome через официальный репозиторий
- Автоматическая установка ChromeDriver
- Более надежная конфигурация

### 3. Обновленный парсер
- Поддержка Google Chrome вместо Chromium
- Улучшенные опции для стабильности
- Скрытие автоматизации

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