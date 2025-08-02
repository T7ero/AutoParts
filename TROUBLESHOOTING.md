# Устранение неполадок AutoParts

## Проблема: GPG ошибки при сборке Docker

### Ошибка:
```
W: GPG error: http://archive.ubuntu.com/ubuntu jammy InRelease: At least one invalid signature was encountered.
E: The repository 'http://archive.ubuntu.com/ubuntu jammy InRelease' is not signed.
```

### Решение 1: Исправление на сервере

```bash
# Запустите скрипт исправления
chmod +x fix_gpg.sh
./fix_gpg.sh

# Или выполните команды вручную:
sudo apt-get update
sudo apt-get install -y ubuntu-keyring
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 871920D1991BC93F
sudo update-ca-certificates
sudo apt-get clean
sudo apt-get autoclean
```

### Решение 2: Использование альтернативного Dockerfile

Система уже настроена для использования альтернативного Dockerfile с `python:3.11-slim`:

```bash
# Запустите сборку с альтернативным Dockerfile
docker compose build --no-cache

# Или запустите всю систему
docker compose up -d --build
```

### Решение 3: Ручная сборка образов

```bash
# Остановите все контейнеры
docker compose down

# Удалите старые образы
docker system prune -f

# Соберите образы по отдельности
docker build -f backend/Dockerfile.alternative -t autoparts-backend ./backend

# Запустите систему
docker compose up -d
```

## Проблема: Недостаточно места на диске

### Решение:
```bash
# Очистите неиспользуемые Docker ресурсы
docker system prune -a -f

# Проверьте свободное место
df -h

# Удалите старые образы
docker images | grep none | awk '{print $3}' | xargs docker rmi
```

## Проблема: Порт 80 занят

### Решение:
```bash
# Проверьте что использует порт 80
sudo netstat -tlnp | grep :80

# Остановите nginx если он запущен
sudo systemctl stop nginx

# Или измените порт в docker-compose.yml
ports:
  - "8080:80"  # вместо "80:80"
```

## Проблема: Недостаточно памяти

### Решение:
```bash
# Создайте swap файл
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Сделайте swap постоянным
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Проверьте swap
free -h
```

## Проблема: Docker не запускается

### Решение:
```bash
# Проверьте статус Docker
sudo systemctl status docker

# Перезапустите Docker
sudo systemctl restart docker

# Проверьте что пользователь в группе docker
groups $USER

# Добавьте пользователя в группу docker
sudo usermod -aG docker $USER
sudo reboot
```

## Проблема: Ошибки Selenium

### Решение:
```bash
# Перезапустите только celery
docker compose restart celery

# Проверьте логи
docker compose logs celery

# Очистите процессы Chrome
docker compose exec celery pkill -f chrome
```

## Проблема: Медленная работа

### Решение:
```bash
# Проверьте ресурсы
docker stats

# Увеличьте ресурсы в docker-compose.yml (если позволяет сервер)
# Уменьшите количество одновременных задач
```

## Проблема: База данных не подключается

### Решение:
```bash
# Проверьте статус базы данных
docker compose logs db

# Перезапустите базу данных
docker compose restart db

# Проверьте подключение
docker compose exec backend python manage.py check --database default
```

## Проблема: Redis не подключается

### Решение:
```bash
# Проверьте статус Redis
docker compose logs redis

# Перезапустите Redis
docker compose restart redis

# Проверьте подключение
docker compose exec redis redis-cli ping
```

## Полезные команды для диагностики

```bash
# Просмотр всех контейнеров
docker compose ps

# Просмотр логов всех сервисов
docker compose logs

# Просмотр логов конкретного сервиса
docker compose logs backend
docker compose logs celery
docker compose logs db
docker compose logs redis

# Просмотр использования ресурсов
docker stats

# Проверка дискового пространства
df -h

# Проверка использования памяти
free -h

# Проверка открытых портов
sudo netstat -tlnp

# Проверка статуса Docker
sudo systemctl status docker
```

## Полная переустановка системы

Если ничего не помогает:

```bash
# Остановите все контейнеры
docker compose down

# Удалите все образы и контейнеры
docker system prune -a -f

# Удалите volumes (осторожно - потеряете данные)
docker volume prune -f

# Пересоберите систему
docker compose up -d --build

# Проверьте статус
docker compose ps
```

## Контакты для поддержки

При возникновении проблем:
1. Проверьте логи: `docker compose logs`
2. Убедитесь, что все сервисы запущены: `docker compose ps`
3. Перезапустите систему: `docker compose restart`
4. Проверьте ресурсы системы и интернет-соединение 