FROM ubuntu:22.04

# Устанавливаем Python и необходимые зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-dev \
        ca-certificates \
        wget \
        curl \
        unzip \
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
        xdg-utils && \
    rm -rf /var/lib/apt/lists/*

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
RUN groupadd -r chrome && useradd -r -g chrome -G audio,video chrome \
    && mkdir -p /home/chrome/Downloads \
    && chown -R chrome:chrome /home/chrome

WORKDIR /app

# Копируем и устанавливаем Python-зависимости
COPY requirements.txt ./
RUN python3 -m pip install --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Копируем остальные файлы
COPY . .

# Добавляем Daphne
RUN pip3 install daphne

# Собираем статику
RUN python3 manage.py collectstatic --noinput

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

EXPOSE 8000
CMD ["/usr/local/bin/entrypoint.sh", "daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"] 