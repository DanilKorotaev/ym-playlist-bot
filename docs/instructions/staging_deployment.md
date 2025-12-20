# Развертывание на стейдж сервер

## Дата создания
2025-12-11

## Обзор

Данная инструкция описывает процесс развертывания бота с Mini App плеером на стейдж сервер. Стейдж используется для тестирования новых функций перед развертыванием на production.

**Особенности стейджа:**
- Отдельный сервер для тестирования
- Возможность развертывания из любой ветки (не только main)
- SSL сертификат без домена (самоподписанный или через туннель)
- Отдельная база данных (не влияет на production)

---

## Предварительные требования

### 1. Сервер

**Минимальные требования:**
- Ubuntu 20.04+ или Debian 11+
- 2 CPU, 4GB RAM (минимум)
- 20GB свободного места на диске
- Доступ по SSH
- Открытые порты: 22 (SSH), 80 (HTTP), 443 (HTTPS)

**Рекомендуемые требования:**
- 4 CPU, 8GB RAM
- 50GB свободного места
- Статический IP-адрес

### 2. Установка базового ПО

**На сервере выполните:**

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка необходимых пакетов
sudo apt install -y git curl wget nano ufw

# Установка Docker и Docker Compose V2
# См. инструкцию в docs/instructions/cicd_setup.md, раздел 5.1
```

**Проверка установки:**

```bash
# Проверка Docker
docker --version
docker compose version  # Должна быть версия V2

# Проверка Git
git --version
```

---

## Шаг 1: Подготовка сервера

### 1.1. Настройка firewall

```bash
# Разрешить SSH (важно сделать первым!)
sudo ufw allow 22/tcp

# Разрешить HTTP и HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Включить firewall
sudo ufw enable

# Проверка статуса
sudo ufw status
```

### 1.2. Создание пользователя для деплоя (опционально, но рекомендуется)

```bash
# Создание пользователя
sudo adduser deploy-bot

# Добавление в группу docker
sudo usermod -aG docker deploy-bot
sudo usermod -aG sudo deploy-bot

# Переключение на нового пользователя
su - deploy-bot
```

### 1.3. Клонирование репозитория

```bash
# Переход в домашнюю директорию
cd ~

# Клонирование репозитория
git clone <your-repo-url> ym-playlist-bot-staging

# Переход в директорию проекта
cd ym-playlist-bot-staging

# Переключение на нужную ветку (например, с плеером)
git checkout <your-branch-name>
```

---

## Шаг 2: Настройка переменных окружения

### 2.1. Создание файла `.env`

```bash
# Создание файла .env из примера (если есть)
cp .env.example .env

# Или создание нового файла
nano .env
```

### 2.2. Заполнение переменных окружения

```env
# Telegram Bot Token (можно использовать тестового бота)
TELEGRAM_TOKEN=your_telegram_bot_token

# Yandex Music Token
YANDEX_TOKEN=your_yandex_token

# Database settings
DB_TYPE=postgresql
DB_HOST=postgres
DB_PORT=5432
DB_NAME=yandex_music_bot_staging
DB_USER=postgres
DB_PASSWORD=your_secure_password_here

# Mini App URL (будет заполнен после настройки SSL)
# Для начала можно оставить пустым или использовать IP
MINIAPP_URL=https://YOUR_SERVER_IP

# Дополнительные настройки
LOG_LEVEL=INFO
MAINTENANCE_MODE=false
ADMIN_IDS=your_telegram_user_id

# API настройки
MINIAPP_API_PORT=8000
MINIAPP_API_HOST=0.0.0.0
```

**Важно:**
- Используйте отдельную базу данных для стейджа (например, `yandex_music_bot_staging`)
- Используйте отдельный Telegram бот для тестирования (или тот же, если нужно)
- `MINIAPP_URL` будет обновлен после настройки SSL

---

## Шаг 3: Настройка SSL без домена

Telegram Mini Apps требуют HTTPS. Для стейджа без домена есть несколько вариантов:

### Вариант 1: Самоподписанный SSL сертификат (рекомендуется для стейджа)

**Плюсы:**
- ✅ Не требует внешних сервисов
- ✅ Работает сразу
- ✅ Бесплатно

**Минусы:**
- ⚠️ Браузеры показывают предупреждение о небезопасном соединении
- ⚠️ Нужно принять исключение в браузере при первом открытии

**Установка:**

Используйте скрипт из проекта (рекомендуется):

```bash
# Из директории проекта
sudo ./scripts/generate_ssl_cert.sh YOUR_SERVER_IP
```

**Или вручную:**

```bash
# Создание директории для сертификатов
sudo mkdir -p /etc/nginx/ssl

# Генерация самоподписанного сертификата
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/nginx-selfsigned.key \
  -out /etc/nginx/ssl/nginx-selfsigned.crt \
  -subj "/C=RU/ST=State/L=City/O=Organization/CN=YOUR_SERVER_IP"

# Установка прав доступа
sudo chmod 600 /etc/nginx/ssl/nginx-selfsigned.key
sudo chmod 644 /etc/nginx/ssl/nginx-selfsigned.crt
```

**Важно:** Замените `YOUR_SERVER_IP` на реальный IP-адрес вашего сервера.

### Вариант 2: Cloudflare Tunnel (альтернатива)

Если самоподписанный сертификат не подходит, используйте Cloudflare Tunnel:

```bash
# Установка cloudflared
# macOS: brew install cloudflared
# Linux: скачать с https://github.com/cloudflare/cloudflared/releases

# Запуск туннеля
cloudflared tunnel --url http://localhost:80
```

Скопируйте полученный HTTPS URL и используйте его в `MINIAPP_URL`.

### Вариант 3: Использование домена (если появится)

Если у вас есть домен, настройте Let's Encrypt:

```bash
# Установка certbot
sudo apt install certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com
```

---

## Шаг 4: Настройка nginx с SSL

### 4.1. Обновление конфигурации nginx

**Вариант 1: Использование готовой SSL конфигурации (рекомендуется)**

В проекте уже есть готовая конфигурация с SSL: `nginx/nginx-ssl.conf`. Скопируйте её:

```bash
# Из директории проекта
cp nginx/nginx-ssl.conf nginx/nginx.conf
```

**Вариант 2: Создание конфигурации вручную**

Создайте или обновите файл `nginx/nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    sendfile        on;
    keepalive_timeout  65;

    # Редирект HTTP на HTTPS
    server {
        listen 80;
        server_name _;
        
        # Редирект на HTTPS
        return 301 https://$host$request_uri;
    }

    # HTTPS сервер
    server {
        listen 443 ssl http2;
        server_name _;

        # SSL сертификаты
        ssl_certificate /etc/nginx/ssl/nginx-selfsigned.crt;
        ssl_certificate_key /etc/nginx/ssl/nginx-selfsigned.key;

        # SSL настройки
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        # Проксирование API запросов к FastAPI серверу
        location /api/ {
            proxy_pass http://api:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # CORS заголовки для Telegram Web App
            add_header Access-Control-Allow-Origin * always;
            add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
            add_header Access-Control-Allow-Headers "Content-Type, X-Telegram-Init-Data" always;
            
            # Обработка preflight запросов
            if ($request_method = OPTIONS) {
                add_header Access-Control-Allow-Origin *;
                add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
                add_header Access-Control-Allow-Headers "Content-Type, X-Telegram-Init-Data";
                add_header Content-Length 0;
                add_header Content-Type text/plain;
                return 204;
            }
        }

        # Раздача статики Mini App
        location / {
            root /usr/share/nginx/html;
            index index.html;
            try_files $uri $uri/ /index.html;
            
            # CORS заголовки для Telegram Web App
            add_header Access-Control-Allow-Origin * always;
            add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
            add_header Access-Control-Allow-Headers "Content-Type, X-Telegram-Init-Data" always;
            
            # Обработка preflight запросов
            if ($request_method = OPTIONS) {
                add_header Access-Control-Allow-Origin *;
                add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
                add_header Access-Control-Allow-Headers "Content-Type, X-Telegram-Init-Data";
                add_header Content-Length 0;
                add_header Content-Type text/plain;
                return 204;
            }
        }

        # Логирование
        access_log /var/log/nginx/access.log;
        error_log /var/log/nginx/error.log;
    }
}
```

### 4.2. Обновление docker-compose.yml

Убедитесь, что nginx имеет доступ к SSL сертификатам. В `docker-compose.yml` раскомментируйте строку с монтированием SSL:

```yaml
nginx:
  image: nginx:alpine
  container_name: ym_bot_nginx
  ports:
    - "80:80"
    - "443:443"  # HTTPS порт
  volumes:
    - ./miniapp/static:/usr/share/nginx/html:ro
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    - /etc/nginx/ssl:/etc/nginx/ssl:ro  # Раскомментируйте эту строку
  depends_on:
    - bot
    - api
  networks:
    - bot_network
  restart: unless-stopped
```

**Или отредактируйте файл напрямую:**

```bash
# Откройте docker-compose.yml
nano docker-compose.yml

# Найдите секцию nginx и раскомментируйте строку:
# - /etc/nginx/ssl:/etc/nginx/ssl:ro
```

---

## Шаг 5: Первый запуск

### 5.1. Запуск контейнеров

```bash
# Из директории проекта
docker compose up -d

# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f
```

**Ожидаемые контейнеры:**
- `ym_bot_postgres` - PostgreSQL
- `ym_bot_pgadmin` - pgAdmin (опционально)
- `ym_bot` - Telegram бот
- `ym_bot_api` - FastAPI сервер
- `ym_bot_nginx` - nginx

### 5.2. Проверка работы

**Проверка бота:**
```bash
# Логи бота
docker compose logs bot

# Должны быть сообщения о запуске, без ошибок
```

**Проверка API:**
```bash
# Проверка доступности API
curl http://localhost:8000/docs

# Или через HTTPS (после настройки SSL)
curl -k https://YOUR_SERVER_IP/api/docs
```

**Проверка nginx:**
```bash
# Проверка статики
curl -k https://YOUR_SERVER_IP/

# Должна вернуться HTML страница Mini App
```

### 5.3. Анализ логов PostgreSQL

При первом запуске PostgreSQL вы можете увидеть следующие предупреждения в логах:

#### Предупреждение о locale (не критично)

```
sh: locale: not found
WARNING: no usable system locales were found
```

**Причина:** В Alpine-образе PostgreSQL отсутствуют системные локали.

**Влияние:** Минимальное. База данных работает нормально, но сортировка может отличаться от ожидаемой.

**Решение:** Для стейджа можно игнорировать. Для production можно добавить локали в Dockerfile PostgreSQL.

#### Предупреждение о trust authentication (не критично)

```
initdb: warning: enabling "trust" authentication for local connections
```

**Причина:** По умолчанию PostgreSQL использует "trust" аутентификацию для локальных подключений.

**Влияние:** Для внутренней сети Docker это нормально и безопасно, так как контейнеры изолированы.

**Решение:** Для стейджа можно оставить как есть. Для production рекомендуется настроить парольную аутентификацию.

**Важно:** Все предупреждения не критичны и не мешают работе базы данных. PostgreSQL успешно запущен и готов к работе.

### 5.4. Обновление MINIAPP_URL

После успешного запуска обновите `MINIAPP_URL` в `.env`:

```env
MINIAPP_URL=https://YOUR_SERVER_IP
```

**Важно:** Замените `YOUR_SERVER_IP` на реальный IP-адрес сервера.

**Перезапуск бота:**
```bash
docker compose restart bot
```

---

## Шаг 6: Настройка CI/CD для стейджа

### 6.1. Добавление GitHub Secrets для стейджа

В GitHub репозитории добавьте следующие секреты:

- `STAGING_DEPLOY_HOST` - IP-адрес стейдж сервера
- `STAGING_DEPLOY_USER` - имя пользователя для SSH
- `STAGING_DEPLOY_SSH_KEY` - приватный SSH ключ (без passphrase)
- `STAGING_DEPLOY_PATH` - путь к проекту на сервере (например, `/home/deploy-bot/ym-playlist-bot-staging`)

**См. инструкцию:** `docs/instructions/cicd_setup.md`, раздел 3

### 6.2. Использование CI/CD

После настройки секретов можно использовать GitHub Actions для автоматического развертывания на стейдж:

1. Откройте GitHub → **Actions**
2. Выберите workflow **Deploy to Staging**
3. Нажмите **Run workflow**
4. Выберите ветку для развертывания
5. Нажмите **Run workflow**

**Или автоматически при push в ветку `staging`** (если настроено в workflow).

---

## Шаг 7: Тестирование Mini App

### 7.1. Открытие Mini App в Telegram

1. Откройте бота в Telegram
2. Нажмите кнопку "🎵 Открыть плеер"
3. Mini App должен открыться

**Если браузер показывает предупреждение о небезопасном соединении:**
- Это нормально для самоподписанного сертификата
- Нажмите "Дополнительно" → "Перейти на сайт" (или аналогичную кнопку)
- После этого Mini App должен открыться

### 7.2. Проверка функциональности

- ✅ Открытие Mini App
- ✅ Загрузка списка плейлистов
- ✅ Выбор плейлиста
- ✅ Загрузка треков
- ✅ Воспроизведение треков
- ✅ Навигация по очереди
- ✅ Автоматическое обновление очереди

---

## Обслуживание

### Обновление кода

**Вручную:**
```bash
cd ~/ym-playlist-bot-staging
git pull origin <branch-name>
docker compose build
docker compose up -d
```

**Через CI/CD:**
- Используйте GitHub Actions workflow "Deploy to Staging"

### Просмотр логов

```bash
# Все сервисы
docker compose logs -f

# Конкретный сервис
docker compose logs -f bot
docker compose logs -f api
docker compose logs -f nginx
docker compose logs -f postgres
```

### Остановка/запуск

```bash
# Остановка
docker compose stop

# Запуск
docker compose start

# Перезапуск
docker compose restart
```

### Очистка (если нужно)

```bash
# Остановка и удаление контейнеров
docker compose down

# Удаление с volumes (ОСТОРОЖНО: удалит базу данных!)
docker compose down -v
```

---

## Устранение неполадок

### Проблема 1: nginx не запускается

**Ошибка:** `nginx: [emerg] SSL_CTX_use_certificate_file() failed`

**Решение:**
- Проверьте, что SSL сертификаты созданы: `ls -la /etc/nginx/ssl/`
- Проверьте права доступа: `sudo chmod 644 /etc/nginx/ssl/nginx-selfsigned.crt`
- Проверьте, что путь к сертификатам правильный в `nginx.conf`

### Проблема 2: Mini App не открывается

**Решение:**
- Проверьте, что `MINIAPP_URL` установлен в `.env`
- Проверьте, что URL доступен: `curl -k https://YOUR_SERVER_IP/`
- Проверьте логи nginx: `docker compose logs nginx`
- Проверьте, что порты 80 и 443 открыты в firewall

### Проблема 3: API не отвечает

**Решение:**
- Проверьте, что контейнер `api` запущен: `docker compose ps`
- Проверьте логи API: `docker compose logs api`
- Проверьте доступность API: `curl http://localhost:8000/docs`
- Проверьте переменные окружения в `.env`

### Проблема 4: База данных не подключается

**Решение:**
- Проверьте, что контейнер `postgres` запущен: `docker compose ps`
- Проверьте логи PostgreSQL: `docker compose logs postgres`
- Проверьте переменные окружения `DB_*` в `.env`
- Проверьте, что база данных создана (должна создаться автоматически)
- Проверьте предупреждения в логах (см. раздел 5.3) - они не критичны

### Проблема 5: Предупреждения в логах PostgreSQL

**Решение:**
- Предупреждения о locale и trust authentication не критичны
- База данных работает нормально
- Для production можно настроить более строгую аутентификацию

---

## Безопасность

### Рекомендации для стейджа

1. **Firewall:** Убедитесь, что firewall настроен и разрешает только необходимые порты
2. **SSH:** Используйте ключи вместо паролей для SSH
3. **Пароли:** Используйте сильные пароли для базы данных
4. **Обновления:** Регулярно обновляйте систему и Docker
5. **Логи:** Регулярно проверяйте логи на подозрительную активность

### Ограничение доступа (опционально)

Если нужно ограничить доступ к стейджу только для определенных IP:

```bash
# В firewall разрешить только определенные IP
sudo ufw allow from YOUR_IP to any port 80
sudo ufw allow from YOUR_IP to any port 443
```

---

## Чеклист развертывания

- [ ] Сервер подготовлен (Docker, Git установлены)
- [ ] Репозиторий клонирован
- [ ] Файл `.env` создан и заполнен
- [ ] SSL сертификат создан (самоподписанный или через туннель)
- [ ] nginx настроен с SSL
- [ ] docker-compose.yml обновлен
- [ ] Контейнеры запущены и работают
- [ ] Логи PostgreSQL проверены (предупреждения не критичны)
- [ ] `MINIAPP_URL` обновлен в `.env`
- [ ] Бот перезапущен
- [ ] Mini App открывается в Telegram
- [ ] Функциональность протестирована
- [ ] CI/CD настроен (опционально)

---

## Следующие шаги

После успешного развертывания на стейдж:

1. Протестируйте все функции Mini App
2. Проверьте работу автоматического обновления очереди
3. Убедитесь, что нет критических ошибок в логах
4. После тестирования можно развернуть на production

---

**Документ создан:** 2025-12-11  
**Версия:** 1.1  
**Автор:** AI Agent
