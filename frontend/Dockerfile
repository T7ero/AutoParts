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
