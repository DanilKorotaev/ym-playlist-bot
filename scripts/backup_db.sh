#!/bin/bash

# Скрипт для создания резервной копии базы данных PostgreSQL
# Использование:
#   ./scripts/backup_db.sh                    # Бекап в директорию backups/
#   ./scripts/backup_db.sh /path/to/backups    # Бекап в указанную директорию
#   ./scripts/backup_db.sh --weekly            # Еженедельный бекап
#   ./scripts/backup_db.sh --upload            # Бекап с загрузкой в облако (если настроено)

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

# Параметры по умолчанию
BACKUP_DIR="${1:-backups}"
WEEKLY=false
UPLOAD=false

# Парсинг аргументов
if [[ "$1" == "--weekly" ]] || [[ "$2" == "--weekly" ]]; then
    WEEKLY=true
    BACKUP_DIR="${1:-backups}"
    if [[ "$1" == "--weekly" ]]; then
        BACKUP_DIR="${2:-backups}"
    fi
fi

if [[ "$1" == "--upload" ]] || [[ "$2" == "--upload" ]] || [[ "$3" == "--upload" ]]; then
    UPLOAD=true
fi

# Создаем директорию для бекапов, если её нет
mkdir -p "$BACKUP_DIR"

# Загружаем переменные окружения из .env, если файл существует
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Параметры БД из переменных окружения или значения по умолчанию
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-yandex_music_bot}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ym_bot_postgres}"

# Формируем имя файла бекапа
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
if [ "$WEEKLY" = true ]; then
    BACKUP_FILE="$BACKUP_DIR/backup_weekly_${TIMESTAMP}.sql"
else
    BACKUP_FILE="$BACKUP_DIR/backup_${TIMESTAMP}.sql"
fi

echo -e "${GREEN}Создание резервной копии базы данных...${NC}"
echo "База данных: $POSTGRES_DB"
echo "Пользователь: $POSTGRES_USER"
echo "Контейнер: $POSTGRES_CONTAINER"
echo "Файл бекапа: $BACKUP_FILE"

# Проверяем, запущен ли контейнер PostgreSQL
if ! docker ps | grep -q "$POSTGRES_CONTAINER"; then
    echo -e "${RED}ОШИБКА: Контейнер PostgreSQL '$POSTGRES_CONTAINER' не запущен!${NC}"
    echo "Запустите PostgreSQL: docker-compose up -d postgres"
    exit 1
fi

# Создаем бекап
echo -e "${YELLOW}Создание дампа базы данных...${NC}"
if docker exec "$POSTGRES_CONTAINER" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$BACKUP_FILE"; then
    # Проверяем размер файла (не должен быть пустым)
    FILE_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
    
    if [ "$FILE_SIZE" -lt 100 ]; then
        echo -e "${RED}ОШИБКА: Размер файла бекапа подозрительно мал ($FILE_SIZE байт)!${NC}"
        rm -f "$BACKUP_FILE"
        exit 1
    fi
    
    # Сжимаем бекап
    echo -e "${YELLOW}Сжатие бекапа...${NC}"
    gzip -f "$BACKUP_FILE"
    BACKUP_FILE="${BACKUP_FILE}.gz"
    
    FILE_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
    FILE_SIZE_MB=$((FILE_SIZE / 1024 / 1024))
    
    echo -e "${GREEN}✅ Бекап успешно создан!${NC}"
    echo "Файл: $BACKUP_FILE"
    echo "Размер: ${FILE_SIZE_MB} MB"
    
    # Ротация старых бекапов (удаление бекапов старше 7 дней, кроме недельных)
    echo -e "${YELLOW}Очистка старых бекапов...${NC}"
    find "$BACKUP_DIR" -name "backup_*.sql.gz" ! -name "backup_weekly_*.sql.gz" -mtime +7 -delete 2>/dev/null || true
    
    # Удаление недельных бекапов старше 30 дней
    find "$BACKUP_DIR" -name "backup_weekly_*.sql.gz" -mtime +30 -delete 2>/dev/null || true
    
    # Загрузка в облако (если настроено)
    if [ "$UPLOAD" = true ]; then
        echo -e "${YELLOW}Загрузка в облачное хранилище...${NC}"
        
        # AWS S3 (если настроено)
        if command -v aws &> /dev/null && [ -n "$AWS_S3_BUCKET" ]; then
            echo "Загрузка в AWS S3: $AWS_S3_BUCKET"
            aws s3 cp "$BACKUP_FILE" "s3://$AWS_S3_BUCKET/backups/" && \
            echo -e "${GREEN}✅ Бекап загружен в S3${NC}" || \
            echo -e "${RED}⚠️  Ошибка при загрузке в S3${NC}"
        fi
        
        # Google Cloud Storage (если настроено)
        if command -v gsutil &> /dev/null && [ -n "$GCS_BUCKET" ]; then
            echo "Загрузка в Google Cloud Storage: $GCS_BUCKET"
            gsutil cp "$BACKUP_FILE" "gs://$GCS_BUCKET/backups/" && \
            echo -e "${GREEN}✅ Бекап загружен в GCS${NC}" || \
            echo -e "${RED}⚠️  Ошибка при загрузке в GCS${NC}"
        fi
        
        # Yandex Object Storage (если настроено)
        if command -v yc &> /dev/null && [ -n "$YANDEX_S3_BUCKET" ]; then
            echo "Загрузка в Yandex Object Storage: $YANDEX_S3_BUCKET"
            yc storage cp "$BACKUP_FILE" "s3://$YANDEX_S3_BUCKET/backups/" && \
            echo -e "${GREEN}✅ Бекап загружен в Yandex Object Storage${NC}" || \
            echo -e "${RED}⚠️  Ошибка при загрузке в Yandex Object Storage${NC}"
        fi
        
        if ! command -v aws &> /dev/null && ! command -v gsutil &> /dev/null && ! command -v yc &> /dev/null; then
            echo -e "${YELLOW}⚠️  Облачные инструменты не настроены. Пропуск загрузки.${NC}"
        fi
    fi
    
    exit 0
else
    echo -e "${RED}ОШИБКА: Не удалось создать бекап!${NC}"
    rm -f "$BACKUP_FILE"
    exit 1
fi

