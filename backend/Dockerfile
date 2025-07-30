FROM ubuntu:22.04

# Устанавливаем переменные окружения
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

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
        unzip \
        xvfb \
        sudo \
        gosu \
        && rm -rf /var/lib/apt/lists/*

# Устанавливаем Python и зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-dev \
        build-essential \
        libpq-dev \
        postgresql-client \
        && rm -rf /var/lib/apt/lists/*

# Устанавливаем Chromium и ChromeDriver
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        chromium-browser \
        chromium-chromedriver \
        && rm -rf /var/lib/apt/lists/*

# Создаем символические ссылки для совместимости
RUN ln -sf /usr/bin/chromium-browser /usr/bin/google-chrome && \
    ln -sf /usr/bin/chromedriver /usr/local/bin/chromedriver

# Создаем пользователя для запуска приложения
RUN groupadd -r appuser && \
    useradd -r -g appuser -G audio,video appuser && \
    mkdir -p /home/appuser && \
    chown -R appuser:appuser /home/appuser && \
    echo "appuser ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Устанавливаем дополнительные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
        procps \
        gcc \
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

# Создаем структуру директорий с правильными правами
RUN mkdir -p /app/media/uploads /app/media/results /app/media/temp /app/static && \
    chown -R appuser:appuser /app && \
    chmod -R 775 /app/media

# Копируем requirements.txt
COPY --chown=appuser:appuser requirements.txt .

# Устанавливаем Python зависимости
RUN pip3 install --no-cache-dir -r requirements.txt daphne

# Копируем код приложения
COPY --chown=appuser:appuser . .

# Копируем entrypoint скрипт
COPY --chown=appuser:appuser entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Фиксируем права для media директорий
RUN chown -R appuser:appuser /app/media && \
    chmod -R 775 /app/media

# Собираем статические файлы
RUN python3 manage.py collectstatic --noinput

# Открываем порт
EXPOSE 8000

# Запускаем приложение через entrypoint
CMD ["/usr/local/bin/entrypoint.sh"]