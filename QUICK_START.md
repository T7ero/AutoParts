# Быстрый запуск AutoParts

## 1. Запуск системы

```bash
# Убедитесь, что Docker Desktop запущен
docker compose up -d --build
```

## 2. Проверка статуса

```bash
docker compose ps
```

Все сервисы должны быть в статусе "Up".

## 3. Доступ к системе

- **Основной интерфейс:** http://localhost
- **Управление прокси:** http://localhost/proxy-manager
- **Мониторинг задач:** http://localhost/tasks

## 4. Загрузка прокси (опционально)

1. Откройте http://localhost/proxy-manager
2. Создайте файл `proxies.txt` в корне проекта:
```
192.168.1.100:8080@user1:pass1
10.0.0.1:3128@user2:pass2
```
3. Загрузите файл через веб-интерфейс

## 5. Загрузка файла для парсинга

1. Откройте http://localhost
2. Загрузите Excel файл с колонками: Бренд, Артикул, Наименование
3. Следите за прогрессом на странице задач

## 6. Просмотр логов

```bash
# Все логи
docker compose logs -f

# Только celery (парсинг)
docker compose logs -f celery
```

## 7. Остановка системы

```bash
docker compose down
```

## Решение проблем

### Docker не запускается
- Убедитесь, что Docker Desktop запущен
- Перезапустите Docker Desktop

### Ошибки Selenium
```bash
docker compose restart celery
```

### Медленная обработка
- Добавьте больше прокси
- Увеличьте ресурсы в docker-compose.yml

### Не все артикулы обрабатываются
- Проверьте логи: `docker compose logs celery`
- Увеличьте таймауты в tasks.py 