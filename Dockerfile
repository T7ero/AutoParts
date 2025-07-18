
FROM node:18 AS frontend-builder  # Замените 'as' на 'AS' для соответствия регистру

WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build


FROM python:3.10-slim

WORKDIR /app


COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt


COPY backend/ ./


COPY --from=frontend-builder /app/build /app/backend/static/


RUN python manage.py collectstatic --noinput


EXPOSE 8000


CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]
