# Локальное тестирование Mini App через Docker

Пошаговая инструкция для запуска и тестирования Mini App локально через Docker.

## Предварительные требования

1. **Docker и Docker Compose** установлены

2. **Выберите один из вариантов для HTTPS туннеля** (Telegram требует HTTPS):

   ### Вариант 1: cloudflared (Cloudflare Tunnel) ⭐ РЕКОМЕНДУЕТСЯ для РФ
   
   **Работает из России, бесплатный, стабильный:**
   
   ```bash
   # macOS
   brew install cloudflared
   
   # Linux
   # Скачайте с https://github.com/cloudflare/cloudflared/releases
   ```
   
   **Преимущества:**
   - ✅ Работает из РФ без проблем
   - ✅ Бесплатный
   - ✅ Стабильный
   - ✅ Не требует регистрации для базового использования
   
   ### Вариант 2: xTunnel (российский сервис)
   
   **Российский аналог ngrok:**
   
   - Зарегистрируйтесь на [xtunnel.ru](https://xtunnel.ru)
   - Установите клиент согласно инструкциям на сайте
   
   **Преимущества:**
   - ✅ Российский сервис, точно работает из РФ
   - ✅ Бесплатный тариф доступен
   
   ### Вариант 3: Tuna (российский аналог ngrok)
   
   - Зарегистрируйтесь на [tuna.ru](https://tuna.ru) (если доступен)
   - Установите клиент согласно инструкциям
   
   **Примечание:** На бесплатном тарифе туннель может быть ограничен 30 минутами
   
   ### Вариант 4: ngrok (если доступен)
   
   ```bash
   # macOS
   brew install ngrok
   
   # Регистрация на ngrok.com
   ngrok config add-authtoken <your-token>
   ```
   
   **Примечание:** ngrok может быть недоступен или затруднен из РФ

## Шаг 1: Подготовка переменных окружения

Создайте файл `.env` в корне проекта (если его еще нет):

```env
# Telegram Bot Token
TELEGRAM_TOKEN=your_telegram_bot_token

# Yandex Music Token
YANDEX_TOKEN=your_yandex_token

# Database settings
DB_TYPE=postgresql
DB_HOST=postgres
DB_PORT=5432
DB_NAME=yandex_music_bot
DB_USER=postgres
DB_PASSWORD=postgres

# Mini App URL (будет заполнен после запуска туннеля: cloudflared/xTunnel/ngrok)
MINIAPP_URL=

# Дополнительные настройки (опционально)
LOG_LEVEL=INFO
MAINTENANCE_MODE=false
ADMIN_IDS=
```

**Важно:** `MINIAPP_URL` пока оставьте пустым - заполним после запуска туннеля.

## Шаг 2: Запуск Docker контейнеров

Запустите бота и PostgreSQL через Docker Compose:

```bash
# Из корня проекта
docker compose up -d
```

Проверьте, что контейнеры запущены:

```bash
docker compose ps
```

Должны быть запущены:
- `ym_bot_postgres` (PostgreSQL)
- `ym_bot_pgadmin` (pgAdmin, опционально)
- `ym_bot` (бот)

## Шаг 3: Запуск nginx для раздачи статики Mini App

### Вариант A: nginx в Docker (рекомендуется)

Nginx уже добавлен в `docker compose.yml` и настроен для раздачи статики из `miniapp/static/`.

Проверьте, что nginx запущен:

```bash
docker compose ps nginx
```

Если nginx не запущен, запустите:

```bash
docker compose up -d nginx
```

### Вариант B: nginx на хосте (альтернатива)

Если хотите запустить nginx на хосте:

1. Установите nginx:
   ```bash
   # macOS
   brew install nginx
   ```

2. Создайте конфигурацию `nginx.conf`:
   ```nginx
   server {
       listen 8080;
       server_name localhost;
       
       location / {
           root /path/to/ym-playlist-bot/miniapp/static;
           index index.html;
           try_files $uri $uri/ /index.html;
           
           # CORS заголовки для Telegram
           add_header Access-Control-Allow-Origin *;
           add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
           add_header Access-Control-Allow-Headers "Content-Type";
       }
   }
   ```

3. Запустите nginx:
   ```bash
   nginx -c /path/to/nginx.conf
   ```

## Шаг 4: Создание HTTPS туннеля

**Важно:** Telegram требует HTTPS для Web Apps. Выберите один из вариантов ниже.

### Вариант 1: cloudflared (может не работать из РФ)

1. **Запустите cloudflared** (в отдельном терминале):

   Если используете nginx в Docker (порт 80):
   ```bash
   cloudflared tunnel --url http://localhost:80
   ```

   Если используете nginx на хосте (порт 8080):
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```

   **Если не подключается**, попробуйте другой протокол:
   ```bash
   cloudflared tunnel --url http://localhost:80 --protocol http2
   ```

2. **Скопируйте HTTPS URL** из вывода:

   Вы увидите что-то вроде:
   ```
   +--------------------------------------------------------------------------------------------+
   |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable): |
   |  https://xxxx-xx-xx-xx-xx.trycloudflare.com                                               |
   +--------------------------------------------------------------------------------------------+
   ```

   Скопируйте URL: `https://xxxx-xx-xx-xx-xx.trycloudflare.com`

3. **Проверьте доступность URL**:
   ```bash
   curl -I https://xxxx-xx-xx-xx-xx.trycloudflare.com
   ```
   
   **Если получаете ошибку 530 или timeout:** cloudflared может быть заблокирован в вашем регионе. Попробуйте альтернативные варианты ниже (xTunnel, localhost.run, bore.pub).

4. **Обновите переменную окружения `MINIAPP_URL`**:

   Отредактируйте `.env`:
   ```env
   MINIAPP_URL=https://xxxx-xx-xx-xx-xx.trycloudflare.com
   ```

   **Примечание:** URL меняется при каждом перезапуске cloudflared. Для стабильного URL используйте именованный туннель (см. документацию Cloudflare).

### Вариант 2: xTunnel (РЕКОМЕНДУЕТСЯ для РФ) ⭐

1. **Зарегистрируйтесь на [xtunnel.ru](https://xtunnel.ru)**

2. **Установите клиент** согласно инструкциям на сайте

3. **Запустите xTunnel**:
   ```bash
   xtunnel --port 80
   ```

4. **Скопируйте полученный HTTPS URL**

5. **Обновите `.env`**:
   ```env
   MINIAPP_URL=https://your-xtunnel-url.xtunnel.ru
   ```

### Вариант 3: localhost.run (SSH туннель) ⭐ ПРОСТОЙ

**Не требует регистрации, обычно работает из РФ:**

1. **Запустите SSH туннель** (SSH обычно уже установлен):
   ```bash
   ssh -R 80:localhost:80 serveo.net
   ```
   
   Или используйте альтернативный сервер:
   ```bash
   ssh -R 80:localhost:80 ssh.localhost.run
   ```

2. **Скопируйте полученный URL** (будет вида `https://xxxx.localhost.run`)

3. **Обновите `.env`**:
   ```env
   MINIAPP_URL=https://xxxx.localhost.run
   ```

### Вариант 4: bore.pub ⭐ БЫСТРЫЙ

1. **Установите bore**:
   ```bash
   # macOS
   brew install bore
   
   # Или через cargo
   cargo install bore-cli
   ```

2. **Запустите туннель**:
   ```bash
   bore local 80 --to bore.pub
   ```

3. **Скопируйте полученный URL** и обновите `.env`

### Вариант 5: Tuna

1. **Запустите Tuna** согласно инструкциям на сайте

2. **Скопируйте полученный HTTPS URL**

3. **Обновите `.env`**:
   ```env
   MINIAPP_URL=https://your-tuna-url.tuna.ru
   ```
   
   **Примечание:** На бесплатном тарифе туннель может быть ограничен 30 минутами

### Вариант 4: ngrok (если доступен)

1. **Запустите ngrok** (в отдельном терминале):

   ```bash
   ngrok http 80
   ```

2. **Скопируйте HTTPS URL** из вывода:
   ```
   Forwarding   https://xxxx-xx-xx-xx-xx.ngrok-free.app -> http://localhost:80
   ```

3. **Обновите `.env`**:
   ```env
   MINIAPP_URL=https://xxxx-xx-xx-xx-xx.ngrok-free.app
   ```

## Шаг 5: Перезапуск бота с новым URL

После обновления `MINIAPP_URL` перезапустите бота:

```bash
docker compose restart bot
```

Или пересоберите и перезапустите:

```bash
docker compose up -d --build bot
```

Проверьте логи бота:

```bash
docker compose logs -f bot
```

Должно появиться сообщение о том, что бот запущен и готов к работе.

## Шаг 6: Тестирование Mini App

1. **Откройте бота в Telegram**

2. **Проверьте главное меню** - должна появиться кнопка "🎵 Открыть плеер"

3. **Нажмите на кнопку "🎵 Открыть плеер"**

4. **Mini App должен открыться** в Telegram

5. **Проверьте функциональность:**
   - Mini App должен загрузиться
   - Должен отображаться интерфейс плеера
   - Попробуйте загрузить плейлисты (если есть такая кнопка)
   - Проверьте, что данные отправляются в бот через `sendData()`

## Шаг 7: Отладка

### Проверка логов

**Логи бота:**
```bash
docker compose logs -f bot
```

**Логи nginx:**
```bash
docker compose logs -f nginx
```

### Проверка доступности Mini App

Откройте в браузере URL туннеля (например, `https://xxxx-xx-xx-xx-xx.trycloudflare.com`). Должна открыться страница Mini App.

**Важно:** 
- Для cloudflared может появиться предупреждение Cloudflare - нажмите "Continue" или "Visit Site"
- Для ngrok может появиться предупреждение - нажмите "Visit Site"

### Проверка консоли браузера

В Telegram Mini App откройте DevTools (если доступно) или используйте `console.log` в коде для отладки.

### Проверка переменных окружения

Убедитесь, что `MINIAPP_URL` правильно установлен:

```bash
docker compose exec bot env | grep MINIAPP_URL
```

## Возможные проблемы

### Проблема 1: Кнопка "🎵 Открыть плеер" не появляется

**Решение:**
- Проверьте, что `MINIAPP_URL` установлен в `.env`
- Проверьте, что бот перезапущен после изменения `.env`
- Проверьте логи бота на наличие ошибок

### Проблема 2: Mini App не открывается

**Решение:**
- Проверьте, что туннель запущен и URL доступен
- Проверьте доступность URL: `curl -I https://your-url`
- Если получаете ошибку 530 (Cloudflare) или timeout, попробуйте альтернативные варианты туннелей (xTunnel, localhost.run, bore.pub)
- Проверьте, что URL в `MINIAPP_URL` начинается с `https://`
- Проверьте, что nginx запущен и раздает статику
- Проверьте логи nginx
- Попробуйте открыть URL в браузере - должна открыться страница Mini App

### Проблема 6: Туннель не подключается (ошибка 530, timeout)

**Решение:**
- Попробуйте альтернативные сервисы: xTunnel, localhost.run, bore.pub (см. варианты выше)
- Попробуйте альтернативные сервисы: xTunnel, localhost.run, bore.pub
- Если cloudflared не работает, это может быть из-за блокировки Cloudflare в вашем регионе

### Проблема 3: Ошибка "Telegram Web App API не доступен"

**Решение:**
- Убедитесь, что открываете Mini App через Telegram (не в обычном браузере)
- Проверьте, что скрипт `telegram-web-app.js` загружается (откройте DevTools и проверьте Network)

### Проблема 4: URL туннеля меняется при перезапуске

**Решение:**
- Это нормально для бесплатных версий туннелей
- Для cloudflared: используйте именованный туннель для стабильного URL (см. документацию)
- Для xTunnel: используйте платный тариф для стабильного URL
- Или используйте локальный домен с самоподписанным сертификатом (сложнее)

### Проблема 5: CORS ошибки

**Решение:**
- Проверьте, что nginx настроен с правильными CORS заголовками
- Проверьте конфигурацию nginx в `nginx/nginx.conf`

## Следующие шаги

После успешного тестирования базовой функциональности:

1. Протестируйте загрузку плейлистов
2. Протестируйте воспроизведение треков
3. Проверьте работу плеера (play/pause, перемотка)
4. Проверьте взаимодействие с ботом через `sendData()`

## Полезные команды

```bash
# Остановить все контейнеры
docker compose down

# Остановить и удалить volumes (очистка БД)
docker compose down -v

# Пересобрать контейнеры
docker compose up -d --build

# Просмотр логов
docker compose logs -f [service_name]

# Войти в контейнер бота
docker compose exec bot bash

# Проверить статус контейнеров
docker compose ps
```

## Примечания

- **HTTPS обязателен** для Web Apps - Telegram требует HTTPS
- **Для РФ рекомендуется xTunnel или localhost.run** - работают стабильно из России
- cloudflared может не работать из РФ из-за блокировки Cloudflare
- Для разработки используйте xTunnel, localhost.run, bore.pub, Tuna или ngrok (если доступен)
- Для продакшена нужен реальный домен с SSL сертификатом (Let's Encrypt)
- В бесплатных версиях туннелей URL меняется при каждом перезапуске
- Для стабильного URL используйте именованный туннель или платную подписку
- Если возникают проблемы с туннелями, попробуйте альтернативные варианты (xTunnel, localhost.run, bore.pub)

