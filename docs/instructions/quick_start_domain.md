# Быстрый старт: Настройка домена и Let's Encrypt

## Минимальная инструкция для получения валидного SSL сертификата

### Шаг 1: Регистрация домена (5-10 минут)

1. Выберите регистратора:
   - **Reg.ru** (https://www.reg.ru/) - от 199₽/год
   - **Timeweb** (https://timeweb.com/) - от 199₽/год
   - **Namecheap** (https://www.namecheap.com/) - международный

2. Зарегистрируйте домен (например, `mybot.ru`)

3. Сохраните данные для доступа к панели управления

### Шаг 2: Настройка DNS (5 минут)

1. Войдите в панель управления регистратора
2. Перейдите в раздел "DNS" или "Управление DNS"
3. Добавьте A-запись:
   - **Тип:** A
   - **Имя:** @ (или оставьте пустым)
   - **Значение:** IP-адрес вашего сервера
   - **TTL:** 3600

4. Подождите 1-2 часа (обычно быстрее) для распространения DNS

### Шаг 3: Получение Let's Encrypt сертификата (5 минут)

**На сервере выполните:**

```bash
# 1. Установите certbot (если не установлен)
sudo apt update
sudo apt install -y certbot python3-certbot-nginx

# 2. Остановите nginx
docker compose stop nginx

# 3. Получите сертификат (используйте автоматический скрипт)
sudo ./scripts/setup_letsencrypt.sh your-domain.com

# Или вручную:
sudo certbot certonly --standalone -d your-domain.com
```

### Шаг 4: Настройка nginx (5 минут)

1. **Обновите конфигурацию nginx:**

   Скопируйте `nginx/nginx-letsencrypt.conf` и замените `your-domain.com` на ваш домен:

   ```bash
   cp nginx/nginx-letsencrypt.conf nginx/nginx-letsencrypt-custom.conf
   nano nginx/nginx-letsencrypt-custom.conf
   # Замените your-domain.com на ваш домен в строках:
   # ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
   # ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
   ```

2. **Обновите docker-compose.yml:**

   В секции `nginx` измените:
   ```yaml
   volumes:
     - ./nginx/nginx-letsencrypt-custom.conf:/etc/nginx/nginx.conf:ro
     - /etc/letsencrypt:/etc/letsencrypt:ro  # Вместо /etc/nginx/ssl
   ```

3. **Запустите nginx:**

   ```bash
   docker compose up -d nginx
   ```

### Шаг 5: Обновление конфигурации бота (2 минуты)

1. **Обновите `.env`:**
   ```env
   MINIAPP_URL=https://your-domain.com
   ```

2. **Перезапустите бота:**
   ```bash
   docker compose restart bot
   ```

### Шаг 6: Проверка (2 минуты)

1. Откройте `https://your-domain.com` в браузере
2. Проверьте, что сертификат валидный (замок в адресной строке)
3. Откройте Mini App в Telegram - должно работать без предупреждений

---

## Полная инструкция

Для подробной информации см. [`domain_and_letsencrypt_setup.md`](domain_and_letsencrypt_setup.md)

---

## Устранение проблем

**DNS не обновился:**
- Подождите 1-2 часа
- Проверьте через `dig your-domain.com +short`
- Используйте онлайн-сервисы: https://dnschecker.org/

**Certbot не может получить сертификат:**
- Убедитесь, что порт 80 открыт: `sudo ufw allow 80/tcp`
- Убедитесь, что nginx остановлен: `docker compose stop nginx`
- Проверьте DNS: `dig your-domain.com +short`

**Nginx не запускается:**
- Проверьте пути к сертификатам в конфигурации
- Убедитесь, что домен заменен на ваш реальный домен
- Проверьте логи: `docker compose logs nginx`

---

**Время выполнения:** ~30 минут (включая ожидание DNS)

**Стоимость:** от 199₽/год (только домен, Let's Encrypt бесплатно)

