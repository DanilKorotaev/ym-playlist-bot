#!/bin/bash

# Скрипт для настройки Let's Encrypt SSL сертификата
# Использование: sudo ./scripts/setup_letsencrypt.sh <domain> [staging_domain]

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Проверка аргументов
if [ -z "$1" ]; then
    echo -e "${RED}Ошибка: Не указан домен${NC}"
    echo "Использование: $0 <domain> [staging_domain]"
    echo "Пример: $0 mybot.ru"
    echo "Пример: $0 mybot.ru staging.mybot.ru"
    exit 1
fi

DOMAIN=$1
STAGING_DOMAIN=$2

echo -e "${GREEN}🔐 Настройка Let's Encrypt SSL сертификата${NC}"
echo "Домен: $DOMAIN"
if [ -n "$STAGING_DOMAIN" ]; then
    echo "Поддомен: $STAGING_DOMAIN"
fi
echo ""

# Проверка прав доступа
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}⚠️  Требуются права root для настройки сертификата${NC}"
    echo "Запустите скрипт с sudo:"
    echo "sudo $0 $DOMAIN $STAGING_DOMAIN"
    exit 1
fi

# Проверка установки certbot
if ! command -v certbot &> /dev/null; then
    echo -e "${YELLOW}⚠️  Certbot не установлен${NC}"
    echo "Установка certbot..."
    
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y certbot python3-certbot-nginx
    elif command -v yum &> /dev/null; then
        yum install -y epel-release
        yum install -y certbot python3-certbot-nginx
    else
        echo -e "${RED}❌ Не удалось определить пакетный менеджер${NC}"
        echo "Установите certbot вручную:"
        echo "  Ubuntu/Debian: sudo apt install certbot python3-certbot-nginx"
        echo "  CentOS/RHEL: sudo yum install certbot python3-certbot-nginx"
        exit 1
    fi
fi

# Проверка DNS
echo -e "${BLUE}📡 Проверка DNS записей...${NC}"
DOMAIN_IP=$(dig +short $DOMAIN | tail -n1)
SERVER_IP=$(curl -s ifconfig.me)

if [ -z "$DOMAIN_IP" ]; then
    echo -e "${RED}❌ Ошибка: DNS запись для $DOMAIN не найдена${NC}"
    echo "Настройте A-запись в панели управления доменом:"
    echo "  Тип: A"
    echo "  Имя: @ (или оставьте пустым)"
    echo "  Значение: $SERVER_IP"
    exit 1
fi

if [ "$DOMAIN_IP" != "$SERVER_IP" ]; then
    echo -e "${YELLOW}⚠️  Внимание: DNS указывает на другой IP${NC}"
    echo "  DNS IP: $DOMAIN_IP"
    echo "  Сервер IP: $SERVER_IP"
    echo ""
    read -p "Продолжить? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Отменено"
        exit 0
    fi
else
    echo -e "${GREEN}✅ DNS запись корректна: $DOMAIN -> $DOMAIN_IP${NC}"
fi

# Проверка портов
echo -e "${BLUE}🔌 Проверка портов...${NC}"
if ! ufw status | grep -q "80/tcp.*ALLOW"; then
    echo -e "${YELLOW}⚠️  Порт 80 не открыт в firewall${NC}"
    echo "Открытие порта 80..."
    ufw allow 80/tcp
fi

if ! ufw status | grep -q "443/tcp.*ALLOW"; then
    echo -e "${YELLOW}⚠️  Порт 443 не открыт в firewall${NC}"
    echo "Открытие порта 443..."
    ufw allow 443/tcp
fi

# Остановка nginx для получения сертификата
echo -e "${BLUE}🛑 Остановка nginx...${NC}"
if command -v docker &> /dev/null && docker ps | grep -q "ym_bot_nginx"; then
    echo "Остановка контейнера nginx..."
    docker stop ym_bot_nginx 2>/dev/null || true
    NGINX_STOPPED=true
else
    if systemctl is-active --quiet nginx; then
        echo "Остановка службы nginx..."
        systemctl stop nginx
        NGINX_STOPPED=true
    else
        NGINX_STOPPED=false
    fi
fi

# Получение сертификата
echo -e "${BLUE}📜 Получение Let's Encrypt сертификата...${NC}"

CERTBOT_DOMAINS="-d $DOMAIN"
if [ -n "$STAGING_DOMAIN" ]; then
    CERTBOT_DOMAINS="$CERTBOT_DOMAINS -d $STAGING_DOMAIN"
fi

if certbot certonly --standalone $CERTBOT_DOMAINS --non-interactive --agree-tos --email admin@$DOMAIN 2>/dev/null; then
    echo -e "${GREEN}✅ Сертификат успешно получен!${NC}"
else
    echo -e "${YELLOW}⚠️  Автоматическое получение не удалось${NC}"
    echo "Запуск интерактивного режима..."
    certbot certonly --standalone $CERTBOT_DOMAINS
fi

# Проверка сертификата
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo -e "${GREEN}✅ Сертификат найден: /etc/letsencrypt/live/$DOMAIN/fullchain.pem${NC}"
else
    echo -e "${RED}❌ Ошибка: Сертификат не найден${NC}"
    exit 1
fi

# Запуск nginx обратно
if [ "$NGINX_STOPPED" = true ]; then
    echo -e "${BLUE}▶️  Запуск nginx...${NC}"
    if command -v docker &> /dev/null; then
        docker start ym_bot_nginx 2>/dev/null || true
    else
        systemctl start nginx 2>/dev/null || true
    fi
fi

# Вывод информации
echo ""
echo -e "${GREEN}✅ Настройка завершена!${NC}"
echo ""
echo "Сертификат сохранен в:"
echo "  Полная цепочка: /etc/letsencrypt/live/$DOMAIN/fullchain.pem"
echo "  Приватный ключ: /etc/letsencrypt/live/$DOMAIN/privkey.pem"
echo ""
echo "Следующие шаги:"
echo "  1. Обновите конфигурацию nginx для использования Let's Encrypt сертификатов"
echo "     (см. docs/instructions/domain_and_letsencrypt_setup.md, раздел 5)"
echo "  2. Обновите docker-compose.yml для монтирования /etc/letsencrypt"
echo "  3. Обновите MINIAPP_URL в .env: https://$DOMAIN"
echo "  4. Перезапустите nginx и бота"
echo ""
echo -e "${YELLOW}⚠️  Важно:${NC}"
echo "  - Сертификат действителен 90 дней"
echo "  - Certbot автоматически обновит сертификат за 30 дней до истечения"
echo "  - Проверьте автоматическое обновление: sudo certbot renew --dry-run"

