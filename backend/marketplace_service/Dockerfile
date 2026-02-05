FROM python:3.11-slim

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

RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

RUN CHROME_VERSION=$(google-chrome --product-version) \
    && CHROME_BUILD=$(echo "$CHROME_VERSION" | cut -d. -f1-3) \
    && CHROME_MAJOR=$(echo "$CHROME_VERSION" | cut -d. -f1) \
    && DRIVER_URL=$(curl -fsSL "https://googlechromelabs.github.io/chrome-for-testing/latest-patch-versions-per-build-with-downloads.json" | \
      jq -r --arg b "$CHROME_BUILD" '.builds[$b].downloads.chromedriver[]? | select(.platform=="linux64") | .url' | head -n1) \
    && if [ -z "$DRIVER_URL" ] || [ "$DRIVER_URL" = "null" ]; then \
      DRIVER_URL=$(curl -fsSL "https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone-with-downloads.json" | \
      jq -r --arg m "$CHROME_MAJOR" '.milestones[$m].downloads.chromedriver[]? | select(.platform=="linux64") | .url' | head -n1); \
    fi \
    && if [ -z "$DRIVER_URL" ] || [ "$DRIVER_URL" = "null" ]; then \
      echo "Failed to resolve chromedriver for chrome $CHROME_VERSION"; exit 1; \
    fi \
    && echo "Chrome version: $CHROME_VERSION" \
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
