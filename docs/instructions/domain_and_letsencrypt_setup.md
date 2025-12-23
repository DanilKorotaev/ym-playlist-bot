# Настройка домена и Let's Encrypt SSL сертификата

## Дата создания
2025-12-20

## Обзор

Данная инструкция описывает процесс получения домена, настройки DNS записей и получения валидного SSL сертификата от Let's Encrypt для работы Mini App в Telegram.

**Почему нужен домен и Let's Encrypt:**
- ✅ Telegram Mini Apps требуют валидный HTTPS сертификат
- ✅ Самоподписанные сертификаты не работают (браузер и Telegram блокируют)
- ✅ Let's Encrypt предоставляет бесплатные валидные SSL сертификаты
- ✅ Автоматическое обновление сертификатов

---

## Шаг 1: Выбор и регистрация домена

### 1.1. Выбор регистратора домена

**Рекомендуемые регистраторы для РФ:**

1. **Reg.ru** (https://www.reg.ru/)
   - ✅ Популярный в РФ
   - ✅ Русскоязычная поддержка
   - ✅ Удобная панель управления
   - ✅ Цены от 199₽/год для .ru доменов

2. **Timeweb** (https://timeweb.com/)
   - ✅ Хорошая поддержка
   - ✅ Интеграция с хостингом
   - ✅ Цены от 199₽/год

3. **Namecheap** (https://www.namecheap.com/)
   - ✅ Международный регистратор
   - ✅ Хорошие цены
   - ✅ Англоязычный интерфейс

4. **Cloudflare Registrar** (https://www.cloudflare.com/products/registrar/)
   - ✅ Бесплатный WHOIS privacy
   - ✅ Нет наценки на домены
   - ✅ Интеграция с Cloudflare DNS

**Рекомендация:** Для начала используйте **Reg.ru** или **Timeweb** - они простые и понятные для русскоязычных пользователей.

### 1.2. Выбор домена

**Рекомендации по выбору домена:**

- ✅ Короткое и запоминающееся имя
- ✅ Используйте домены `.ru`, `.com`, `.net` (популярные зоны)
- ✅ Избегайте сложных символов и дефисов
- ✅ Примеры: `mybot.ru`, `musicbot.com`, `playlistbot.net`

**Для стейджа можно использовать поддомен:**
- `staging.mybot.ru`
- `test.mybot.ru`
- `dev.mybot.ru`

### 1.3. Регистрация домена

**Процесс регистрации (на примере Reg.ru):**

1. **Перейдите на сайт регистратора** (например, https://www.reg.ru/)

2. **Проверьте доступность домена:**
   - Введите желаемое имя домена в поиск
   - Проверьте доступность и цены

3. **Добавьте домен в корзину и оформите заказ:**
   - Выберите срок регистрации (минимум 1 год)
   - Заполните контактные данные
   - Оплатите заказ

4. **Подтвердите регистрацию:**
   - Проверьте email (придет письмо с подтверждением)
   - Подтвердите регистрацию домена

**Важно:**
- Сохраните данные для доступа к панели управления доменом
- Запишите логин и пароль в безопасное место
- Домен активируется в течение 24 часов (обычно быстрее)

---

## Шаг 2: Настройка DNS записей

После регистрации домена нужно настроить DNS записи, чтобы домен указывал на ваш сервер.

### 2.1. Получение IP-адреса сервера

**Узнайте IP-адрес вашего сервера:**

```bash
# На сервере выполните:
curl ifconfig.me

# Или:
hostname -I
```

**Запишите IP-адрес** - он понадобится для настройки DNS.

### 2.2. Настройка DNS в панели регистратора

**Процесс настройки (на примере Reg.ru):**

1. **Войдите в панель управления** регистратора

2. **Перейдите в раздел "DNS" или "Управление DNS"**

3. **Найдите ваш домен** и откройте настройки DNS

4. **Добавьте A-запись:**
   - **Тип:** A
   - **Имя:** @ (или оставьте пустым для корневого домена)
   - **Значение:** IP-адрес вашего сервера (например, `185.123.45.67`)
   - **TTL:** 3600 (или по умолчанию)

5. **Если нужен поддомен (например, для стейджа):**
   - **Тип:** A
   - **Имя:** staging (или test, dev)
   - **Значение:** IP-адрес вашего сервера
   - **TTL:** 3600

6. **Сохраните изменения**

**Пример настроек DNS:**

```
Тип    Имя      Значение          TTL
A      @        185.123.45.67     3600
A      staging  185.123.45.67     3600
```

### 2.3. Проверка DNS записей

**Проверьте, что DNS записи применились:**

```bash
# Проверка A-записи для корневого домена
dig your-domain.com +short

# Должен вернуться IP-адрес вашего сервера

# Проверка поддомена
dig staging.your-domain.com +short

# Также должен вернуться IP-адрес сервера
```

**Или используйте онлайн-сервисы:**
- https://dnschecker.org/
- https://www.whatsmydns.net/

**Важно:**
- DNS изменения могут распространяться до 24 часов (обычно 1-2 часа)
- Дождитесь, пока DNS записи обновятся, прежде чем продолжать

---

## Шаг 3: Установка Certbot

Certbot - это инструмент для автоматического получения и обновления Let's Encrypt сертификатов.

### 3.1. Установка Certbot на сервере

**На Ubuntu/Debian:**

```bash
# Обновление списка пакетов
sudo apt update

# Установка certbot и плагина для nginx
sudo apt install -y certbot python3-certbot-nginx

# Проверка установки
certbot --version
```

**На CentOS/RHEL:**

```bash
# Установка EPEL репозитория
sudo yum install -y epel-release

# Установка certbot
sudo yum install -y certbot python3-certbot-nginx
```

### 3.2. Проверка доступности домена

**Перед получением сертификата убедитесь, что:**

1. **Домен указывает на ваш сервер:**
   ```bash
   # Проверка DNS
   dig your-domain.com +short
   # Должен вернуться IP вашего сервера
   ```

2. **Порты 80 и 443 открыты:**
   ```bash
   # Проверка firewall
   sudo ufw status
   # Должны быть открыты порты 80 и 443
   
   # Если не открыты, откройте:
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   ```

3. **Nginx не запущен** (для метода standalone):
   ```bash
   # Остановите nginx, если запущен
   docker compose stop nginx
   ```

---

## Шаг 4: Получение Let's Encrypt сертификата

### 4.1. Метод 1: Standalone (рекомендуется для первого раза)

**Этот метод временно запускает веб-сервер на порту 80 для проверки домена.**

```bash
# Остановите nginx (если запущен)
docker compose stop nginx

# Получение сертификата
sudo certbot certonly --standalone -d your-domain.com

# Если нужен поддомен:
sudo certbot certonly --standalone -d your-domain.com -d staging.your-domain.com
```

**Во время выполнения certbot:**
1. Запросит email (для уведомлений об истечении сертификата)
2. Спросит согласие с условиями использования
3. Спросит, хотите ли вы подписаться на новости (можно отказаться)
4. Автоматически проверит домен и получит сертификат

**Результат:**
- Сертификат будет сохранен в `/etc/letsencrypt/live/your-domain.com/`
- Файлы:
  - `fullchain.pem` - полная цепочка сертификатов
  - `privkey.pem` - приватный ключ

### 4.2. Метод 2: Webroot (если nginx уже запущен)

**Если nginx уже настроен и работает:**

```bash
# Certbot автоматически настроит nginx
sudo certbot --nginx -d your-domain.com
```

**Этот метод:**
- Автоматически настроит nginx для использования сертификата
- Добавит редирект с HTTP на HTTPS
- Обновит конфигурацию nginx

**Примечание:** Для Docker-контейнеров этот метод может не работать напрямую, так как certbot должен иметь доступ к конфигурации nginx внутри контейнера.

### 4.3. Проверка сертификата

**Проверьте, что сертификат получен:**

```bash
# Просмотр списка сертификатов
sudo certbot certificates

# Должен показать ваш домен и пути к файлам:
# Certificate Name: your-domain.com
# Domains: your-domain.com
# Certificate Path: /etc/letsencrypt/live/your-domain.com/fullchain.pem
# Private Key Path: /etc/letsencrypt/live/your-domain.com/privkey.pem
```

---

## Шаг 5: Настройка nginx для использования Let's Encrypt

### 5.1. Обновление конфигурации nginx

**Создайте новую конфигурацию nginx для Let's Encrypt:**

Создайте файл `nginx/nginx-letsencrypt.conf`:

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
        server_name your-domain.com staging.your-domain.com;
        
        # Редирект на HTTPS
        return 301 https://$host$request_uri;
    }

    # HTTPS сервер
    server {
        listen 443 ssl http2;
        server_name your-domain.com staging.your-domain.com;

        # SSL сертификаты Let's Encrypt
        ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

        # SSL настройки (рекомендуемые Let's Encrypt)
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;
        
        # Дополнительные SSL настройки для безопасности
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        # Проксирование API запросов к FastAPI серверу
        location /api/ {
            rewrite ^/api/(.*)$ /$1 break;
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

**Важно:** Замените `your-domain.com` на ваш реальный домен в конфигурации.

### 5.2. Обновление docker-compose.yml

**Обновите секцию nginx в `docker-compose.yml`:**

```yaml
nginx:
  image: nginx:alpine
  container_name: ym_bot_nginx
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./miniapp/static:/usr/share/nginx/html:ro
    - ./nginx/nginx-letsencrypt.conf:/etc/nginx/nginx.conf:ro
    # Let's Encrypt сертификаты
    - /etc/letsencrypt:/etc/letsencrypt:ro
  depends_on:
    - bot
    - api
  networks:
    - bot_network
  restart: unless-stopped
```

**Изменения:**
- Используется `nginx-letsencrypt.conf` вместо `nginx.conf`
- Монтируется `/etc/letsencrypt` вместо `/etc/nginx/ssl`

### 5.3. Запуск nginx

```bash
# Перезапуск nginx с новой конфигурацией
docker compose up -d nginx

# Проверка логов
docker compose logs nginx

# Проверка конфигурации внутри контейнера
docker compose exec nginx nginx -t
```

---

## Шаг 6: Настройка автоматического обновления сертификата

Let's Encrypt сертификаты действительны 90 дней. Certbot автоматически настраивает cron для обновления, но нужно убедиться, что это работает.

### 6.1. Проверка автоматического обновления

```bash
# Проверка, настроен ли автоматический обновление
sudo systemctl status certbot.timer

# Или проверка cron задач
sudo crontab -l | grep certbot
```

### 6.2. Тестовое обновление

```bash
# Тестовое обновление (не обновляет реальный сертификат)
sudo certbot renew --dry-run

# Если тест прошел успешно, автоматическое обновление работает
```

### 6.3. Ручное обновление (если нужно)

```bash
# Обновление всех сертификатов
sudo certbot renew

# После обновления перезапустите nginx
docker compose restart nginx
```

**Важно:** Certbot автоматически обновляет сертификаты за 30 дней до истечения. Обычно ничего делать не нужно.

---

## Шаг 7: Обновление MINIAPP_URL

После настройки домена и SSL обновите переменную окружения в `.env`:

```env
# Обновленный URL Mini App
MINIAPP_URL=https://your-domain.com

# Или для поддомена:
MINIAPP_URL=https://staging.your-domain.com
```

**Перезапустите бота:**

```bash
docker compose restart bot
```

---

## Шаг 8: Проверка работы

### 8.1. Проверка SSL сертификата

**Проверьте сертификат в браузере:**

1. Откройте `https://your-domain.com` в браузере
2. Нажмите на значок замка в адресной строке
3. Проверьте, что сертификат валидный и выдан Let's Encrypt

**Или используйте онлайн-сервисы:**
- https://www.ssllabs.com/ssltest/
- https://www.sslshopper.com/ssl-checker.html

### 8.2. Проверка Mini App в Telegram

1. Откройте бота в Telegram
2. Нажмите кнопку "🎵 Открыть плеер"
3. Mini App должен открыться без предупреждений о безопасности
4. Проверьте работу всех функций

### 8.3. Проверка API

```bash
# Проверка API через HTTPS
curl https://your-domain.com/api/docs

# Должна вернуться HTML страница Swagger UI
```

---

## Устранение неполадок

### Проблема 1: DNS не обновился

**Симптомы:** `dig your-domain.com` не возвращает IP сервера

**Решение:**
- Подождите 1-2 часа (DNS изменения распространяются не сразу)
- Проверьте настройки DNS в панели регистратора
- Используйте онлайн-сервисы для проверки DNS (https://dnschecker.org/)

### Проблема 2: Certbot не может получить сертификат

**Ошибка:** `Failed to obtain certificate`

**Решение:**
- Убедитесь, что порт 80 открыт: `sudo ufw allow 80/tcp`
- Убедитесь, что nginx остановлен: `docker compose stop nginx`
- Проверьте, что домен указывает на сервер: `dig your-domain.com +short`
- Проверьте firewall на сервере и у провайдера

### Проблема 3: Nginx не запускается

**Ошибка:** `SSL_CTX_use_certificate_file() failed`

**Решение:**
- Проверьте пути к сертификатам в конфигурации nginx
- Убедитесь, что сертификаты существуют: `sudo ls -la /etc/letsencrypt/live/your-domain.com/`
- Проверьте права доступа: `sudo chmod 644 /etc/letsencrypt/live/your-domain.com/fullchain.pem`
- Проверьте, что `/etc/letsencrypt` монтируется в контейнер nginx

### Проблема 4: Сертификат истекает

**Решение:**
- Certbot автоматически обновляет сертификаты
- Проверьте статус: `sudo certbot certificates`
- Проверьте автоматическое обновление: `sudo certbot renew --dry-run`
- Если нужно, обновите вручную: `sudo certbot renew && docker compose restart nginx`

### Проблема 5: Mini App все еще показывает предупреждение

**Решение:**
- Убедитесь, что используете правильный URL (с https://)
- Проверьте сертификат в браузере (должен быть валидный Let's Encrypt)
- Очистите кэш Telegram (закройте и снова откройте Mini App)
- Проверьте, что `MINIAPP_URL` обновлен в `.env` и бот перезапущен

---

## Чеклист настройки

- [ ] Домен зарегистрирован
- [ ] DNS записи настроены (A-запись указывает на IP сервера)
- [ ] DNS изменения применились (проверено через `dig`)
- [ ] Порты 80 и 443 открыты в firewall
- [ ] Certbot установлен
- [ ] Let's Encrypt сертификат получен
- [ ] Конфигурация nginx обновлена для Let's Encrypt
- [ ] docker-compose.yml обновлен
- [ ] Nginx запущен и работает
- [ ] SSL сертификат проверен в браузере
- [ ] `MINIAPP_URL` обновлен в `.env`
- [ ] Бот перезапущен
- [ ] Mini App открывается в Telegram без предупреждений
- [ ] Автоматическое обновление сертификата настроено

---

## Стоимость

**Домен:**
- `.ru` домен: от 199₽/год
- `.com` домен: от 500-1000₽/год
- Поддомены: бесплатно (используют основной домен)

**Let's Encrypt:**
- ✅ Полностью бесплатно
- ✅ Неограниченное количество сертификатов
- ✅ Автоматическое обновление

**Итого:** Минимальная стоимость - только регистрация домена (от 199₽/год).

---

## Дополнительные ресурсы

- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Certbot Documentation](https://certbot.eff.org/)
- [DNS Checker](https://dnschecker.org/)
- [SSL Labs SSL Test](https://www.ssllabs.com/ssltest/)

---

**Документ создан:** 2025-12-20  
**Версия:** 1.0  
**Автор:** AI Agent

