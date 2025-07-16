# AutoParts Parser

Веб-приложение для парсинга данных автозапчастей с различных сайтов.

## Функциональность

- Загрузка и обработка Excel-файлов с данными запчастей
- Парсинг брендов-конкурентов и кросс-номеров
- Сохранение данных в PostgreSQL
- Экспорт результатов в Excel/TXT
- Система авторизации
- Ограничение одновременного парсинга
- Отображение прогресса выполнения

## Технологии

- Backend: Django + Django REST Framework
- Frontend: React + Tailwind CSS
- База данных: PostgreSQL
- Очереди задач: Celery + Redis
- Парсинг: Scrapy + Selenium
- Тестирование: pytest

## Установка

1. Клонировать репозиторий
2. Создать виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```

3. Установить зависимости:
```bash
pip install -r requirements.txt
```

4. Настроить переменные окружения в файле .env

5. Применить миграции:
```bash
python manage.py migrate
 cd frontend - npm install - npm start
 cd backend - celery -A backend worker --loglevel=info // celery -A backend worker -l info --pool=solo
redis-server

```

6. Запустить сервер разработки:
```bash
python manage.py runserver
```

## Структура проекта

```
autoparts/
├── backend/           # Django проект
│   ├── api/          # REST API
│   ├── parser/       # Модуль парсинга
│   └── core/         # Основные компоненты
├── frontend/         # React приложение
└── tests/            # Тесты
``` 