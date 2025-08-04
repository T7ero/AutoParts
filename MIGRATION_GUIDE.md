# Руководство по переносу AutoParts Parser на свой сервер

## Требования к серверу

### Минимальные требования
- **CPU**: 2 ядра
- **RAM**: 4 GB
- **Диск**: 20 GB свободного места
- **ОС**: Ubuntu 20.04+ / CentOS 7+ / Debian 10+

### Рекомендуемые требования
- **CPU**: 4+ ядра
- **RAM**: 8+ GB
- **Диск**: 50+ GB SSD
- **ОС**: Ubuntu 22.04 LTS

## Подготовка сервера

### 1. Обновление системы
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Установка Docker и Docker Compose
```bash
# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Добавление пользователя в группу docker
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перезагрузка для применения изменений
sudo reboot
```

### 3. Установка Git
```bash
sudo apt install git -y
```

## Клонирование и настройка проекта

### 1. Клонирование репозитория
```bash
git clone https://github.com/your-username/AutoParts.git
cd AutoParts
```

### 2. Настройка переменных окружения
```bash
# Создание файла .env
cat > .env << EOF
POSTGRES_DB=autoparts
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password
DJANGO_SECRET_KEY=your_django_secret_key_here
DEBUG=False
ALLOWED_HOSTS=your_domain.com,your_ip_address
EOF
```

### 3. Настройка Nginx
```bash
# Редактирование nginx/nginx.conf
# Замените your_domain.com на ваш домен
sed -i 's/your_domain.com/your_actual_domain.com/g' nginx/nginx.conf
```

## Запуск системы

### 1. Первый запуск
```bash
# Сборка и запуск контейнеров
docker compose up -d --build

# Ожидание готовности сервисов
sleep 60

# Проверка статуса
docker compose ps
```

### 2. Создание суперпользователя Django
```bash
docker compose exec backend python manage.py createsuperuser
```

### 3. Применение миграций
```bash
docker compose exec backend python manage.py migrate
```

## Настройка домена и SSL

### 1. Настройка DNS
Добавьте A-запись для вашего домена:
```
your_domain.com -> ваш_ip_адрес
```

### 2. Установка SSL сертификата (Let's Encrypt)
```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx -y

# Получение сертификата
sudo certbot --nginx -d your_domain.com

# Автоматическое обновление
sudo crontab -e
# Добавьте строку:
# 0 12 * * * /usr/bin/certbot renew --quiet
```

### 3. Обновление Nginx конфигурации
```bash
# Редактирование nginx/nginx.conf для HTTPS
# Добавьте SSL конфигурацию
```

## Настройка прокси

### 1. Подготовка файла прокси
```bash
# Создание файла proxies.txt
cat > proxies.txt << EOF
username1:password1@proxy1_ip:port
username2:password2@proxy2_ip:port
username3:password3@proxy3_ip:port
EOF
```

### 2. Загрузка прокси через веб-интерфейс
1. Откройте http://your_domain.com/proxy-manager
2. Загрузите файл proxies.txt
3. Проверьте статус прокси

## Мониторинг и обслуживание

### 1. Настройка логирования
```bash
# Создание директории для логов
sudo mkdir -p /var/log/autoparts
sudo chown $USER:$USER /var/log/autoparts

# Добавление в docker-compose.yml
# volumes:
#   - /var/log/autoparts:/app/logs
```

### 2. Настройка автоматических бэкапов
```bash
# Создание скрипта бэкапа
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backup/autoparts"

mkdir -p $BACKUP_DIR

# Бэкап базы данных
docker compose exec -T postgres pg_dump -U postgres autoparts > $BACKUP_DIR/db_$DATE.sql

# Бэкап файлов результатов
docker cp autoparts-backend-1:/app/media/results/ $BACKUP_DIR/results_$DATE/

# Удаление старых бэкапов (старше 7 дней)
find $BACKUP_DIR -name "db_*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "results_*" -mtime +7 -exec rm -rf {} \;
EOF

chmod +x backup.sh

# Добавление в crontab
crontab -e
# Добавьте строку:
# 0 2 * * * /path/to/backup.sh
```

### 3. Настройка мониторинга
```bash
# Установка htop для мониторинга
sudo apt install htop -y

# Создание скрипта мониторинга
cat > monitor.sh << 'EOF'
#!/bin/bash
echo "=== AutoParts Parser Status ==="
echo "Date: $(date)"
echo ""

echo "Docker containers:"
docker compose ps
echo ""

echo "Resource usage:"
docker stats --no-stream
echo ""

echo "Recent logs:"
docker compose logs --tail=20 celery
EOF

chmod +x monitor.sh
```

## Оптимизация производительности

### 1. Настройка Docker
```bash
# Создание /etc/docker/daemon.json
sudo tee /etc/docker/daemon.json << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
EOF

sudo systemctl restart docker
```

### 2. Настройка PostgreSQL
```bash
# Оптимизация PostgreSQL в docker-compose.yml
# Добавьте переменные окружения:
# POSTGRES_SHARED_BUFFERS=256MB
# POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
# POSTGRES_WORK_MEM=4MB
```

### 3. Настройка Celery
```bash
# Увеличение количества воркеров в docker-compose.yml
# command: celery -A backend worker --loglevel=info --concurrency=4
```

## Безопасность

### 1. Настройка файрвола
```bash
# Установка UFW
sudo apt install ufw -y

# Настройка правил
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

### 2. Обновление паролей
```bash
# Изменение пароля PostgreSQL
docker compose exec postgres psql -U postgres -c "ALTER USER postgres PASSWORD 'new_secure_password';"

# Обновление .env файла
sed -i 's/your_secure_password/new_secure_password/g' .env
```

### 3. Настройка регулярных обновлений
```bash
# Создание скрипта обновления
cat > update.sh << 'EOF'
#!/bin/bash
cd /path/to/AutoParts
git pull origin main
docker compose down
docker compose build --no-cache
docker compose up -d
EOF

chmod +x update.sh
```

## Решение проблем

### Частые проблемы и решения

#### 1. Проблемы с памятью
```bash
# Увеличение swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

#### 2. Проблемы с дисковым пространством
```bash
# Очистка Docker
docker system prune -a
docker volume prune
```

#### 3. Проблемы с сетью
```bash
# Проверка портов
sudo netstat -tulpn | grep :80
sudo netstat -tulpn | grep :443
```

## Контакты и поддержка

### Полезные команды
```bash
# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f

# Перезапуск сервисов
docker compose restart

# Обновление системы
./update.sh
```

### Логи для диагностики
- **Celery**: `docker compose logs -f celery`
- **Backend**: `docker compose logs -f backend`
- **Frontend**: `docker compose logs -f frontend`
- **Nginx**: `docker compose logs -f nginx`
- **PostgreSQL**: `docker compose logs -f postgres`

### Контакты
При возникновении проблем:
1. Проверьте логи: `docker compose logs -f`
2. Проверьте статус: `docker compose ps`
3. Обратитесь к разработчику с подробным описанием проблемы 