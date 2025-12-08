# Вынос Mini App API в отдельный контейнер

**Статус**: 📋 Планируется  
**Приоритет**: 🟡 Средний  
**Категория**: Технические улучшения  
**Связанная задача**: `task-feature-miniapp-player.md`

## Описание

Вынести FastAPI сервер для Mini App из контейнера бота в отдельный контейнер. Это улучшит архитектуру, позволит независимо масштабировать и обновлять API и бота, а также упростит деплой и мониторинг.

## Текущая ситуация

### Как работает сейчас

1. **Запуск API**: FastAPI сервер запускается внутри бота в отдельном потоке (Thread) с отдельным event loop
2. **Расположение**: API и бот находятся в одном контейнере (`bot`)
3. **Зависимости**: API использует те же зависимости (БД, client_manager), которые передаются через `init_app()`
4. **Порт**: API слушает на порту `MINIAPP_API_PORT` (по умолчанию 8000)

### Код запуска API (bot.py, строки 155-197)

```python
# Инициализируем и запускаем FastAPI сервер для Mini App
from miniapp.api.server import app, init_app
init_app(db, client_manager)

# Запускаем FastAPI сервер в отдельном потоке с отдельным event loop
def run_api_server():
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    # ... запуск uvicorn

api_thread = Thread(target=run_api_server, daemon=True)
api_thread.start()
```

### Зависимости API

API использует:
- ✅ **DatabaseInterface** - можно подключиться к той же БД через сеть Docker
- ✅ **YandexClientManager** - можно создать свой экземпляр с теми же токенами
- ✅ **Services** (PlaylistService, YandexService) - уже независимы от бота
- ❌ **НЕТ прямой зависимости от handlers бота** - API не общается с ботом напрямую

### Коммуникация

- API **НЕ общается напрямую с ботом**
- API использует только БД и сервисы
- Бот и API работают независимо, общаясь только через БД
- **Вывод**: API можно полностью вынести в отдельный контейнер!

## Цели

1. Создать отдельный контейнер для FastAPI сервера
2. Настроить независимую инициализацию API (БД, client_manager)
3. Обновить docker-compose.yml для запуска API в отдельном сервисе
4. Убрать запуск API из bot.py
5. Настроить сеть Docker для связи между контейнерами
6. Обновить nginx конфигурацию для проксирования к API контейнеру
7. Протестировать работу после разделения

## Преимущества

1. **Независимое масштабирование**: Можно масштабировать API и бота отдельно
2. **Независимые обновления**: Можно обновлять бота и API отдельно без перезапуска другого
3. **Изоляция ресурсов**: Проблемы в одном сервисе не влияют на другой
4. **Упрощение деплоя**: Можно деплоить изменения только в нужный сервис
5. **Улучшенный мониторинг**: Легче отслеживать метрики отдельно для API и бота
6. **Чистая архитектура**: Разделение ответственности на уровне инфраструктуры

## Архитектура после изменений

### Текущая архитектура

```
┌─────────────────┐
│  bot container  │
│  - aiogram bot  │
│  - FastAPI API  │ (в потоке)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  postgres DB    │
└─────────────────┘
```

### Новая архитектура

```
┌─────────────────┐     ┌─────────────────┐
│  bot container  │     │  api container   │
│  - aiogram bot  │     │  - FastAPI API   │
└────────┬────────┘     └────────┬─────────┘
         │                       │
         └───────────┬───────────┘
                     │
                     ▼
            ┌─────────────────┐
            │  postgres DB    │
            └─────────────────┘
```

## План реализации

### Этап 1: Создание отдельного entry point для API

- [ ] Создать `miniapp/api/main.py` - точку входа для запуска API
- [ ] Реализовать инициализацию БД в `main.py`
- [ ] Реализовать инициализацию YandexClientManager в `main.py`
- [ ] Реализовать запуск FastAPI сервера через uvicorn
- [ ] Добавить обработку сигналов для корректного завершения

**Пример структуры `miniapp/api/main.py`:**

```python
"""
Точка входа для запуска Mini App API в отдельном контейнере.
"""
import os
import logging
import asyncio
import signal
import sys
from dotenv import load_dotenv
import uvicorn

from database import create_database
from yandex_client_manager import YandexClientManager
from miniapp.api.server import app, init_app

load_dotenv()

# Логирование
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, LOG_LEVEL, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные переменные
db = None
client_manager = None


async def init():
    """Инициализация БД и зависимостей."""
    global db, client_manager
    
    # Создаем БД
    db = create_database()
    await db.init_db()
    
    # Создаем client_manager
    yandex_token = os.getenv("YANDEX_TOKEN")
    if not yandex_token:
        raise ValueError("YANDEX_TOKEN не установлен")
    
    client_manager = YandexClientManager(yandex_token, db)
    await client_manager.init_default_account()
    
    # Инициализируем FastAPI приложение
    init_app(db, client_manager)
    logger.info("Mini App API инициализирован")


def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения."""
    logger.info(f"Получен сигнал {signum}, завершаю работу API...")
    sys.exit(0)


async def main():
    """Главная функция."""
    try:
        # Регистрируем обработчики сигналов
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        logger.info("Запуск Mini App API...")
        
        # Инициализируем зависимости
        await init()
        
        # Получаем порт из переменных окружения
        api_port = int(os.getenv("MINIAPP_API_PORT", "8000"))
        api_host = os.getenv("MINIAPP_API_HOST", "0.0.0.0")
        
        logger.info(f"Запуск FastAPI сервера на {api_host}:{api_port}...")
        
        # Запускаем uvicorn
        config = uvicorn.Config(
            app,
            host=api_host,
            port=api_port,
            log_level="info" if log_level <= logging.INFO else "warning",
            loop="asyncio"
        )
        server = uvicorn.Server(config)
        await server.serve()
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания, завершаю работу...")
    except Exception as e:
        logger.exception(f"Критическая ошибка при запуске API: {e}")
        raise
    finally:
        if db:
            # Закрываем соединения с БД
            if hasattr(db, 'close'):
                await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("API остановлен пользователем")
```

### Этап 2: Создание Dockerfile для API

- [ ] Создать `miniapp/Dockerfile` для API контейнера
- [ ] Настроить копирование только необходимых файлов
- [ ] Настроить CMD для запуска `miniapp/api/main.py`

**Пример `miniapp/Dockerfile`:**

```dockerfile
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
```

### Этап 3: Обновление docker-compose.yml

- [ ] Добавить сервис `api` в docker-compose.yml
- [ ] Настроить переменные окружения для API
- [ ] Настроить зависимости (postgres)
- [ ] Настроить сеть для связи между контейнерами
- [ ] Обновить сервис `bot` (убрать запуск API)
- [ ] Обновить сервис `nginx` (проксирование к API контейнеру)

**Пример обновленного docker-compose.yml:**

```yaml
services:
  # ... postgres, pgadmin остаются без изменений ...
  
  bot:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ym_bot
    environment:
      TELEGRAM_TOKEN: ${TELEGRAM_TOKEN}
      YANDEX_TOKEN: ${YANDEX_TOKEN}
      DB_TYPE: ${DB_TYPE:-postgresql}
      DB_HOST: ${DB_HOST:-postgres}
      DB_PORT: ${DB_PORT:-5432}
      DB_NAME: ${POSTGRES_DB:-yandex_music_bot}
      DB_USER: ${POSTGRES_USER:-postgres}
      DB_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      MAINTENANCE_MODE: ${MAINTENANCE_MODE:-false}
      ADMIN_IDS: ${ADMIN_IDS:-}
      MINIAPP_URL: ${MINIAPP_URL:-}
      # УБРАТЬ: MINIAPP_API_PORT (больше не нужен в боте)
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - bot_network
    restart: unless-stopped

  api:
    build:
      context: .
      dockerfile: miniapp/Dockerfile
    container_name: ym_bot_api
    environment:
      YANDEX_TOKEN: ${YANDEX_TOKEN}
      DB_TYPE: ${DB_TYPE:-postgresql}
      DB_HOST: ${DB_HOST:-postgres}
      DB_PORT: ${DB_PORT:-5432}
      DB_NAME: ${POSTGRES_DB:-yandex_music_bot}
      DB_USER: ${POSTGRES_USER:-postgres}
      DB_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      MINIAPP_API_PORT: ${MINIAPP_API_PORT:-8000}
      MINIAPP_API_HOST: ${MINIAPP_API_HOST:-0.0.0.0}
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - bot_network
    restart: unless-stopped
    # Можно добавить healthcheck для API
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/playlists"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    container_name: ym_bot_nginx
    ports:
      - "80:80"
    volumes:
      - ./miniapp/static:/usr/share/nginx/html:ro
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - bot
      - api  # Добавить зависимость от API
    networks:
      - bot_network
    restart: unless-stopped
```

### Этап 4: Обновление bot.py

- [ ] Убрать импорт FastAPI и uvicorn из bot.py
- [ ] Убрать функцию `run_api_server()` и запуск API в потоке
- [ ] Убрать вызов `init_app()` для API
- [ ] Убрать переменную `MINIAPP_API_PORT` из окружения бота (если не используется)

**Изменения в bot.py:**

```python
# УБРАТЬ эти строки:
# from miniapp.api.server import app, init_app
# init_app(db, client_manager)
# def run_api_server(): ...
# api_thread = Thread(target=run_api_server, daemon=True)
# api_thread.start()
```

### Этап 5: Обновление nginx конфигурации

- [ ] Обновить `nginx/nginx.conf` для проксирования к API контейнеру
- [ ] Изменить `proxy_pass` с `http://bot:8000` на `http://api:8000`

**Пример обновленного nginx.conf:**

```nginx
server {
    listen 80;
    server_name _;
    
    # Раздача статики Mini App
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
        
        # CORS заголовки для Telegram
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
        add_header Access-Control-Allow-Headers "Content-Type, X-Telegram-Init-Data";
    }
    
    # Проксирование API запросов к API контейнеру
    location /api/ {
        proxy_pass http://api:8000;  # Изменить с bot на api
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # CORS заголовки
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
        add_header Access-Control-Allow-Headers "Content-Type, X-Telegram-Init-Data";
    }
}
```

### Этап 6: Тестирование

- [ ] Протестировать запуск всех контейнеров через `docker-compose up`
- [ ] Проверить, что бот работает без API
- [ ] Проверить, что API работает независимо
- [ ] Проверить, что API может подключиться к БД
- [ ] Проверить, что nginx проксирует запросы к API
- [ ] Протестировать Mini App через Telegram
- [ ] Проверить все эндпоинты API (`/api/playlists`, `/api/tracks`, и т.д.)

### Этап 7: Документация

- [ ] Обновить `docs/architecture/architecture.md` с новой архитектурой
- [ ] Обновить `docs/instructions/miniapp_local_testing.md` (если нужно)
- [ ] Обновить `README.md` с информацией о новых контейнерах
- [ ] Добавить информацию о переменных окружения для API

## Технические детали

### Переменные окружения для API

API контейнеру нужны следующие переменные:

```env
# Обязательные
YANDEX_TOKEN=<токен Яндекс.Музыки>
DB_TYPE=postgresql  # или sqlite
DB_HOST=postgres
DB_PORT=5432
DB_NAME=yandex_music_bot
DB_USER=postgres
DB_PASSWORD=postgres

# Опциональные
LOG_LEVEL=INFO
MINIAPP_API_PORT=8000
MINIAPP_API_HOST=0.0.0.0
```

### Сеть Docker

Все контейнеры должны быть в одной сети `bot_network` для связи:
- `bot` контейнер может обращаться к `postgres` по имени `postgres`
- `api` контейнер может обращаться к `postgres` по имени `postgres`
- `nginx` контейнер может обращаться к `api` по имени `api`

### Healthcheck для API

Можно добавить healthcheck для API контейнера:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/docs"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

## Потенциальные проблемы и решения

### Проблема 1: Дублирование зависимостей

**Проблема**: Бот и API используют одни и те же зависимости (БД, client_manager), но в разных контейнерах.

**Решение**: Это нормально! Каждый контейнер создает свой экземпляр, но подключается к одной БД. Это стандартная практика микросервисов.

### Проблема 2: Инициализация дефолтного аккаунта

**Проблема**: И бот, и API инициализируют дефолтный аккаунт в `client_manager.init_default_account()`.

**Решение**: Это безопасно - метод идемпотентный, можно вызывать несколько раз. Если аккаунт уже существует, он не создается заново.

### Проблема 3: Event loops для PostgreSQL

**Проблема**: В текущей реализации для PostgreSQL создаются отдельные pools для разных event loops.

**Решение**: Теперь каждый контейнер имеет свой event loop, поэтому каждый создаст свой pool. Это правильно и безопасно.

### Проблема 4: Порты

**Проблема**: API слушает на порту 8000 внутри контейнера, но не нужно пробрасывать его наружу (nginx проксирует).

**Решение**: Не пробрасывать порт 8000 наружу в docker-compose.yml. Nginx будет проксировать запросы к API через внутреннюю сеть Docker.

## Связанные файлы

- `bot.py` - убрать запуск API
- `miniapp/api/server.py` - остается без изменений
- `miniapp/api/routes.py` - остается без изменений
- `miniapp/api/main.py` - **новый файл**, точка входа для API
- `miniapp/Dockerfile` - **новый файл**, Dockerfile для API
- `docker-compose.yml` - добавить сервис `api`
- `nginx/nginx.conf` - обновить proxy_pass
- `docs/architecture/architecture.md` - обновить архитектуру
- `docs/tasks/pending/task-feature-miniapp-player.md` - обновить информацию о развертывании

## Ресурсы

- [Docker Compose Networking](https://docs.docker.com/compose/networking/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [Microservices Architecture](https://microservices.io/patterns/microservices.html)

