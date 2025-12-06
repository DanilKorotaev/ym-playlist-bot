#!/bin/bash

# Скрипт для восстановления базы данных из резервной копии
# Использование:
#   ./scripts/restore_db.sh backup_YYYYMMDD_HHMMSS.sql
#   ./scripts/restore_db.sh backup_YYYYMMDD_HHMMSS.sql.gz
#   ./scripts/restore_db.sh /path/to/backup.sql

set -e  # Остановка при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Получаем директорию проекта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Проверяем наличие аргумента
if [ -z "$1" ]; then
    echo -e "${RED}ОШИБКА: Укажите файл бекапа для восстановления!${NC}"
    echo "Использование: $0 <backup_file>"
    echo "Пример: $0 backups/backup_20240101_120000.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

# Проверяем существование файла
if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}ОШИБКА: Файл '$BACKUP_FILE' не найден!${NC}"
    exit 1
fi

# Загружаем переменные окружения из .env, если файл существует
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Параметры БД из переменных окружения или значения по умолчанию
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-yandex_music_bot}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ym_bot_postgres}"

echo -e "${YELLOW}⚠️  ВНИМАНИЕ: Восстановление базы данных приведет к потере всех текущих данных!${NC}"
echo "База данных: $POSTGRES_DB"
echo "Пользователь: $POSTGRES_USER"
echo "Контейнер: $POSTGRES_CONTAINER"
echo "Файл бекапа: $BACKUP_FILE"

# Запрашиваем подтверждение
read -p "Вы уверены, что хотите продолжить? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Восстановление отменено."
    exit 0
fi

# Проверяем, запущен ли контейнер PostgreSQL
if ! docker ps | grep -q "$POSTGRES_CONTAINER"; then
    echo -e "${YELLOW}Контейнер PostgreSQL не запущен. Запускаем...${NC}"
    docker compose up -d postgres
    
    # Ждем, пока PostgreSQL будет готов
    echo "Ожидание готовности PostgreSQL..."
    sleep 5
    for i in {1..30}; do
        if docker exec "$POSTGRES_CONTAINER" pg_isready -U "$POSTGRES_USER" > /dev/null 2>&1; then
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}ОШИБКА: PostgreSQL не запустился за отведенное время!${NC}"
            exit 1
        fi
        sleep 1
    done
fi

# Определяем, сжат ли файл
if [[ "$BACKUP_FILE" == *.gz ]]; then
    echo -e "${YELLOW}Распаковка сжатого бекапа...${NC}"
    TEMP_FILE=$(mktemp)
    gunzip -c "$BACKUP_FILE" > "$TEMP_FILE"
    BACKUP_TO_RESTORE="$TEMP_FILE"
else
    BACKUP_TO_RESTORE="$BACKUP_FILE"
fi

# Останавливаем бота (если запущен)
if docker ps | grep -q "ym_bot"; then
    echo -e "${YELLOW}Остановка бота...${NC}"
    docker compose stop bot || true
fi

# Восстанавливаем базу данных
echo -e "${YELLOW}Восстановление базы данных...${NC}"

# Сначала удаляем существующую БД и создаем новую
echo "Удаление существующей базы данных (если есть)..."
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS $POSTGRES_DB;" postgres || true

echo "Создание новой базы данных..."
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c "CREATE DATABASE $POSTGRES_DB;" postgres

# Восстанавливаем данные
echo "Восстановление данных из бекапа..."
if docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" "$POSTGRES_DB" < "$BACKUP_TO_RESTORE"; then
    echo -e "${GREEN}✅ База данных успешно восстановлена!${NC}"
    
    # Удаляем временный файл, если был создан
    if [ -n "$TEMP_FILE" ]; then
        rm -f "$TEMP_FILE"
    fi
    
    # Проверяем данные
    echo -e "${YELLOW}Проверка восстановленных данных...${NC}"
    docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" "$POSTGRES_DB" -c "
        SELECT 
            'users' as table_name, COUNT(*) as count FROM users
        UNION ALL
        SELECT 'playlists', COUNT(*) FROM playlists
        UNION ALL
        SELECT 'yandex_accounts', COUNT(*) FROM yandex_accounts
        UNION ALL
        SELECT 'playlist_access', COUNT(*) FROM playlist_access
        UNION ALL
        SELECT 'actions', COUNT(*) FROM actions
        UNION ALL
        SELECT 'user_subscriptions', COUNT(*) FROM user_subscriptions
        UNION ALL
        SELECT 'payments', COUNT(*) FROM payments;
    "
    
    echo -e "${GREEN}Восстановление завершено успешно!${NC}"
    echo "Можно запустить бота: docker compose up -d"
    
    exit 0
else
    echo -e "${RED}ОШИБКА: Не удалось восстановить базу данных!${NC}"
    
    # Удаляем временный файл, если был создан
    if [ -n "$TEMP_FILE" ]; then
        rm -f "$TEMP_FILE"
    fi
    
    exit 1
fi

