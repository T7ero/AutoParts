# Инструкция по настройке Docker и решению проблем

## Проблема с Docker Desktop

Если вы видите ошибку:
```
error during connect: Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/v1.49/containers/json?all=1&filters=%7B%22label%22%3A%7B%22com.docker.compose.config-hash%22%3Atrue%2C%22com.docker.compose.oneoff%3DFalse%22%3Atrue%2C%22com.docker.compose.project%3Dautoparts%22%3Atrue%7D%7D": open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

Это означает, что Docker Desktop не запущен.

## Решение

### 1. Запустите Docker Desktop
- Найдите Docker Desktop в меню Пуск
- Запустите приложение
- Дождитесь полной загрузки (значок в трее станет зеленым)

### 2. Проверьте статус Docker
```powershell
docker --version
docker compose version
```

### 3. Попробуйте собрать проект снова
```powershell
cd C:\Users\Tima\Desktop\AutoParts
docker compose build --no-cache
```

## Исправление проблем с GPG

### Вариант 1: Использовать Ubuntu-based Dockerfile (рекомендуется)

Если у вас проблемы с GPG ключами в Debian, используйте Ubuntu-based Dockerfile:

```powershell
cd backend
Move-Item Dockerfile Dockerfile.debian
Move-Item Dockerfile.ubuntu Dockerfile
cd ..
docker compose build --no-cache
```

### Вариант 2: Использовать простой Dockerfile

```powershell
cd backend
Move-Item Dockerfile Dockerfile.debian
Move-Item Dockerfile.simple Dockerfile
cd ..
docker compose build --no-cache
```

## Доступные варианты Dockerfile

### 1. Dockerfile.ubuntu (Ubuntu 22.04) - РЕКОМЕНДУЕТСЯ
- Более стабильный базовый образ
- Меньше проблем с GPG ключами
- Полная поддержка Chrome

### 2. Dockerfile.simple (Минимальный)
- Только необходимые зависимости
- Установка Chrome через официальный репозиторий
- Быстрая сборка

### 3. Dockerfile.debian (Debian slim)
- Обновленный основной файл
- Раздельная установка зависимостей
- Оптимизированная структура

## Пошаговая инструкция

### Шаг 1: Запустите Docker Desktop
1. Откройте Docker Desktop
2. Дождитесь полной загрузки
3. Проверьте, что значок в трее зеленый

### Шаг 2: Переключитесь на Ubuntu-based Dockerfile
```powershell
cd C:\Users\Tima\Desktop\AutoParts\backend
Move-Item Dockerfile Dockerfile.debian
Move-Item Dockerfile.ubuntu Dockerfile
cd ..
```

### Шаг 3: Соберите проект
```powershell
docker compose build --no-cache
```

### Шаг 4: Запустите проект
```powershell
docker compose up -d
```

### Шаг 5: Проверьте логи
```powershell
docker compose logs
```

## Проверка работоспособности

### Проверка сборки
```powershell
docker compose build --no-cache
```

### Проверка запуска
```powershell
docker compose up -d
docker compose logs
```

### Проверка Selenium
```powershell
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

### Для Windows
1. Убедитесь, что Docker Desktop запущен
2. Проверьте, что WSL2 включен
3. Убедитесь, что у вас достаточно места на диске

### Для продакшена
1. Используйте фиксированные версии образов
2. Настройте локальный репозиторий пакетов
3. Используйте multi-stage builds для оптимизации

### Для разработки
1. Используйте volume mounts для быстрой разработки
2. Настройте hot reload для изменений кода
3. Используйте Docker Compose override для локальных настроек 