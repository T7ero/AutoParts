# Развертывание AutoParts на Linux сервере

## Быстрый старт

### 1. Подготовка сервера

```bash
# Обновите систему
sudo apt update && sudo apt upgrade -y

# Установите Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Добавьте пользователя в группу docker
sudo usermod -aG docker $USER

# Создайте swap файл (для серверов с 2GB RAM)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Перезагрузитесь
sudo reboot
```

### 2. Клонирование проекта

```bash
# После перезагрузки
cd ~
git clone <repository-url> AutoParts
cd AutoParts

# Или скопируйте файлы вручную
mkdir AutoParts
cd AutoParts
# Скопируйте все файлы проекта
```

### 3. Исправление GPG проблем

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

### 4. Запуск системы

```bash
# Соберите и запустите систему
docker compose up -d --build

# Проверьте статус
docker compose ps

# Проверьте логи
docker compose logs
```

## Подробная установка

### Требования к серверу

- **ОС:** Ubuntu 20.04+ / CentOS 7+ / Debian 10+
- **CPU:** 1 ядро
- **RAM:** 2 ГБ
- **Диск:** 10 ГБ свободного места

### Установка Docker

#### Ubuntu/Debian:
```bash
# Удалите старые версии Docker
sudo apt-get remove docker docker-engine docker.io containerd runc

# Установите зависимости
sudo apt-get update
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Добавьте GPG ключ Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Добавьте репозиторий Docker
echo \
  "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установите Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Запустите Docker
sudo systemctl start docker
sudo systemctl enable docker

# Добавьте пользователя в группу docker
sudo usermod -aG docker $USER
```

#### CentOS/RHEL:
```bash
# Установите зависимости
sudo yum install -y yum-utils

# Добавьте репозиторий Docker
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# Установите Docker
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Запустите Docker
sudo systemctl start docker
sudo systemctl enable docker

# Добавьте пользователя в группу docker
sudo usermod -aG docker $USER
```

### Настройка swap

```bash
# Создайте swap файл 2GB
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Сделайте swap постоянным
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Проверьте swap
free -h
```

### Настройка firewall

```bash
# Ubuntu/Debian
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# CentOS/RHEL
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --permanent --add-port=443/tcp
sudo firewall-cmd --reload
```

### Развертывание приложения

```bash
# Клонируйте репозиторий
git clone <repository-url> AutoParts
cd AutoParts

# Создайте файл прокси (опционально)
cat > proxies.txt << EOF
# Добавьте ваши прокси в формате:
# ip:port@login:password
# или
# ip:port

# Примеры:
# 192.168.1.100:8080@user1:pass1
# 10.0.0.1:3128@user2:pass2
EOF

# Исправьте GPG проблемы
chmod +x fix_gpg.sh
./fix_gpg.sh

# Соберите и запустите систему
docker compose up -d --build

# Проверьте статус
docker compose ps
```

### Проверка работы

```bash
# Проверьте доступность веб-интерфейса
curl http://localhost

# Проверьте API
curl http://localhost/api/parsing-tasks/

# Проверьте логи
docker compose logs

# Проверьте использование ресурсов
docker stats
```

## Управление системой

### Основные команды

```bash
# Запуск системы
docker compose up -d

# Остановка системы
docker compose down

# Перезапуск системы
docker compose restart

# Просмотр логов
docker compose logs -f

# Просмотр статуса
docker compose ps

# Обновление системы
git pull
docker compose down
docker compose up -d --build
```

### Мониторинг

```bash
# Просмотр использования ресурсов
docker stats

# Проверка дискового пространства
df -h

# Проверка использования памяти
free -h

# Проверка открытых портов
sudo netstat -tlnp
```

### Резервное копирование

```bash
# Создание бэкапа базы данных
docker compose exec db pg_dump -U postgres autoparts > backup_$(date +%Y%m%d_%H%M%S).sql

# Восстановление из бэкапа
docker compose exec -T db psql -U postgres autoparts < backup_file.sql
```

## Устранение неполадок

### Проблема: GPG ошибки при сборке

```bash
# Запустите скрипт исправления
./fix_gpg.sh

# Или выполните команды вручную:
sudo apt-get update
sudo apt-get install -y ubuntu-keyring
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 871920D1991BC93F
sudo update-ca-certificates
```

### Проблема: Недостаточно памяти

```bash
# Проверьте swap
free -h

# Создайте дополнительный swap если нужно
sudo fallocate -l 4G /swapfile2
sudo chmod 600 /swapfile2
sudo mkswap /swapfile2
sudo swapon /swapfile2
```

### Проблема: Порт 80 занят

```bash
# Проверьте что использует порт 80
sudo netstat -tlnp | grep :80

# Остановите nginx если он запущен
sudo systemctl stop nginx

# Или измените порт в docker-compose.yml
```

### Проблема: Docker не запускается

```bash
# Проверьте статус Docker
sudo systemctl status docker

# Перезапустите Docker
sudo systemctl restart docker

# Проверьте что пользователь в группе docker
groups $USER
```

## Оптимизация производительности

### Для серверов с 2GB RAM:
- Система уже оптимизирована
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
# Обновляйте систему регулярно
sudo apt update && sudo apt upgrade -y

# Настройте firewall
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Проверяйте открытые порты
sudo netstat -tlnp
```

## Поддержка

При возникновении проблем:
1. Проверьте логи: `docker compose logs`
2. Убедитесь, что все сервисы запущены: `docker compose ps`
3. Перезапустите систему: `docker compose restart`
4. Проверьте ресурсы системы и интернет-соединение 