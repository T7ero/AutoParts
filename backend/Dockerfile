FROM python:3.10-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        gnupg \
        wget \
        curl \
        unzip \
        xvfb \
        procps && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 648ACFD622F3D138 && \
    apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 0E98404D386FA1D9 && \
    echo "deb http://deb.debian.org/debian bookworm main" > /etc/apt/sources.list && \
    echo "deb http://deb.debian.org/debian bookworm-updates main" >> /etc/apt/sources.list && \
    echo "deb http://security.debian.org/debian-security bookworm-security main" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        chromium-driver \
        chromium \
        gcc \
        python3-dev \
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

# Создаем пользователя для запуска Chrome
RUN groupadd -r chrome && useradd -r -g chrome -G audio,video chrome \
    && mkdir -p /home/chrome/Downloads \
    && chown -R chrome:chrome /home/chrome

# Копируем и устанавливаем Python-зависимости
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы
COPY . .

# Добавьте эту строку для установки Daphne
RUN pip install daphne

# Собираем статику
RUN python manage.py collectstatic --noinput

# Создаем скрипт для запуска Xvfb
RUN echo '#!/bin/bash\nXvfb :99 -screen 0 1280x720x24 &\nexport DISPLAY=:99\nexec "$@"' > /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000
CMD ["/usr/local/bin/entrypoint.sh", "daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]