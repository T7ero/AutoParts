# ===== Фронтенд (React/Vue) =====
FROM node:18 AS frontend-builder  # Замените 'as' на 'AS' для соответствия регистру

WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ===== Бэкенд (Django) =====
FROM python:3.10-slim

WORKDIR /app

# Установка зависимостей
COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копирование кода
COPY backend/ ./

# Копирование собранного фронтенда
COPY --from=frontend-builder /app/build /app/backend/static/

# Сборка статики
RUN python manage.py collectstatic --noinput

# Указываем порт (без комментария в этой строке!)
EXPOSE 8000

# Команда запуска (тоже без комментариев в строке)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]
