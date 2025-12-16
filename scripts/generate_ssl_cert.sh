#!/bin/bash

# Скрипт для генерации самоподписанного SSL сертификата
# Использование: ./scripts/generate_ssl_cert.sh [IP_OR_DOMAIN]

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка аргументов
if [ -z "$1" ]; then
    echo -e "${RED}Ошибка: Не указан IP-адрес или домен${NC}"
    echo "Использование: $0 <IP_OR_DOMAIN>"
    echo "Пример: $0 192.168.1.100"
    echo "Пример: $0 staging.example.com"
    exit 1
fi

IP_OR_DOMAIN=$1
SSL_DIR="/etc/nginx/ssl"
KEY_FILE="$SSL_DIR/nginx-selfsigned.key"
CERT_FILE="$SSL_DIR/nginx-selfsigned.crt"

echo -e "${GREEN}🔐 Генерация самоподписанного SSL сертификата${NC}"
echo "IP/Домен: $IP_OR_DOMAIN"
echo ""

# Проверка прав доступа
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}⚠️  Требуются права root для создания сертификата${NC}"
    echo "Запустите скрипт с sudo:"
    echo "sudo $0 $IP_OR_DOMAIN"
    exit 1
fi

# Создание директории для сертификатов
echo "📁 Создание директории для сертификатов..."
mkdir -p "$SSL_DIR"

# Проверка существующих сертификатов
if [ -f "$KEY_FILE" ] || [ -f "$CERT_FILE" ]; then
    echo -e "${YELLOW}⚠️  Обнаружены существующие сертификаты${NC}"
    read -p "Перезаписать? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Отменено"
        exit 0
    fi
    rm -f "$KEY_FILE" "$CERT_FILE"
fi

# Генерация сертификата
echo "🔨 Генерация сертификата..."
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -subj "/C=RU/ST=State/L=City/O=Organization/CN=$IP_OR_DOMAIN"

# Установка прав доступа
echo "🔒 Установка прав доступа..."
chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

# Проверка создания файлов
if [ -f "$KEY_FILE" ] && [ -f "$CERT_FILE" ]; then
    echo -e "${GREEN}✅ Сертификат успешно создан!${NC}"
    echo ""
    echo "Файлы:"
    echo "  Ключ: $KEY_FILE"
    echo "  Сертификат: $CERT_FILE"
    echo ""
    echo -e "${YELLOW}⚠️  Важно:${NC}"
    echo "  - Это самоподписанный сертификат"
    echo "  - Браузеры будут показывать предупреждение о небезопасном соединении"
    echo "  - Это нормально для стейдж сервера"
    echo "  - При первом открытии нужно принять исключение в браузере"
    echo ""
    echo "Следующие шаги:"
    echo "  1. Убедитесь, что nginx.conf настроен на использование этих сертификатов"
    echo "  2. Перезапустите nginx: docker compose restart nginx"
    echo "  3. Обновите MINIAPP_URL в .env: https://$IP_OR_DOMAIN"
else
    echo -e "${RED}❌ Ошибка при создании сертификата${NC}"
    exit 1
fi

