# Руководство по администрированию AutoParts Parser

## Обзор системы

AutoParts Parser - это веб-приложение для парсинга брендов автозапчастей с сайтов Autopiter, Emex и Armtek. Система состоит из:

- **Backend**: Django + Celery + Redis
- **Frontend**: React
- **База данных**: PostgreSQL
- **Прокси**: Ротация прокси для обхода блокировок
- **Selenium**: Для динамического контента

## Последние улучшения производительности (январь 2025)

### Оптимизация таймаутов
- Увеличен лимит времени выполнения задач до 6 часов
- Оптимизированы таймауты для HTTP-запросов и Selenium
- Улучшена система мониторинга прогресса

### Улучшенная фильтрация брендов
- Расширен список исключений для "мусорных" брендов
- Добавлена фильтрация UI-элементов и навигационных элементов
- Улучшена обработка объединенных брендов

### Оптимизация Selenium
- Ускорена инициализация Chrome драйвера
- Улучшена очистка временных файлов и процессов
- Добавлены дополнительные опции для стабильности

## Структура проекта

```
AutoParts/
├── backend/          # Django backend
├── frontend/         # React frontend
├── nginx/           # Nginx конфигурация
├── docker-compose.yml
└── README.md
```

## Основные команды

### Запуск системы
```bash
# Запуск всех сервисов
docker compose up -d

# Просмотр логов
docker compose logs -f

# Остановка
docker compose down
```

### Пересборка после изменений
```bash
# Полная пересборка
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Мониторинг

#### Проверка статуса сервисов
```bash
docker compose ps
```

#### Просмотр логов конкретного сервиса
```bash
# Логи Celery (парсинг)
docker compose logs -f celery

# Логи Backend (Django)
docker compose logs -f backend

# Логи Frontend (React)
docker compose logs -f frontend

# Логи Nginx
docker compose logs -f nginx
```

#### Мониторинг ресурсов
```bash
# Использование памяти и CPU
docker stats

# Дисковое пространство
df -h
```

## Управление задачами

### Просмотр задач
- Откройте веб-интерфейс: http://87.228.101.164
- Перейдите на вкладку "Задачи"

### Очистка задач
- В веб-интерфейсе: кнопка "Очистить задачи"
- Через API: `DELETE /api/parsing-tasks/clear/`

### Удаление отдельных задач
- В веб-интерфейсе: кнопка "Удалить задачу" рядом с каждой задачей

## Управление прокси

### Загрузка прокси
1. Подготовьте файл `proxies.txt` в формате:
   ```
   username:password@ip:port
   username:password@ip:port
   ```
2. Загрузите через веб-интерфейс: http://87.228.101.164/proxy-manager

### Сброс прокси
- В веб-интерфейсе: кнопка "Сбросить прокси"

## Решение проблем

### Проблемы с парсингом

#### "Failed to parse" ошибки
1. Проверьте доступность сайтов
2. Обновите прокси
3. Проверьте логи Celery: `docker compose logs -f celery`

#### Таймауты
1. Увеличьте таймауты в `backend/api/tasks.py`
2. Проверьте качество прокси
3. Уменьшите количество одновременных запросов

#### Неполная обработка файлов
1. Проверьте логи на ошибки
2. Увеличьте `time_limit` в Celery
3. Проверьте доступность прокси

### Проблемы с Docker

#### Ошибки сборки
```bash
# Очистка кэша Docker
docker system prune -a

# Пересборка
docker compose build --no-cache
```

#### Проблемы с памятью
```bash
# Ограничение памяти для контейнеров
docker compose down
# Отредактируйте docker-compose.yml, добавьте memory limits
docker compose up -d
```

### Проблемы с базой данных
```bash
# Сброс базы данных
docker compose down
docker volume rm autoparts_postgres_data
docker compose up -d
```

## Рекомендации по прокси

### Где купить прокси
- **Residential прокси**: Bright Data, Oxylabs, Smartproxy
- **Datacenter прокси**: ProxyMesh, ProxyRack
- **Rotating прокси**: Luminati, GeoSurf

### Типы прокси для парсинга
1. **Residential** - лучшие для обхода блокировок
2. **Rotating** - автоматическая смена IP
3. **Sticky** - один IP на сессию

### Формат файла proxies.txt
```
username:password@ip:port
username:password@ip:port
username:password@ip:port
```

## Резервное копирование

### База данных
```bash
# Создание бэкапа
docker compose exec postgres pg_dump -U postgres autoparts > backup.sql

# Восстановление
docker compose exec -T postgres psql -U postgres autoparts < backup.sql
```

### Файлы результатов
```bash
# Копирование результатов
docker cp autoparts-backend-1:/app/media/results/ ./backup_results/
```

## Обновление системы

### Обновление кода
```bash
# Остановка
docker compose down

# Обновление кода
git pull origin main

# Пересборка
docker compose build --no-cache
docker compose up -d
```

### Обновление зависимостей
```bash
# Обновление requirements.txt
docker compose exec backend pip install -r requirements.txt

# Перезапуск
docker compose restart backend
```

## Мониторинг производительности

### Метрики для отслеживания
- Время выполнения задач
- Количество успешных/неуспешных запросов
- Использование памяти и CPU
- Качество прокси

### Логирование
- Логи Celery: `docker compose logs -f celery`
- Логи Django: `docker compose logs -f backend`
- Логи Nginx: `docker compose logs -f nginx`

## Безопасность

### Рекомендации
1. Используйте HTTPS в продакшене
2. Ограничьте доступ к админ-панели
3. Регулярно обновляйте зависимости
4. Мониторьте логи на подозрительную активность

### Настройка файрвола
```bash
# Открыть только необходимые порты
ufw allow 80
ufw allow 443
ufw enable
```

## Контакты для поддержки

При возникновении проблем:
1. Проверьте логи: `docker compose logs -f`
2. Проверьте статус сервисов: `docker compose ps`
3. Обратитесь к разработчику с логами ошибок 