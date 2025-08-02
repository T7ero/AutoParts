# Настройка AutoParts на Linux сервере

## Требования к серверу

- **ОС:** Ubuntu 20.04+ / CentOS 7+ / Debian 10+
- **CPU:** 1 ядро
- **RAM:** 2 ГБ
- **Диск:** 10 ГБ свободного места

## 1. Установка Docker

### Ubuntu/Debian:
```bash
# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Устанавливаем зависимости
sudo apt install -y apt-transport-https ca-certificates curl gnupg lsb-release

# Добавляем GPG ключ Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Добавляем репозиторий Docker
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Устанавливаем Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Добавляем пользователя в группу docker
sudo usermod -aG docker $USER

# Запускаем Docker
sudo systemctl start docker
sudo systemctl enable docker
```

### CentOS/RHEL:
```bash
# Устанавливаем зависимости
sudo yum install -y yum-utils

# Добавляем репозиторий Docker
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# Устанавливаем Docker
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Запускаем Docker
sudo systemctl start docker
sudo systemctl enable docker

# Добавляем пользователя в группу docker
sudo usermod -aG docker $USER
```

## 2. Настройка swap (рекомендуется)

```bash
# Создаем swap файл 2GB
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Делаем swap постоянным
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 3. Клонирование проекта

```bash
# Клонируем репозиторий
git clone <repository-url> AutoParts
cd AutoParts

# Или если у вас уже есть файлы
cd /path/to/AutoParts
```

## 4. Настройка файла прокси (опционально)

```bash
# Создаем файл прокси
cat > proxies.txt << EOF
# Добавьте ваши прокси в формате:
# ip:port@login:password
# или
# ip:port

# Примеры:
# 192.168.1.100:8080@user1:pass1
# 10.0.0.1:3128@user2:pass2
EOF
```

## 5. Запуск системы

```bash
# Перезагружаемся для применения изменений группы docker
sudo reboot

# После перезагрузки
cd AutoParts

# Запускаем систему
docker compose up -d --build

# Проверяем статус
docker compose ps
```

## 6. Проверка работы

```bash
# Проверяем логи
docker compose logs

# Проверяем доступность
curl http://localhost

# Проверяем API
curl http://localhost/api/parsing-tasks/
```

## 7. Настройка firewall (если нужно)

```bash
# Ubuntu/Debian
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --permanent --add-port=443/tcp
sudo firewall-cmd --reload
```

## 8. Мониторинг системы

```bash
# Просмотр логов в реальном времени
docker compose logs -f

# Просмотр использования ресурсов
docker stats

# Проверка дискового пространства
df -h

# Проверка использования памяти
free -h
```

## 9. Управление системой

```bash
# Остановка системы
docker compose down

# Перезапуск системы
docker compose restart

# Обновление системы
git pull
docker compose down
docker compose up -d --build

# Очистка неиспользуемых образов
docker system prune -f
```

## 10. Резервное копирование

```bash
# Создание бэкапа базы данных
docker compose exec db pg_dump -U postgres autoparts > backup_$(date +%Y%m%d_%H%M%S).sql

# Восстановление из бэкапа
docker compose exec -T db psql -U postgres autoparts < backup_file.sql
```

## Устранение неполадок

### Проблема: Недостаточно памяти
```bash
# Проверяем swap
free -h

# Если swap не активен, создаем его
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### Проблема: Docker не запускается
```bash
# Проверяем статус Docker
sudo systemctl status docker

# Перезапускаем Docker
sudo systemctl restart docker
```

### Проблема: Порт 80 занят
```bash
# Проверяем что использует порт 80
sudo netstat -tlnp | grep :80

# Останавливаем nginx если он запущен
sudo systemctl stop nginx
```

### Проблема: Медленная работа
```bash
# Проверяем ресурсы
htop

# Увеличиваем swap если нужно
sudo fallocate -l 4G /swapfile2
sudo chmod 600 /swapfile2
sudo mkswap /swapfile2
sudo swapon /swapfile2
```

## Оптимизация производительности

### Для серверов с 2GB RAM:
- Система уже оптимизирована для минимальных ресурсов
- Используется 1 поток для экономии памяти
- Периодическая очистка процессов Chrome

### Для серверов с 4GB+ RAM:
Можно увеличить ресурсы в `docker-compose.yml`:
```yaml
celery:
  deploy:
    resources:
      limits:
        memory: 2G
        cpus: '1.0'
      reservations:
        memory: 1G
        cpus: '0.5'
```

## Безопасность

```bash
# Обновляем систему регулярно
sudo apt update && sudo apt upgrade -y

# Проверяем открытые порты
sudo netstat -tlnp

# Настраиваем firewall
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
``` 