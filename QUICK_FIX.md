# Быстрое исправление ошибок gosu

## Проблема
```
/usr/local/bin/entrypoint.sh: line 13: exec: gosu: not found
```

## Решение

### 1. Остановите систему
```bash
docker compose down
```

### 2. Пересоберите образы
```bash
docker compose build --no-cache
```

### 3. Запустите систему
```bash
docker compose up -d
```

### 4. Проверьте статус
```bash
docker compose ps
```

### 5. Проверьте логи
```bash
docker compose logs backend
docker compose logs celery
```

## Альтернативное решение

Если проблема с gosu остается:

### 1. Используйте упрощенный entrypoint
Система уже настроена для использования `entrypoint_simple.sh` который не требует gosu.

### 2. Ручная сборка
```bash
# Остановите все
docker compose down

# Удалите старые образы
docker system prune -f

# Соберите образы по отдельности
docker build -f backend/Dockerfile.alternative -t autoparts-backend ./backend

# Запустите систему
docker compose up -d
```

## Проверка работы

### 1. Проверьте доступность
```bash
curl http://localhost
```

### 2. Проверьте API
```bash
curl http://localhost/api/parsing-tasks/
```

### 3. Проверьте логи
```bash
docker compose logs -f
```

## Данные для входа

- **URL:** http://localhost
- **Логин:** admin
- **Пароль:** admin

## Полезные команды

```bash
# Просмотр всех контейнеров
docker compose ps

# Просмотр логов конкретного сервиса
docker compose logs backend
docker compose logs celery
docker compose logs db
docker compose logs redis

# Перезапуск конкретного сервиса
docker compose restart backend
docker compose restart celery

# Полная перезагрузка
docker compose down
docker compose up -d --build
```

## Если ничего не помогает

```bash
# Полная очистка
docker compose down
docker system prune -a -f
docker volume prune -f

# Пересборка с нуля
docker compose up -d --build

# Проверка
docker compose ps
docker compose logs
``` 