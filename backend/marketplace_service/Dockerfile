FROM python:3.11-slim

# 1. Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    unzip \
    xvfb \
    libxi6 \
    libnss3 \
    libxss1 \
    libasound2 \
    libgbm1 \
    fonts-liberation \
    jq \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 2. Устанавливаем Google Chrome (stable)
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# 3. Устанавливаем ChromeDriver (Используем jq вместо Python для парсинга JSON)
# Мы просто берем драйвер для канала "Stable", который всегда соответствует последнему Chrome
RUN DRIVER_URL=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | \
    jq -r '.channels.Stable.downloads.chromedriver[] | select(.platform=="linux64") | .url') \
    && echo "Downloading driver from: $DRIVER_URL" \
    && wget -q -O chromedriver-linux64.zip "$DRIVER_URL" \
    && unzip -o chromedriver-linux64.zip \
    && mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf chromedriver-linux64.zip chromedriver-linux64

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8002

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
