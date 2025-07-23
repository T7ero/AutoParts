FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./
RUN python3 -m pip install --upgrade pip setuptools wheel

# Установка Chromium и chromedriver
RUN apt-get update && \
    apt-get install -y chromium-driver chromium && \
    rm -rf /var/lib/apt/lists/*

COPY . .

# Собираем статику
RUN python manage.py collectstatic --noinput

# Открываем порт для ASGI
EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"] 
