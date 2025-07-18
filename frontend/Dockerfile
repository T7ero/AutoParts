# Этап сборки
FROM node:18 AS builder

WORKDIR /usr/src/app
COPY package*.json ./
RUN npm ci --silent
COPY . .
RUN npm run build

# Этап запуска
FROM nginx:alpine
COPY --from=builder /usr/src/app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
