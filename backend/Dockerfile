FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Собираем статику
RUN python manage.py collectstatic --noinput

# Открываем порт для ASGI
EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"] 