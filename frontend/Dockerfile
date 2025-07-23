# Этап сборки
FROM node:18 AS builder

# Создаем рабочую директорию внутри контейнера
WORKDIR /usr/src/app

# Копируем package.json и package-lock.json из папки frontend
COPY frontend/package*.json ./

# Устанавливаем зависимости
RUN npm ci --silent

# Копируем ВСЕ файлы фронтенда (включая исходный код)
COPY frontend/ ./

# Запускаем сборку проекта
RUN npm run build

# Этап запуска
FROM nginx:alpine

# Копируем собранные файлы из папки сборки
COPY --from=builder /usr/src/app/build /usr/share/nginx/html

# Копируем конфигурацию Nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Открываем порт 80
EXPOSE 80

# Запускаем Nginx
CMD ["nginx", "-g", "daemon off;"]
