# Реализация музыкального плеера в Telegram Mini App

**Статус**: 🚧 В разработке  
**Приоритет**: 🟡 Средний  
**Категория**: Новые функции  
**Связанная задача**: `task-feature-auto-queue-update.md`

**Прогресс:** Этап 5/8 завершен ✅

## Описание

Реализация полноценного музыкального плеера в виде Telegram Mini App (Web App), который позволит воспроизводить треки из плейлистов Яндекс.Музыки прямо в Telegram. Плеер будет автоматически обновлять очередь при изменении плейлиста, решая проблему устаревшей очереди при воспроизведении через приложение Яндекс.Музыки.

## Цели

1. Создать веб-приложение (Mini App) с музыкальным плеером
2. Интегрировать плеер с ботом через Telegram Web App API
3. Реализовать воспроизведение треков через стриминг из Яндекс.Музыки
4. Обеспечить автоматическое обновление очереди при изменении плейлиста
5. Создать удобный UI для управления воспроизведением

## Стек технологий

### Frontend (Mini App)
- **HTML5** - структура приложения
- **CSS3** - стилизация (можно использовать CSS-переменные для темной темы Telegram)
- **Vanilla JavaScript** (ES6+) - логика плеера
  - **Fetch API** - для загрузки треков по частям (Range Requests)
  - **Blob URL** - для воспроизведения аудио с правильным Content-Type
  - **Telegram Web App API** - для взаимодействия с ботом
- **HTML5 Audio API** - для воспроизведения аудио
- **Web Workers** (опционально) - для фоновой загрузки треков

### Backend (интеграция с ботом)
- **Python** - существующий стек бота
- **aiogram 3.x** - для обработки Web App данных
- **FastAPI** - для REST API эндпоинтов (обязательно для Mini App)
- **Существующие сервисы**:
  - `YandexService` - для получения URL треков через `get_download_info()`
  - `PlaylistService` - для получения списка треков из плейлистов
  - `DatabaseInterface` - для работы с БД

### Инфраструктура
- **Docker** - для контейнеризации (добавить nginx для статики)
- **Nginx** - для раздачи статических файлов Mini App
- **HTTPS** - обязательно для Web Apps (Telegram требует HTTPS)

## Архитектура

### Структура проекта

```
Liza_patry_bot/
├── bot.py                          # Существующий бот
├── miniapp/                        # Новая папка для Mini App
│   ├── static/                     # Статические файлы
│   │   ├── index.html              # Главная страница Mini App
│   │   ├── css/
│   │   │   └── styles.css          # Стили плеера
│   │   ├── js/
│   │   │   ├── app.js              # Основная логика приложения
│   │   │   ├── player.js           # Класс для управления воспроизведением
│   │   │   ├── playlist.js         # Работа с плейлистами
│   │   │   └── telegram-api.js     # Обертка для Telegram Web App API
│   │   └── assets/                 # Изображения, иконки
│   ├── api/                        # REST API для Mini App
│   │   ├── __init__.py
│   │   ├── routes.py               # FastAPI роуты
│   │   └── auth.py                 # Аутентификация через Telegram Web App
│   └── handlers/                   # Обработчики для Web App данных (legacy, если нужно)
│       └── webapp.py               # Обработка данных от Mini App через sendData()
├── services/
│   └── ...                         # Существующие сервисы
├── handlers/
│   ├── keyboards.py               # Добавить кнопку Web App
│   └── ...                        # Существующие обработчики
└── docker-compose.yml              # Добавить nginx сервис
```

### Взаимодействие компонентов

```
┌─────────────────┐
│  Telegram User  │
└────────┬────────┘
         │
         │ Нажатие кнопки "Open"
         ▼
┌─────────────────┐
│  Mini App (Web) │◄────┐
│  - HTML/CSS/JS  │     │
│  - Player UI    │     │ HTTP/HTTPS
│  - Telegram API │     │ REST API
└────────┬────────┘     │
         │              │
         │ REST API     │
         │ (Fetch)      │
         │              │
         ▼              │
┌─────────────────┐     │
│  FastAPI Server │     │
│  (REST API)     │     │
│  - /api/playlists│    │
│  - /api/tracks   │    │
│  - /api/stream   │    │
└────────┬────────┘     │
         │              │
         │              │
         ▼              │
┌─────────────────┐     │
│  Telegram Bot   │     │
│  (aiogram)      │     │
│  - services/    │─────┘
│  - database/    │
└────────┬────────┘
         │
         │ API calls
         ▼
┌─────────────────┐
│  Yandex Music   │
│  API            │
└─────────────────┘
```

**Примечание:** Mini App взаимодействует с ботом через REST API (FastAPI), а не через `sendData()`. Это более гибкий и масштабируемый подход.

### Поток данных

1. **Инициализация Mini App:**
   - Пользователь нажимает кнопку "Open" в боте
   - Telegram открывает Mini App (HTML страница)
   - Mini App инициализирует Telegram Web App API
   - Mini App получает `initData` от Telegram (содержит информацию о пользователе)
   - Mini App отправляет запрос на `/api/playlists` с авторизацией через `initData`

2. **Получение плейлистов (REST API):**
   - Mini App отправляет `GET /api/playlists` с заголовком `X-Telegram-Init-Data`
   - FastAPI сервер проверяет подпись `initData` (Telegram Web App валидация)
   - Извлекает `user_id` из `initData`
   - Использует `PlaylistService` для получения списка плейлистов пользователя
   - Возвращает JSON с плейлистами

3. **Воспроизведение трека (REST API):**
   - Пользователь выбирает плейлист и трек в Mini App
   - Mini App запрашивает URL трека: `GET /api/tracks/{track_id}/stream?playlist_id={playlist_id}`
   - FastAPI сервер использует `YandexService` для получения `download_info`
   - Строит URL из `host` и `path` и возвращает JSON: `{url: "https://..."}`
   - Mini App использует Fetch API + Blob URL для стриминга

4. **Автоматическое обновление (Polling):**
   - Mini App периодически проверяет обновления плейлиста: `GET /api/playlists/{playlist_id}/tracks?revision={current_revision}`
   - **Интервал:** 10 секунд (настраивается)
   - **Умная проверка:** Проверка выполняется только когда текущий трек близок к концу очереди (последние 2-3 трека)
   - При обнаружении новых треков автоматически добавляются в конец очереди
   - Пользователь получает уведомление о новых треках

## Развертывание

### Локальная разработка

#### Вариант 1: Простой HTTP сервер + ngrok (для разработки)

```bash
# В папке miniapp/static
python -m http.server 8000

# В отдельном терминале - создаем HTTPS туннель
ngrok http 8000
# ngrok выдаст URL вида: https://xxxx-xx-xx-xx-xx.ngrok-free.app
```

**Важно:** Для тестирования Web App в Telegram **обязательно нужен HTTPS**. 

**Для разработки используем ngrok:**
- Установка: `brew install ngrok` (macOS) или скачать с [ngrok.com](https://ngrok.com)
- Регистрация бесплатна, дает HTTPS туннель
- Команда: `ngrok http 8000` - создает HTTPS URL
- Использовать полученный URL в кнопке Web App

**Альтернативы ngrok:**
- **localtunnel**: `npx localtunnel --port 8000` (бесплатно, но менее стабильно)
- **cloudflared**: `cloudflared tunnel --url http://localhost:8000` (от Cloudflare)

**Для прода:** Используем Let's Encrypt (см. раздел "Прод развертывание")

#### Вариант 2: FastAPI сервер для REST API + статика (рекомендуется для разработки)

Создать FastAPI приложение, которое раздает статику и предоставляет REST API:

```python
# miniapp/api/server.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Mini App API")

# CORS для Telegram
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздача статики
app.mount("/static", StaticFiles(directory="miniapp/static"), name="static")

# REST API роуты (см. miniapp/api/routes.py)
from miniapp.api.routes import router
app.include_router(router, prefix="/api")
```

Запуск:
```bash
# Установить зависимости
pip install fastapi uvicorn python-multipart

# Запустить сервер
uvicorn miniapp.api.server:app --host 0.0.0.0 --port 8000 --reload

# В отдельном терминале - ngrok
ngrok http 8000
```

**Преимущества:**
- Один сервер для статики и API
- Легко тестировать локально
- Готово к интеграции с ботом

### Прод развертывание

#### Вариант 1: Nginx в Docker (рекомендуется)

Добавить nginx сервис в `docker-compose.yml`:

```yaml
services:
  nginx:
    image: nginx:alpine
    container_name: ym_bot_nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./miniapp/static:/usr/share/nginx/html/miniapp:ro
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro  # SSL сертификаты
    depends_on:
      - bot
    networks:
      - bot_network
    restart: unless-stopped
```

Конфигурация nginx (`nginx/nginx.conf`):
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Редирект на HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL сертификаты от Let's Encrypt (см. раздел "Получение SSL сертификата")
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # Раздача статики Mini App
    location /miniapp/ {
        alias /usr/share/nginx/html/miniapp/;
        try_files $uri $uri/ /miniapp/index.html;
        
        # CORS заголовки для Telegram
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
        add_header Access-Control-Allow-Headers "Content-Type";
    }
    
    # Проксирование API запросов к FastAPI серверу
    location /api/ {
        proxy_pass http://bot:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Вариант 2: Статический хостинг (альтернатива)

Можно использовать внешний хостинг для статики:
- **GitHub Pages** - бесплатный хостинг для статики
- **Netlify** - с поддержкой HTTPS
- **Vercel** - быстрый деплой
- **Cloudflare Pages** - с CDN

**Важно:** URL должен быть доступен по HTTPS и иметь валидный SSL сертификат.

## REST API для Mini App

### Структура API

Mini App взаимодействует с ботом через REST API на базе FastAPI. Все эндпоинты требуют авторизации через Telegram Web App `initData`.

**Базовый URL:** `https://your-domain.com/api`

### Эндпоинты

#### 1. Получение списка плейлистов
```
GET /api/playlists
Headers:
  X-Telegram-Init-Data: <telegram_init_data>

Response:
{
  "playlists": [
    {
      "id": 1,
      "title": "Мой плейлист",
      "track_count": 15,
      "cover_url": "https://...",
      "is_shared": false
    }
  ]
}
```

#### 2. Получение треков из плейлиста
```
GET /api/playlists/{playlist_id}/tracks?revision={revision}
Headers:
  X-Telegram-Init-Data: <telegram_init_data>

Response:
{
  "tracks": [
    {
      "id": 123456,
      "title": "Название трека",
      "artists": ["Артист 1", "Артист 2"],
      "duration": 180,
      "position": 0
    }
  ],
  "revision": 42
}
```

#### 3. Получение URL трека для стриминга
```
GET /api/tracks/{track_id}/stream?playlist_id={playlist_id}
Headers:
  X-Telegram-Init-Data: <telegram_init_data>

Response:
{
  "url": "https://api.music.yandex.net/get-mp3/...",
  "expires_at": "2025-12-07T12:00:00Z"
}
```

#### 4. Проверка обновлений плейлиста (для polling)
```
GET /api/playlists/{playlist_id}/updates?revision={current_revision}
Headers:
  X-Telegram-Init-Data: <telegram_init_data>

Response:
{
  "has_updates": true,
  "new_tracks_count": 3,
  "new_revision": 45,
  "new_tracks": [...]
}
```

### Авторизация

Все запросы должны содержать заголовок `X-Telegram-Init-Data` с данными от Telegram Web App. Сервер проверяет подпись данных для валидации.

```python
# miniapp/api/auth.py
import hmac
import hashlib
from urllib.parse import parse_qsl

def validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """Валидация initData от Telegram Web App."""
    # Парсим данные
    parsed_data = dict(parse_qsl(init_data))
    
    # Извлекаем hash
    received_hash = parsed_data.pop('hash', '')
    
    # Создаем строку для проверки
    data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
    
    # Вычисляем секретный ключ
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode(),
        digestmod=hashlib.sha256
    ).digest()
    
    # Вычисляем hash
    calculated_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()
    
    # Проверяем
    if calculated_hash != received_hash:
        raise ValueError("Invalid initData signature")
    
    return parsed_data
```

## Взаимодействие с ботом

### 1. REST API сервер (FastAPI)

Создать FastAPI приложение в `miniapp/api/routes.py`:

```python
# miniapp/api/routes.py
from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import Optional
import os

from miniapp.api.auth import validate_telegram_init_data
from services.playlist_service import PlaylistService
from services.yandex_service import YandexService
from yandex_client_manager import YandexClientManager
from database import DatabaseInterface

router = APIRouter()

# Зависимости
async def get_user_id(x_telegram_init_data: str = Header(...)) -> int:
    """Извлекает user_id из initData."""
    bot_token = os.getenv("TELEGRAM_TOKEN")
    try:
        data = validate_telegram_init_data(x_telegram_init_data, bot_token)
        user_id = int(data.get('user', {}).get('id'))
        return user_id
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid initData")

@router.get("/playlists")
async def get_playlists(
    user_id: int = Depends(get_user_id),
    db: DatabaseInterface = Depends(get_db),
    playlist_service: PlaylistService = Depends(get_playlist_service)
):
    """Получить список доступных плейлистов пользователя."""
    # Получаем плейлисты из БД
    user_playlists = await db.get_user_playlists(user_id)
    shared_playlists = await db.get_shared_playlists(user_id)
    
    # Форматируем для ответа
    playlists = []
    for pl in user_playlists + shared_playlists:
        playlists.append({
            "id": pl["id"],
            "title": pl["title"],
            "track_count": await playlist_service.get_playlist_tracks_count(pl["id"], user_id) or 0,
            "cover_url": pl.get("cover_url"),
            "is_shared": pl.get("creator_id") != user_id
        })
    
    return {"playlists": playlists}

@router.get("/playlists/{playlist_id}/tracks")
async def get_playlist_tracks(
    playlist_id: int,
    revision: Optional[int] = None,
    user_id: int = Depends(get_user_id),
    playlist_service: PlaylistService = Depends(get_playlist_service)
):
    """Получить список треков из плейлиста."""
    tracks = await playlist_service.get_playlist_tracks(playlist_id, user_id)
    if tracks is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Форматируем треки
    formatted_tracks = []
    for i, track_item in enumerate(tracks):
        from services.yandex_service import YandexService
        client = await get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        formatted_tracks.append({
            "id": yandex_service.extract_track_info(track_item)[0],
            "title": yandex_service.format_track(track_item),
            "artists": yandex_service.get_track_artists(track_item),
            "duration": getattr(track_item.track if hasattr(track_item, 'track') else track_item, 'duration_ms', 0) // 1000,
            "position": i
        })
    
    # Получаем revision из плейлиста
    pl_obj = await playlist_service.get_playlist_object(playlist_id, user_id)
    current_revision = getattr(pl_obj, 'revision', None) if pl_obj else None
    
    return {
        "tracks": formatted_tracks,
        "revision": current_revision
    }

@router.get("/tracks/{track_id}/stream")
async def get_track_stream_url(
    track_id: int,
    playlist_id: int,
    user_id: int = Depends(get_user_id),
    playlist_service: PlaylistService = Depends(get_playlist_service),
    client_manager: YandexClientManager = Depends(get_client_manager)
):
    """Получить URL трека для стриминга."""
    # Получаем клиент и сервис
    client = await client_manager.get_client_for_playlist(playlist_id)
    yandex_service = YandexService(client)
    
    # Получаем трек
    track = await asyncio.to_thread(yandex_service.get_track, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    
    # Получаем download_info и строим URL (см. раздел "Технические детали")
    url = await _build_streaming_url(track, yandex_service)
    
    return {"url": url}
```

### 2. Добавление кнопки Web App

Обновить `handlers/keyboards.py`:

```python
from aiogram.types import KeyboardButton, WebAppInfo

def get_main_menu_keyboard(web_app_url: str = None):
    """Возвращает клавиатуру главного меню с кнопкой Web App."""
    keyboard = [
        [
            KeyboardButton(text="📁 Мои плейлисты"),
            KeyboardButton(text="📂 Общие плейлисты")
        ],
        [
            KeyboardButton(text="➕ Создать плейлист"),
            KeyboardButton(text="📋 Список треков")
        ],
    ]
    
    # Добавляем кнопку Web App, если URL указан
    if web_app_url:
        keyboard.append([
            KeyboardButton(
                text="🎵 Открыть плеер",
                web_app=WebAppInfo(url=web_app_url)
            )
        ])
    
    keyboard.append([
        KeyboardButton(text="ℹ️ Информация"),
        KeyboardButton(text="🏠 Главное меню")
    ])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
```

### 3. Интеграция с сервисами

Использовать существующие сервисы для получения данных:

```python
# В handlers/webapp.py
from services.yandex_service import YandexService
from services.playlist_service import PlaylistService

async def _get_track_streaming_url(self, track_id: int, playlist_id: int):
    """Получить URL трека для стриминга."""
    # Получаем клиент для плейлиста
    client = await self.client_manager.get_client_for_playlist(playlist_id)
    yandex_service = YandexService(client)
    
    # Получаем трек
    track = await asyncio.to_thread(yandex_service.get_track, track_id)
    if not track:
        return None
    
    # Получаем download_info
    download_info = await asyncio.to_thread(track.get_download_info)
    if not download_info:
        return None
    
    # Строим URL из host и path (как в test_download_tracks.py)
    host = download_info.get('host') or download_info.get('download_info', {}).get('host')
    path = download_info.get('path') or download_info.get('download_info', {}).get('path')
    
    if host and path:
        # Обработка XML, если нужно
        if isinstance(host, str) and host.startswith('<'):
            # Парсим XML (как в test_download_tracks.py)
            host, path = self._extract_url_from_xml(host)
        
        url = f"https://{host}{path}"
        return url
    
    return None
```

## Поэтапный план реализации

### Этап 1: Инфраструктура и базовая структура (MVP) ✅ ЗАВЕРШЕН

- [x] Создать структуру папок `miniapp/static/`
- [x] Создать базовый `index.html` с подключением Telegram Web App API
- [x] Создать `miniapp/static/js/telegram-api.js` - обертка для Telegram API
- [x] Настроить локальную разработку (HTTP сервер + ngrok для HTTPS) - инструкции в `miniapp/README.md`
- [x] Добавить кнопку Web App в главное меню бота (`handlers/keyboards.py`)
- [x] Создать обработчик `handlers/webapp.py` для приема данных от Mini App
- [x] Зарегистрировать обработчик в `bot.py`
- [x] Создать `miniapp/README.md` с инструкциями по разработке

**Результат:** ✅ Mini App открывается, может отправлять и получать данные от бота через `sendData()`. Базовая инфраструктура готова.

**Дата завершения:** 2025-12-07

### Этап 2: Базовый плеер ✅ ЗАВЕРШЕН

- [x] Создать `miniapp/static/js/player.js` - класс для управления воспроизведением
- [x] Реализовать загрузку трека через Fetch API с Range Requests
- [x] Реализовать создание Blob URL с правильным Content-Type
- [x] Реализовать базовое воспроизведение (play/pause)
- [x] Добавить UI элементы (кнопки play/pause, прогресс-бар)
- [x] Создать `miniapp/static/css/styles.css` с базовыми стилями
- [x] Интегрировать с ботом: получение URL трека через `YandexService`
- [x] Добавить обновление прогресс-бара и времени воспроизведения
- [x] Добавить перемотку трека при клике на прогресс-бар
- [x] Добавить отображение списка треков и плейлистов

**Результат:** ✅ Базовый плеер реализован. Можно воспроизводить треки, управлять воспроизведением (play/pause), перематывать трек. UI обновляется в реальном времени. Интеграция с ботом через `sendData()` для получения URL треков.

**Примечание:** В текущей реализации URL треков получаются через сообщения от бота (через `sendData()`). В следующих этапах будет реализован REST API для более удобного взаимодействия.

**Дата завершения:** 2025-12-07

### Этап 2.1: Настройка локального тестирования ✅ ЗАВЕРШЕН

- [x] Добавить nginx в `docker-compose.yml` для раздачи статики Mini App
- [x] Создать конфигурацию `nginx/nginx.conf` с CORS заголовками
- [x] Добавить переменную `MINIAPP_URL` в окружение бота
- [x] Создать инструкцию `docs/instructions/miniapp_local_testing.md` для локального тестирования
- [x] Добавить поддержку альтернативных туннелей для РФ (xTunnel, localhost.run, bore.pub)
- [x] Протестировать запуск через Docker Compose

**Результат:** ✅ Настроена инфраструктура для локального тестирования Mini App через Docker. Создана подробная инструкция с поддержкой различных туннелей для доступа из РФ.

**Дата завершения:** 2025-12-07

### Этап 3: REST API и работа с плейлистами ✅ ЗАВЕРШЕН

- [x] Создать структуру REST API (`miniapp/api/`)
- [x] Реализовать авторизацию через Telegram initData
- [x] Создать эндпоинты: `/api/playlists`, `/api/playlists/{id}/tracks`, `/api/tracks/{id}/stream`
- [x] Интегрировать FastAPI сервер с ботом (параллельный запуск)
- [x] Обновить Mini App для использования REST API вместо `sendData()`
- [x] Реализовать получение списка доступных плейлистов через REST API
- [x] Реализовать выбор плейлиста в UI
- [x] Реализовать получение списка треков из выбранного плейлиста через REST API
- [x] Реализовать отображение списка треков в Mini App
- [x] Реализовать выбор трека для воспроизведения
- [x] Интегрировать с `PlaylistService` для получения данных
- [x] Исправить проблемы с event loops (отдельные pools для PostgreSQL)
- [x] Убрать отладочную информацию из кода

**Результат:** ✅ Mini App работает через REST API. Можно выбрать плейлист и трек для воспроизведения. Плейлисты и треки загружаются через REST API без закрытия Mini App.

**Дата завершения:** 2025-12-08

**Известные проблемы и доработки:** См. [task-feature-miniapp-player-fixes.md](task-feature-miniapp-player-fixes.md)

### Этап 4: Очередь воспроизведения

- [x] Реализовать очередь треков (массив треков)
- [x] Реализовать автоматический переход к следующему треку
- [x] Реализовать кнопки "Следующий" / "Предыдущий"
- [x] Реализовать отображение текущего трека в очереди
- [x] Реализовать индикатор прогресса воспроизведения
- [x] Добавить отображение названия трека и артистов

**Результат:** ✅ Полноценная очередь воспроизведения с навигацией.

**Дата завершения:** 2025-12-08

**Дополнительно реализовано:**
- ✅ Исправлено отображение названия трека (показывался ID вместо названия)
- ✅ Исправлена кнопка паузы (показывала песочные часы и не работала)
- ✅ Реализован Media Session API для нативного плеера (iOS/Android)
  - Отображение названия трека, артистов и обложки на экране блокировки
  - Кнопки переключения треков на нативном плеере
- ✅ Добавлены кнопки play/pause в список треков
- ✅ Унифицированы иконки (заменены эмодзи на простые Unicode символы)
- ✅ Добавлена обложка трека в API ответ

### Этап 5: Автоматическое обновление очереди

- [x] Реализовать периодическую проверку обновлений плейлиста (polling)
  - **Интервал:** 10 секунд (настраивается через конфиг)
  - **Умная проверка:** Проверка выполняется только когда текущий трек близок к концу очереди (последние 2-3 трека)
  - **Оптимизация:** Если очередь не близка к концу, проверка не выполняется
- [x] Реализовать сравнение текущей очереди с актуальным состоянием плейлиста (через revision)
- [x] Реализовать автоматическое добавление новых треков в конец очереди
- [x] Реализовать уведомления о новых треках (toast-уведомление в UI)
- [x] Реализовать эндпоинт `/api/playlists/{id}/updates` для проверки обновлений

**Результат:** ✅ Очередь автоматически обновляется при изменении плейлиста, проверка выполняется только когда нужно.

**Дата завершения:** 2025-12-11

**Реализовано:**
- ✅ Класс `PlaylistUpdater` для периодической проверки обновлений
- ✅ Умная проверка: только когда осталось 2-3 трека до конца очереди
- ✅ Автоматическое добавление новых треков в конец очереди
- ✅ Фильтрация дубликатов (треки, которые уже есть в очереди, не добавляются)
- ✅ Toast-уведомления о новых треках
- ✅ Синхронизация revision между updater и основным приложением
- ✅ Ручная проверка обновлений при достижении конца очереди (в `playNext`)
- ✅ Эндпоинт `/api/playlists/{id}/updates` уже был реализован ранее

**Реализация polling:**
```javascript
// miniapp/static/js/playlist.js
class PlaylistUpdater {
    constructor(playlistId, currentRevision, queue) {
        this.playlistId = playlistId;
        this.currentRevision = currentRevision;
        this.queue = queue;
        this.checkInterval = 10000; // 10 секунд
        this.intervalId = null;
    }
    
    start() {
        this.intervalId = setInterval(() => {
            this.checkForUpdates();
        }, this.checkInterval);
    }
    
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }
    
    async checkForUpdates() {
        // Проверяем, близок ли текущий трек к концу очереди
        const currentIndex = this.queue.currentIndex;
        const queueLength = this.queue.tracks.length;
        const remainingTracks = queueLength - currentIndex;
        
        // Проверяем только если осталось 2-3 трека или меньше
        if (remainingTracks > 3) {
            return; // Не проверяем, если очередь еще длинная
        }
        
        try {
            const response = await fetch(
                `/api/playlists/${this.playlistId}/updates?revision=${this.currentRevision}`,
                {
                    headers: {
                        'X-Telegram-Init-Data': window.Telegram.WebApp.initData
                    }
                }
            );
            
            const data = await response.json();
            
            if (data.has_updates && data.new_tracks.length > 0) {
                // Добавляем новые треки в конец очереди
                this.queue.addTracks(data.new_tracks);
                this.currentRevision = data.new_revision;
                
                // Показываем уведомление
                this.showNotification(`Добавлено ${data.new_tracks_count} новых треков`);
            }
        } catch (error) {
            console.error('Ошибка при проверке обновлений:', error);
        }
    }
}
```

### Этап 6: UI/UX улучшения

- [x] Добавить темную тему (соответствующую Telegram)
- [x] Добавить отображение обложек треков/плейлистов
- [x] Добавить управление громкостью
- [x] Добавить перемотку трека (seek)
- [x] Добавить режимы воспроизведения (повтор, перемешивание)
- [x] Добавить анимации и переходы
- [x] Адаптивный дизайн для разных размеров экрана

**Результат:** Красивый и удобный интерфейс плеера.

**Реализовано:**
- Темная тема интегрирована с Telegram Web App API (автоматическое определение темы через `colorScheme` и `themeParams`)
- Обложки плейлистов отображаются в списке плейлистов
- Обложки треков в списке треков отображаются корректно
- Улучшенная перемотка трека с визуальным индикатором (handle) и поддержкой перетаскивания
- Режимы воспроизведения: перемешивание (shuffle) и повтор (none/all/one) - работают корректно
- Плавные анимации для появления элементов (fadeIn, slideIn)
- Адаптивный дизайн для мобильных устройств (до 480px) и планшетов (от 768px)

**Известные проблемы:**
- Обложка трека в плеере не отображается (требует дополнительной отладки)

### Этап 7: Развертывание на прод

- [x] Настроить nginx для раздачи статики (локально)
- [x] Обновить `docker-compose.yml` с nginx сервисом
- [ ] Получить SSL сертификат через Let's Encrypt (см. раздел "Получение SSL сертификата")
- [ ] Обновить `Dockerfile` (если нужно)
- [ ] Настроить переменные окружения для URL Mini App на проде
- [ ] Протестировать на прод сервере
- [ ] Обновить URL Web App в BotFather (если используется кнопка "Open")

**Результат:** Mini App доступен по HTTPS на прод сервере.

**Примечание:** В текущей реализации API запускается внутри бота в отдельном потоке. Планируется вынос API в отдельный контейнер для улучшения архитектуры и независимого масштабирования. См. [task-tech-separate-api-container.md](task-tech-separate-api-container.md).

## Получение SSL сертификата

### Для разработки (локально)

**Используем ngrok** - самый простой способ получить HTTPS для разработки:

1. **Установка ngrok:**
   ```bash
   # macOS
   brew install ngrok
   
   # Или скачать с https://ngrok.com
   ```

2. **Регистрация (бесплатно):**
   - Зарегистрироваться на [ngrok.com](https://ngrok.com)
   - Получить authtoken
   - Выполнить: `ngrok config add-authtoken <your-token>`

3. **Запуск туннеля:**
   ```bash
   # Запускаем локальный сервер (например, FastAPI на порту 8000)
   uvicorn miniapp.api.server:app --port 8000
   
   # В отдельном терминале - создаем HTTPS туннель
   ngrok http 8000
   ```

4. **Использование:**
   - ngrok выдаст URL вида: `https://xxxx-xx-xx-xx-xx.ngrok-free.app`
   - Этот URL можно использовать в кнопке Web App
   - **Важно:** URL меняется при каждом перезапуске ngrok (в бесплатной версии)
   - Для стабильного URL нужна платная подписка или использование домена

**Альтернативы ngrok:**
- **localtunnel**: `npx localtunnel --port 8000` (бесплатно, но менее стабильно)
- **cloudflared**: `cloudflared tunnel --url http://localhost:8000` (от Cloudflare, бесплатно)

### Для продакшена (Let's Encrypt)

**Let's Encrypt** - бесплатный SSL сертификат, автоматическое обновление.

#### Вариант 1: Certbot (рекомендуется)

1. **Установка certbot:**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install certbot python3-certbot-nginx
   
   # macOS
   brew install certbot
   ```

2. **Получение сертификата:**
   ```bash
   # Если nginx уже настроен
   sudo certbot --nginx -d your-domain.com
   
   # Или только получение сертификата (без настройки nginx)
   sudo certbot certonly --standalone -d your-domain.com
   ```

3. **Автоматическое обновление:**
   - Certbot автоматически настраивает cron для обновления сертификатов
   - Сертификаты обновляются автоматически за 30 дней до истечения

4. **Пути к сертификатам:**
   ```
   /etc/letsencrypt/live/your-domain.com/fullchain.pem
   /etc/letsencrypt/live/your-domain.com/privkey.pem
   ```

#### Вариант 2: Docker с certbot

Можно использовать Docker контейнер для получения и обновления сертификатов:

```yaml
# docker-compose.yml
services:
  certbot:
    image: certbot/certbot
    volumes:
      - ./letsencrypt:/etc/letsencrypt
      - ./letsencrypt-var:/var/lib/letsencrypt
    command: certonly --standalone -d your-domain.com --email your@email.com --agree-tos --non-interactive
```

#### Вариант 3: Cloudflare (если используете Cloudflare DNS)

Если домен использует Cloudflare DNS, можно использовать их бесплатный SSL:
- Включить "Full" или "Full (strict)" режим SSL в настройках Cloudflare
- Cloudflare автоматически предоставляет SSL сертификат

**Требования для Let's Encrypt:**
- Домен должен быть доступен из интернета
- Порты 80 и 443 должны быть открыты
- Домен должен указывать на IP сервера (A-запись)

**Сложность:** Не сложно! Certbot делает все автоматически. Основная сложность - настройка DNS и открытие портов.

### Этап 8: Дополнительные функции (опционально)

- [ ] Реализовать избранные треки
- [ ] Реализовать историю воспроизведения
- [ ] Реализовать поиск по трекам в плейлисте
- [ ] Реализовать сортировку треков
- [ ] Реализовать работу в фоне (через Service Workers)
- [ ] Добавить поддержку плейлистов с большим количеством треков (пагинация)

## Технические детали

### Получение URL трека для стриминга

Использовать логику из `tools/test_download_tracks.py`:

```python
# Получаем download_info
download_info = track.get_download_info()

# Извлекаем host и path (может быть в разных форматах)
host = download_info.host or download_info.download_info.host
path = download_info.path or download_info.download_info.path

# Если это XML, парсим
if isinstance(host, str) and host.startswith('<'):
    # Парсим XML и извлекаем host и path
    host, path = extract_from_xml(host)

# Строим URL
url = f"https://{host}{path}"
```

### Fetch API + Blob URL для стриминга

```javascript
// Загружаем первые байты для быстрого старта
const response = await fetch(url, {
    headers: {
        'Range': 'bytes=0-1048576' // Первый 1MB
    }
});

const blob = await response.blob();

// Создаем Blob URL с правильным типом
const blobUrl = URL.createObjectURL(
    new Blob([blob], { type: 'audio/mpeg' })
);

// Используем в Audio элементе
const audio = new Audio(blobUrl);
audio.play();
```

### Telegram Web App API

```javascript
// Инициализация
window.Telegram.WebApp.ready();

// Отправка данных боту
window.Telegram.WebApp.sendData(JSON.stringify({
    action: 'get_playlists'
}));

// Получение данных от бота (через события или ответы)
// Telegram автоматически передает данные через window.Telegram.WebApp.initData
```

## Переменные окружения

Добавить в `.env`:

```env
# URL Mini App (для кнопки Web App)
MINIAPP_URL=https://your-domain.com/miniapp/

# Порт для HTTP сервера Mini App (для локальной разработки)
MINIAPP_PORT=8080
```

## Связанные файлы

- `services/yandex_service.py` - получение URL треков
- `services/playlist_service.py` - работа с плейлистами
- `handlers/keyboards.py` - добавление кнопки Web App
- `handlers/webapp.py` - обработка данных от Mini App
- `miniapp/static/` - статические файлы Mini App (HTML, CSS, JS)
- `nginx/nginx.conf` - конфигурация nginx для раздачи статики
- `docker-compose.yml` - конфигурация Docker Compose (добавлен nginx сервис)
- `docs/instructions/miniapp_local_testing.md` - инструкция по локальному тестированию
- `tools/test_download_tracks.py` - пример работы с download_info
- `docs/tasks/pending/task-feature-auto-queue-update.md` - исходная задача
- `docs/research/telegram_music_player_research.md` - исследование возможностей

## Ресурсы

- [Telegram Bot API - Web Apps](https://core.telegram.org/bots/webapps)
- [Telegram Mini Apps Documentation](https://core.telegram.org/bots/api#inline-mode)
- [HTML5 Audio API](https://developer.mozilla.org/en-US/docs/Web/API/HTMLAudioElement)
- [Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API)
- [Blob URL](https://developer.mozilla.org/en-US/docs/Web/API/URL/createObjectURL)

## Совместимость с движками Telegram

### Какие движки использует Telegram?

Telegram Mini Apps работают на разных платформах с разными веб-движками:

- **Android:** WebView на базе Chromium (современные версии)
- **iOS:** WKWebView (WebKit) - Safari движок
- **Desktop (Windows/macOS/Linux):** Встроенный браузер на базе Chromium
- **Web версия:** Обычный браузер пользователя

### Критичность для нашей задачи

**Низкая критичность** - все движки поддерживают необходимые технологии:

✅ **HTML5 Audio API** - поддерживается везде  
✅ **Fetch API** - поддерживается везде  
✅ **Blob URL** - поддерживается везде  
✅ **Range Requests** - поддерживается везде  
✅ **ES6+ JavaScript** - поддерживается везде  

**Что нужно учесть:**

1. **Префиксы для аудио форматов:**
   - MP3 поддерживается везде
   - Но лучше явно указывать `type: 'audio/mpeg'` при создании Blob

2. **CORS заголовки:**
   - Все движки требуют правильные CORS заголовки
   - Уже учтено в настройке FastAPI/Nginx

3. **Telegram Web App API:**
   - Работает одинаково на всех платформах
   - Единственное отличие - размеры экрана (учитывается в адаптивном дизайне)

**Вывод:** Не нужно делать специальные проверки для разных движков. Стандартные веб-технологии работают везде одинаково.

## Онлайн и офлайн режимы

### Текущая реализация (онлайн)

- Все треки стримятся напрямую из Яндекс.Музыки
- Нет кэширования на устройстве
- Требуется постоянное подключение к интернету

### Будущая реализация (офлайн) - в планах

При проектировании архитектуры учитываем возможность добавления офлайн режима:

1. **Кэширование треков:**
   - Использовать IndexedDB для хранения загруженных треков
   - Кэшировать треки при первом воспроизведении
   - Ограничение по размеру кэша (например, 500MB)

2. **Service Workers:**
   - Для фоновой загрузки треков
   - Для работы в офлайн режиме

3. **Синхронизация:**
   - При восстановлении соединения синхронизировать изменения
   - Обновлять кэш при изменении плейлиста

**Важно:** Архитектура должна быть готова к добавлению офлайн режима, но сейчас фокус на онлайн режиме.

## Вопросы для уточнения

- [x] Какой домен будет использоваться для Mini App? (определится при развертывании)
- [x] Нужен ли REST API для Mini App? ✅ **Да, REST API обязателен**
- [x] Как часто проверять обновления плейлиста? ✅ **10 секунд, только в конце очереди**
- [x] Нужна ли поддержка офлайн режима? ✅ **Пока нет, но архитектура готова**
- [x] Какие браузеры нужно поддерживать? ✅ **Все движки Telegram поддерживают нужные технологии**

