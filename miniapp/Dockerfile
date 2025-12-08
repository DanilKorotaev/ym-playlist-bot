FROM python:3.12-slim

WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем только необходимые файлы для API
COPY database/ ./database/
COPY services/ ./services/
COPY utils/ ./utils/
COPY yandex_client_manager.py .
COPY miniapp/ ./miniapp/

# Запускаем API
CMD ["python", "-m", "miniapp.api.main"]

