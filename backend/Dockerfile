FROM ubuntu:22.04

# Устанавливаем переменные окружения
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Обновляем систему и устанавливаем базовые зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        gnupg \
        software-properties-common \
        apt-transport-https \
        lsb-release \
        unzip && \
    rm -rf /var/lib/apt/lists/*

# Исправляем GPG ключи Ubuntu - более надежный подход
RUN apt-get update && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32 && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 871920D1991BC93F && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 648ACFD622F3D138 && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 0E98404D386FA1D9 && \
    apt-get update

# Устанавливаем Python и зависимости
RUN apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-dev \
        build-essential \
        libpq-dev \
        postgresql-client \
        && rm -rf /var/lib/apt/lists/*

# Устанавливаем Chrome используя современный способ
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем ChromeDriver более надежным способом
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | awk -F'.' '{print $1}') && \
    echo "Chrome version: $CHROME_VERSION" && \
    LATEST_RELEASE=$(wget -qO- "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION") && \
    echo "Latest ChromeDriver release: $LATEST_RELEASE" && \
    wget -q "https://chromedriver.storage.googleapis.com/$LATEST_RELEASE/chromedriver_linux64.zip" -O chromedriver.zip && \
    ls -la chromedriver.zip && \
    unzip chromedriver.zip && \
    mv chromedriver /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver && \
    rm chromedriver.zip && \
    chromedriver --version

# Создаем пользователя для запуска Chrome
RUN groupadd -r chrome && useradd -r -g chrome -G audio,video chrome && \
    mkdir -p /home/chrome && chown -R chrome:chrome /home/chrome

# Устанавливаем дополнительные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        procps \
        gcc \
        gnupg \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libxss1 \
        libxtst6 \
        xdg-utils \
        && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip3 install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Создаем скрипт для запуска с миграциями
RUN echo '#!/bin/bash\n\
# Ждем готовности базы данных\n\
echo "Waiting for database..."\n\
while ! python3 manage.py check --database default 2>/dev/null; do\n\
    echo "Database not ready, waiting..."\n\
    sleep 2\n\
done\n\
echo "Database is ready!"\n\
\n\
# Выполняем миграции\n\
echo "Running migrations..."\n\
python3 manage.py migrate\n\
\n\
# Создаем суперпользователя если не существует\n\
echo "Creating superuser..."\n\
python3 manage.py shell -c "\n\
from django.contrib.auth.models import User\n\
if not User.objects.filter(username=\"admin\").exists():\n\
    User.objects.create_superuser(\"admin\", \"admin@example.com\", \"admin\")\n\
    print(\"Superuser created\")\n\
else:\n\
    print(\"Superuser already exists\")\n\
"\n\
\n\
# Запускаем Xvfb\n\
Xvfb :99 -screen 0 1280x720x24 &\n\
export DISPLAY=:99\n\
\n\
# Запускаем приложение\n\
exec "$@"' > /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/entrypoint.sh

# Собираем статические файлы
RUN python3 manage.py collectstatic --noinput

# Открываем порт
EXPOSE 8000

# Запускаем приложение
CMD ["/usr/local/bin/entrypoint.sh", "daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"] 