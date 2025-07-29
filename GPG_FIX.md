# Исправление проблем с GPG подписями Ubuntu

## Проблема
```
Err:1 http://security.ubuntu.com/ubuntu jammy-security InRelease
  At least one invalid signature was encountered.
E: The repository 'http://security.ubuntu.com/ubuntu jammy-security InRelease' is not signed.
```

## Причина
Проблемы с GPG ключами репозиториев Ubuntu в Docker контейнере.

## Решение

### 1. Исправление GPG ключей
Добавлены команды для исправления GPG ключей Ubuntu:

```dockerfile
# Исправляем GPG ключи Ubuntu
RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32 871920D1991BC93F && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 871920D1991BC93F && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32

# Обновляем список пакетов с исправленными ключами
RUN apt-get update
```

### 2. Улучшенная структура Dockerfile
- Добавлены переменные окружения
- Разделена установка зависимостей на этапы
- Улучшена обработка ошибок

### 3. Оптимизация установки пакетов
```dockerfile
# Обновляем систему и устанавливаем зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        gnupg \
        software-properties-common \
        apt-transport-https \
        lsb-release && \
    rm -rf /var/lib/apt/lists/*
```

## Внесенные изменения

### 1. Исправление GPG ключей
```dockerfile
# Исправляем GPG ключи Ubuntu
RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32 871920D1991BC93F && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 871920D1991BC93F && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32

# Обновляем список пакетов с исправленными ключами
RUN apt-get update
```

### 2. Переменные окружения
```dockerfile
# Устанавливаем переменные окружения
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
```

### 3. Разделение установки зависимостей
```dockerfile
# Обновляем систему и устанавливаем зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        gnupg \
        software-properties-common \
        apt-transport-https \
        lsb-release && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем Python и зависимости
RUN apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-dev \
        build-essential \
        libpq-dev \
        postgresql-client \
        && rm -rf /var/lib/apt/lists/*
```

## Проверка исправления

### 1. Пересборка образа
```bash
docker compose build --no-cache backend
```

### 2. Проверка логов сборки
```bash
docker compose build backend
```

### 3. Запуск сервисов
```bash
docker compose up -d
```

## Ожидаемые результаты

### После исправления
- Отсутствие ошибок GPG подписей
- Успешная установка пакетов
- Стабильная сборка Docker образа

### Логи успешной сборки
```
Get:1 http://security.ubuntu.com/ubuntu jammy-security InRelease [129 kB]
Get:2 http://archive.ubuntu.com/ubuntu jammy InRelease [270 kB]
Reading package lists...
```

## Дополнительные рекомендации

### 1. Альтернативные ключи
Если проблемы продолжаются, можно попробовать другие ключи:
```bash
apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 871920D1991BC93F
apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32
apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 871920D1991BC93F
```

### 2. Обновление ключей
```bash
apt-get update && apt-get install -y ca-certificates
update-ca-certificates
```

### 3. Проверка ключей
```bash
apt-key list
```

## Если проблемы продолжаются

### 1. Очистка кеша
```bash
docker system prune -a
docker builder prune
```

### 2. Использование другого базового образа
```dockerfile
FROM ubuntu:22.04
# или
FROM python:3.10-slim
```

### 3. Ручное исправление
```bash
# Внутри контейнера
apt-get update
apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32
apt-get update
```

## Быстрое решение

Если нужно быстро исправить проблему:

```bash
# Остановить все
docker compose down

# Очистить образы
docker system prune -a

# Пересобрать с новой конфигурацией
docker compose build --no-cache

# Запустить
docker compose up -d
```