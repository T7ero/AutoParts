#!/bin/bash

echo "🔧 Исправление проблем с парсингом..."

# Останавливаем контейнеры
echo "⏹️ Останавливаем контейнеры..."
docker compose down

# Очищаем кэш Docker
echo "🧹 Очищаем кэш Docker..."
docker system prune -f

# Пересобираем контейнеры
echo "🔨 Пересобираем контейнеры..."
docker compose build --no-cache

# Запускаем контейнеры
echo "🚀 Запускаем контейнеры..."
docker compose up -d

# Ждем готовности сервисов
echo "⏳ Ожидание готовности сервисов..."
sleep 60

# Проверяем статус
echo "📊 Проверяем статус сервисов..."
docker compose ps

echo "✅ Исправления применены!"
echo "🌐 Приложение доступно по адресу: http://87.228.101.164"
echo "🔗 Страница прокси: http://87.228.101.164/proxy-manager"
echo ""
echo "📝 Логи для проверки:"
echo "docker compose logs -f"
echo ""
echo "🔍 Изменения:"
echo "1. Упрощена логика прокси - сначала без прокси, потом с прокси только если есть"
echo "2. Уменьшены таймауты и количество попыток для Emex"
echo "3. Armtek теперь фильтрует только 'PAZ', 'PRC', 'РФ'"
echo "4. Улучшена обработка ошибок Excel файлов"
echo ""
echo "📋 Рекомендации по прокси:"
echo ""
echo "🌐 Где покупать прокси:"
echo "1. https://proxy-seller.com - российские прокси"
echo "2. https://proxy6.net - качественные прокси"
echo "3. https://hidemy.name - проверенные прокси"
echo "4. https://proxy-list.org - бесплатные и платные"
echo ""
echo "💡 Какие прокси покупать:"
echo "- HTTP/HTTPS прокси (не SOCKS)"
echo "- Российские IP адреса для лучшей совместимости"
echo "- Высокая скорость (от 100 Мбит/с)"
echo "- Поддержка авторизации по логину/паролю"
echo "- Минимум 95% uptime"
echo ""
echo "📄 Правильный формат файла proxies.txt:"
echo "login:password@ip:port"
echo "Пример:"
echo "user123:pass456@192.168.1.100:8080"
echo "admin:secret@10.0.0.1:3128"
echo ""
echo "⚠️  Важные моменты:"
echo "- Один прокси на строку"
echo "- Формат: логин:пароль@IP:порт"
echo "- Без пробелов в начале и конце строки"
echo "- Файл должен быть в кодировке UTF-8"
echo ""
echo "🔧 Тестирование прокси:"
echo "curl -x http://user:pass@ip:port http://httpbin.org/ip"
echo ""
echo "📊 Мониторинг работы:"
echo "docker compose logs -f celery" 