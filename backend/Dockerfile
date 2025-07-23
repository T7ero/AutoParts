FROM python:3.10-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update \
    && apt-get install -y --no-install-recommends apt-transport-https ca-certificates gnupg \
    && apt-get install -y --allow-unauthenticated --allow-insecure-repositories chromium-driver chromium gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем и устанавливаем Python-зависимости
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы
COPY . .

# Добавьте эту строку для установки Daphne
RUN pip install daphne

# Собираем статику
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]