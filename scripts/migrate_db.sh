#!/bin/bash

# Скрипт для миграции базы данных между серверами
# Использование:
#   ./scripts/migrate_db.sh export                    # Создать дамп для миграции
#   ./scripts/migrate_db.sh import backup_file.sql    # Восстановить из дампа

set -e  # Остановка при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Получаем директорию проекта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Загружаем переменные окружения из .env, если файл существует
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Параметры БД из переменных окружения или значения по умолчанию
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-yandex_music_bot}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ym_bot_postgres}"

# Функция для экспорта (создание дампа для миграции)
export_db() {
    echo -e "${BLUE}=== Экспорт базы данных для миграции ===${NC}"
    
    # Проверяем, запущен ли контейнер PostgreSQL
    if ! docker ps | grep -q "$POSTGRES_CONTAINER"; then
        echo -e "${RED}ОШИБКА: Контейнер PostgreSQL '$POSTGRES_CONTAINER' не запущен!${NC}"
        echo "Запустите PostgreSQL: docker compose up -d postgres"
        exit 1
    fi
    
    # Создаем директорию для миграции
    MIGRATION_DIR="migration"
    mkdir -p "$MIGRATION_DIR"
    
    # Формируем имя файла дампа
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    DUMP_FILE="$MIGRATION_DIR/migration_dump_${TIMESTAMP}.sql"
    
    echo "База данных: $POSTGRES_DB"
    echo "Пользователь: $POSTGRES_USER"
    echo "Контейнер: $POSTGRES_CONTAINER"
    echo "Файл дампа: $DUMP_FILE"
    
    echo -e "${YELLOW}Создание дампа базы данных...${NC}"
    
    # Создаем дамп
    if docker exec "$POSTGRES_CONTAINER" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$DUMP_FILE"; then
        # Проверяем размер файла
        FILE_SIZE=$(stat -f%z "$DUMP_FILE" 2>/dev/null || stat -c%s "$DUMP_FILE" 2>/dev/null || echo "0")
        
        if [ "$FILE_SIZE" -lt 100 ]; then
            echo -e "${RED}ОШИБКА: Размер файла дампа подозрительно мал ($FILE_SIZE байт)!${NC}"
            rm -f "$DUMP_FILE"
            exit 1
        fi
        
        # Сжимаем дамп
        echo -e "${YELLOW}Сжатие дампа...${NC}"
        gzip -f "$DUMP_FILE"
        DUMP_FILE="${DUMP_FILE}.gz"
        
        FILE_SIZE=$(stat -f%z "$DUMP_FILE" 2>/dev/null || stat -c%s "$DUMP_FILE" 2>/dev/null || echo "0")
        FILE_SIZE_MB=$((FILE_SIZE / 1024 / 1024))
        
        echo -e "${GREEN}✅ Дамп успешно создан!${NC}"
        echo "Файл: $DUMP_FILE"
        echo "Размер: ${FILE_SIZE_MB} MB"
        echo ""
        echo -e "${BLUE}Следующие шаги:${NC}"
        echo "1. Скопируйте файл '$DUMP_FILE' на новый сервер"
        echo "2. На новом сервере выполните: ./scripts/migrate_db.sh import $DUMP_FILE"
        echo ""
        echo "Пример копирования:"
        echo "  scp $DUMP_FILE user@new-server.com:/path/to/Liza_patry_bot/migration/"
        
        exit 0
    else
        echo -e "${RED}ОШИБКА: Не удалось создать дамп!${NC}"
        exit 1
    fi
}

# Функция для импорта (восстановление из дампа)
import_db() {
    if [ -z "$1" ]; then
        echo -e "${RED}ОШИБКА: Укажите файл дампа для импорта!${NC}"
        echo "Использование: $0 import <dump_file>"
        echo "Пример: $0 import migration/migration_dump_20240101_120000.sql.gz"
        exit 1
    fi
    
    DUMP_FILE="$1"
    
    echo -e "${BLUE}=== Импорт базы данных из дампа ===${NC}"
    
    # Проверяем существование файла
    if [ ! -f "$DUMP_FILE" ]; then
        echo -e "${RED}ОШИБКА: Файл '$DUMP_FILE' не найден!${NC}"
        exit 1
    fi
    
    echo "База данных: $POSTGRES_DB"
    echo "Пользователь: $POSTGRES_USER"
    echo "Контейнер: $POSTGRES_CONTAINER"
    echo "Файл дампа: $DUMP_FILE"
    
    echo -e "${YELLOW}⚠️  ВНИМАНИЕ: Импорт приведет к потере всех текущих данных в БД!${NC}"
    read -p "Вы уверены, что хотите продолжить? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Импорт отменен."
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
    if [[ "$DUMP_FILE" == *.gz ]]; then
        echo -e "${YELLOW}Распаковка сжатого дампа...${NC}"
        TEMP_FILE=$(mktemp)
        gunzip -c "$DUMP_FILE" > "$TEMP_FILE"
        DUMP_TO_IMPORT="$TEMP_FILE"
    else
        DUMP_TO_IMPORT="$DUMP_FILE"
    fi
    
    # Останавливаем бота (если запущен)
    if docker ps | grep -q "ym_bot"; then
        echo -e "${YELLOW}Остановка бота...${NC}"
        docker compose stop bot || true
    fi
    
    # Восстанавливаем базу данных
    echo -e "${YELLOW}Восстановление базы данных из дампа...${NC}"
    
    # Сначала удаляем существующую БД и создаем новую
    echo "Удаление существующей базы данных (если есть)..."
    docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS $POSTGRES_DB;" postgres || true
    
    echo "Создание новой базы данных..."
    docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c "CREATE DATABASE $POSTGRES_DB;" postgres
    
    # Восстанавливаем данные
    echo "Восстановление данных из дампа..."
    if docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" "$POSTGRES_DB" < "$DUMP_TO_IMPORT"; then
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
        
        echo -e "${GREEN}Миграция завершена успешно!${NC}"
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
}

# Главная логика
case "$1" in
    export)
        export_db
        ;;
    import)
        import_db "$2"
        ;;
    *)
        echo -e "${RED}ОШИБКА: Неизвестная команда!${NC}"
        echo ""
        echo "Использование:"
        echo "  $0 export                    # Создать дамп для миграции"
        echo "  $0 import <dump_file>         # Восстановить из дампа"
        echo ""
        echo "Примеры:"
        echo "  $0 export"
        echo "  $0 import migration/migration_dump_20240101_120000.sql.gz"
        exit 1
        ;;
esac

