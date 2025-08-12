# Система парсинга автозапчастей

Система для парсинга брендов автозапчастей с сайтов Autopiter, Emex и Armtek.

## Возможности

- Парсинг брендов с трех источников: Autopiter, Emex, Armtek
- Выбор источников для парсинга
- Загрузка Excel-файлов с артикулами
- Отслеживание прогресса в реальном времени
- Сохранение результатов в Excel-файлы
- Управление пользователями
- Ротация прокси для обхода блокировок

## Установка и запуск

### Через Docker (рекомендуется)

```bash
# Клонирование репозитория
git clone <repository-url>
cd AutoParts

# Запуск системы
docker-compose up -d

# Применение миграций
docker-compose exec backend python manage.py migrate

# Создание суперпользователя
docker-compose exec backend python manage.py createsuperuser
```

### Локальная установка

```bash
# Установка зависимостей
pip install -r requirements.txt

# Настройка базы данных
python manage.py migrate

# Создание суперпользователя
python manage.py createsuperuser

# Запуск сервера
python manage.py runserver
```

## Управление пользователями

### Через скрипт (рекомендуется)

```bash
# Создание нового пользователя
python manage_users.py create username email password

# Просмотр списка пользователей
python manage_users.py list

# Удаление пользователя
python manage_users.py delete username

# Изменение пароля
python manage_users.py change_password username new_password

# Справка
python manage_users.py help
```

### Через Django admin

```bash
# Создание суперпользователя для доступа к админке
python manage.py createsuperuser

# Запуск сервера
python manage.py runserver

# Открыть http://localhost:8000/admin/
```

### Через Django shell

```bash
python manage.py shell

# В shell:
from django.contrib.auth.models import User
user = User.objects.create_user('username', 'email@example.com', 'password')
```

## Использование системы

1. **Вход в систему**
   - Откройте http://localhost:3000 (или ваш домен)
   - Войдите с созданными учетными данными

2. **Загрузка файла**
   - Перейдите на страницу "Загрузка"
   - Выберите Excel-файл с артикулами
   - Выберите источники для парсинга (Autopiter, Emex, Armtek)
   - Нажмите "Начать обработку"

3. **Отслеживание прогресса**
   - Перейдите на страницу "Задачи"
   - Следите за прогрессом в реальном времени
   - Скачайте готовые файлы по завершении

## Формат входного файла

Excel-файл должен содержать колонки:
- `brand` - бренд
- `part_number` - номер детали  
- `name` - название детали

## Структура проекта

```
AutoParts/
├── backend/                 # Django backend
│   ├── api/                # API endpoints
│   ├── core/               # Основные модели
│   ├── manage_users.py     # Скрипт управления пользователями
│   └── requirements.txt    # Python зависимости
├── frontend/               # React frontend
│   ├── src/
│   │   ├── pages/         # Страницы приложения
│   │   └── components/    # React компоненты
│   └── package.json       # Node.js зависимости
├── docker-compose.yml      # Docker конфигурация
└── README.md              # Документация
```

## Поддерживаемые бренды

### Armtek
Система распознает следующие бренды:
- QUNZE, NIPPON, MOTORS MATTO, JMC, KOBELCO, PRC
- HUANG LIN, ERISTIC, HINO, OOTOKO, MITSUBISHI, TOYOTA
- AUTOKAT, ZEVS, PITWORK, HITACHI, NISSAN, DETOOL
- CHEMIPRO, STELLOX, FURO, EDCON, REPARTS
- EMEK, HOT-PARTS, ISUZU, CARMECH, G-BRAKE
- QINYAN, AMZ, ERREVI, PETERS, EMMERRE, SIMPECO
- BPW, FEBI, AUGER, BKAVTO, MANSONS, EXOVO
- ALON, AMR, AOSS, KONNOR, SAMPA, WABCO
- И многие другие...

### Autopiter и Emex
Используют черный список для фильтрации мусора и извлечения только реальных брендов.

## Настройка прокси

1. Создайте файл `proxies.txt` в корне проекта
2. Добавьте прокси в формате `ip:port` (по одному на строку)
3. Загрузите файл через веб-интерфейс на странице "Прокси"

## Мониторинг и логи

- Логи Celery: `docker-compose logs celery`
- Логи Django: `docker-compose logs backend`
- Логи Nginx: `docker-compose logs nginx`

## Устранение неполадок

### Проблемы с подключением к базе данных
```bash
# Проверка статуса контейнеров
docker-compose ps

# Перезапуск базы данных
docker-compose restart db

# Применение миграций
docker-compose exec backend python manage.py migrate
```

### Проблемы с парсингом
- Проверьте доступность прокси
- Убедитесь, что сайты доступны
- Проверьте логи на наличие ошибок

### Проблемы с производительностью
- Увеличьте лимиты памяти в docker-compose.yml
- Настройте количество воркеров Celery
- Оптимизируйте размер входных файлов

## Лицензия

Проект разработан для внутреннего использования.