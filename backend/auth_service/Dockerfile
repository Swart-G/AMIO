FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Запуск на порту 8001 (как указано в nginx.conf)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
