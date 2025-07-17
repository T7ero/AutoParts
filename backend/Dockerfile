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

# Этап сборки (React/Vue)
FROM node:18 as build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build  # Убедитесь, что эта команда работает

# Этап запуска (Nginx)
FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf  # Если используется Nginx
EXPOSE 80
