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

# Устанавливаем Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем ChromeDriver
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | awk -F'.' '{print $1}') && \
    wget -q "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION" -O - | xargs -I {} wget -q "https://chromedriver.storage.googleapis.com/{}/chromedriver_linux64.zip" && \
    unzip chromedriver_linux64.zip && \
    mv chromedriver /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver && \
    rm chromedriver_linux64.zip

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

# Создаем скрипт для запуска Xvfb
RUN echo '#!/bin/bash\nXvfb :99 -screen 0 1280x720x24 &\nexport DISPLAY=:99\nexec "$@"' > /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000
CMD ["/usr/local/bin/entrypoint.sh", "daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"] 