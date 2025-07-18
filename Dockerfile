# ===== Фронтенд (React/Vue) =====
FROM node:18 as frontend-builder

WORKDIR /app
COPY frontend/package*.json ./  # Укажите правильный путь к package.json
RUN npm install
COPY frontend/ ./
RUN npm run build

# ===== Бэкенд (Django) =====
FROM python:3.10-slim

WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY backend/requirements.txt ./  # Укажите правильный путь
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копируем весь бэкенд
COPY backend/ ./

# Копируем собранный фронтенд в статику Django (если нужно)
COPY --from=frontend-builder /app/build /app/backend/static/

# Собираем статику Django
RUN python manage.py collectstatic --noinput

EXPOSE 8000  # Обязательно для Timeweb Cloud

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]
