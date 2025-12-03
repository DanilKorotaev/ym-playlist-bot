"""
Реализация базы данных для PostgreSQL.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
import os
from typing import Optional, List, Dict
from datetime import datetime
from contextlib import contextmanager

from .base import DatabaseInterface

logger = logging.getLogger(__name__)


class PostgreSQLDatabase(DatabaseInterface):
    """Класс для работы с базой данных PostgreSQL."""
    
    def __init__(self, 
                 host: Optional[str] = None,
                 port: Optional[int] = None,
                 database: Optional[str] = None,
                 user: Optional[str] = None,
                 password: Optional[str] = None):
        """
        Инициализация подключения к PostgreSQL.
        
        Параметры берутся из переменных окружения:
        - DB_HOST (по умолчанию: localhost)
        - DB_PORT (по умолчанию: 5432)
        - DB_NAME (по умолчанию: yandex_music_bot)
        - DB_USER (по умолчанию: postgres)
        - DB_PASSWORD (обязательно)
        """
        self.host = host or os.getenv("DB_HOST", "localhost")
        self.port = port or int(os.getenv("DB_PORT", "5432"))
        self.database = database or os.getenv("DB_NAME", "yandex_music_bot")
        self.user = user or os.getenv("DB_USER", "postgres")
        self.password = password or os.getenv("DB_PASSWORD")
        
        if not self.password:
            raise ValueError("DB_PASSWORD не установлен в переменных окружения")
        
        self.connection_params = {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password
        }
        
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """Получить соединение с БД (context manager)."""
        conn = psycopg2.connect(**self.connection_params)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def init_db(self):
        """Инициализировать структуру БД."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Таблица пользователей Telegram
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        telegram_id BIGINT PRIMARY KEY,
                        username TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                # Таблица аккаунтов Яндекс.Музыки
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS yandex_accounts (
                        id SERIAL PRIMARY KEY,
                        telegram_id BIGINT,
                        token TEXT NOT NULL,
                        is_default BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                    )
                """)
                
                # Частичные уникальные индексы для правильной работы с NULL
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_yandex_account_user_default 
                    ON yandex_accounts(telegram_id, is_default) 
                    WHERE telegram_id IS NOT NULL
                """)
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_yandex_account_global_default 
                    ON yandex_accounts(is_default) 
                    WHERE telegram_id IS NULL AND is_default = TRUE
                """)
                
                # Таблица плейлистов
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS playlists (
                        id SERIAL PRIMARY KEY,
                        playlist_kind TEXT NOT NULL,
                        owner_id TEXT NOT NULL,
                        creator_telegram_id BIGINT NOT NULL,
                        yandex_account_id INTEGER,
                        title TEXT,
                        description TEXT,
                        cover_url TEXT,
                        share_token TEXT UNIQUE,
                        insert_position TEXT DEFAULT 'end' CHECK (insert_position IN ('start', 'end')),
                        uuid TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW(),
                        FOREIGN KEY (creator_telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
                        FOREIGN KEY (yandex_account_id) REFERENCES yandex_accounts(id) ON DELETE SET NULL
                    )
                """)
                
                # Миграция: добавляем поле insert_position если его нет
                cursor.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='playlists' AND column_name='insert_position'
                        ) THEN
                            ALTER TABLE playlists ADD COLUMN insert_position TEXT DEFAULT 'end' CHECK (insert_position IN ('start', 'end'));
                        END IF;
                    END $$;
                """)
                
                # Миграция: добавляем поле uuid если его нет
                cursor.execute("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='playlists' AND column_name='uuid'
                        ) THEN
                            ALTER TABLE playlists ADD COLUMN uuid TEXT;
                        END IF;
                    END $$;
                """)
                
                # Таблица доступа к плейлистам (кто может добавлять треки)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS playlist_access (
                        id SERIAL PRIMARY KEY,
                        playlist_id INTEGER NOT NULL,
                        telegram_id BIGINT NOT NULL,
                        can_add BOOLEAN DEFAULT TRUE,
                        can_edit BOOLEAN DEFAULT FALSE,
                        can_delete BOOLEAN DEFAULT FALSE,
                        first_access_at TIMESTAMP DEFAULT NOW(),
                        FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
                        UNIQUE(playlist_id, telegram_id)
                    )
                """)
                
                # Таблица действий пользователей
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS actions (
                        id SERIAL PRIMARY KEY,
                        telegram_id BIGINT NOT NULL,
                        playlist_id INTEGER,
                        action_type TEXT NOT NULL,
                        action_data TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
                        FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE SET NULL
                    )
                """)
                
                # Таблица подписок пользователей
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_subscriptions (
                        id SERIAL PRIMARY KEY,
                        telegram_id BIGINT NOT NULL,
                        subscription_type TEXT NOT NULL,
                        stars_amount INTEGER NOT NULL,
                        purchased_at TIMESTAMP DEFAULT NOW(),
                        expires_at TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE,
                        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                    )
                """)
                
                # Таблица платежей
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS payments (
                        id SERIAL PRIMARY KEY,
                        telegram_id BIGINT NOT NULL,
                        invoice_payload TEXT NOT NULL UNIQUE,
                        stars_amount INTEGER NOT NULL,
                        subscription_type TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT NOW(),
                        completed_at TIMESTAMP,
                        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                    )
                """)
                
                # Индексы для ускорения запросов
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_creator ON playlists(creator_telegram_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_share_token ON playlists(share_token)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_access_playlist ON playlist_access(playlist_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_access_user ON playlist_access(telegram_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_user ON actions(telegram_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_playlist ON actions(playlist_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_yandex_account_telegram ON yandex_accounts(telegram_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_subscriptions_telegram_id ON user_subscriptions(telegram_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_subscriptions_active ON user_subscriptions(telegram_id, is_active)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_telegram_id ON payments(telegram_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_payments_payload ON payments(invoice_payload)")
            
            logger.info("База данных PostgreSQL инициализирована")
    
    # === Работа с пользователями ===
    
    def ensure_user(self, telegram_id: int, username: Optional[str] = None):
        """Создать или обновить пользователя."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO users (telegram_id, username, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (telegram_id) 
                    DO UPDATE SET username = EXCLUDED.username, updated_at = NOW()
                """, (telegram_id, username))
    
    def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить информацию о пользователе."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
    
    # === Работа с аккаунтами Яндекс.Музыки ===
    
    def set_default_yandex_account(self, token: str):
        """Установить дефолтный аккаунт Яндекс.Музыки (без привязки к пользователю)."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Удаляем старый дефолтный аккаунт
                cursor.execute("DELETE FROM yandex_accounts WHERE is_default = TRUE AND telegram_id IS NULL")
                # Добавляем новый
                cursor.execute("""
                    INSERT INTO yandex_accounts (telegram_id, token, is_default)
                    VALUES (NULL, %s, TRUE)
                """, (token,))
    
    def get_default_yandex_account(self) -> Optional[Dict]:
        """Получить дефолтный аккаунт Яндекс.Музыки."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM yandex_accounts 
                    WHERE is_default = TRUE AND telegram_id IS NULL
                    ORDER BY id DESC LIMIT 1
                """)
                row = cursor.fetchone()
                return dict(row) if row else None
    
    def set_user_yandex_token(self, telegram_id: int, token: str):
        """Установить токен Яндекс.Музыки для пользователя."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Удаляем старый токен пользователя
                cursor.execute("DELETE FROM yandex_accounts WHERE telegram_id = %s AND is_default = FALSE", (telegram_id,))
                # Добавляем новый
                cursor.execute("""
                    INSERT INTO yandex_accounts (telegram_id, token, is_default)
                    VALUES (%s, %s, FALSE)
                """, (telegram_id, token))
    
    def get_user_yandex_token(self, telegram_id: int) -> Optional[str]:
        """Получить токен Яндекс.Музыки пользователя."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT token FROM yandex_accounts 
                    WHERE telegram_id = %s AND is_default = FALSE
                    ORDER BY id DESC LIMIT 1
                """, (telegram_id,))
                row = cursor.fetchone()
                return row["token"] if row else None
    
    def get_yandex_account_for_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить аккаунт Яндекс.Музыки для пользователя (сначала свой, потом дефолтный)."""
        # Сначала пробуем получить токен пользователя
        user_token = self.get_user_yandex_token(telegram_id)
        if user_token:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT * FROM yandex_accounts 
                        WHERE telegram_id = %s AND is_default = FALSE
                        ORDER BY id DESC LIMIT 1
                    """, (telegram_id,))
                    row = cursor.fetchone()
                    if row:
                        return dict(row)
        
        # Если нет своего, возвращаем дефолтный
        return self.get_default_yandex_account()
    
    def get_yandex_account_by_id(self, account_id: int) -> Optional[Dict]:
        """Получить аккаунт Яндекс.Музыки по ID."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM yandex_accounts WHERE id = %s", (account_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
    
    # === Работа с плейлистами ===
    
    def create_playlist(self, playlist_kind: str, owner_id: str, creator_telegram_id: int,
                       yandex_account_id: Optional[int] = None, title: Optional[str] = None,
                       share_token: Optional[str] = None, insert_position: str = 'end',
                       uuid: Optional[str] = None) -> int:
        """Создать новый плейлист."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO playlists (playlist_kind, owner_id, creator_telegram_id, 
                                         yandex_account_id, title, share_token, insert_position, uuid)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (playlist_kind, owner_id, creator_telegram_id, yandex_account_id, title, share_token, insert_position, uuid))
                playlist_id = cursor.fetchone()["id"]
                
                # Автоматически даем создателю полный доступ
                cursor.execute("""
                    INSERT INTO playlist_access (playlist_id, telegram_id, can_add, can_edit, can_delete)
                    VALUES (%s, %s, TRUE, TRUE, TRUE)
                """, (playlist_id, creator_telegram_id))
                
                return playlist_id
    
    def get_playlist(self, playlist_id: int) -> Optional[Dict]:
        """Получить информацию о плейлисте."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM playlists WHERE id = %s", (playlist_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
    
    def get_playlist_by_share_token(self, share_token: str) -> Optional[Dict]:
        """Получить плейлист по токену для шаринга."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM playlists WHERE share_token = %s", (share_token,))
                row = cursor.fetchone()
                return dict(row) if row else None
    
    def get_playlist_by_kind_and_owner(self, playlist_kind: str, owner_id: str) -> Optional[Dict]:
        """Получить плейлист по kind и owner_id."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM playlists 
                    WHERE playlist_kind = %s AND owner_id = %s
                    ORDER BY id DESC LIMIT 1
                """, (playlist_kind, owner_id))
                row = cursor.fetchone()
                return dict(row) if row else None
    
    def get_user_playlists(self, telegram_id: int, only_created: bool = False) -> List[Dict]:
        """Получить плейлисты пользователя."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                if only_created:
                    # Только созданные пользователем
                    cursor.execute("""
                        SELECT p.* FROM playlists p
                        WHERE p.creator_telegram_id = %s
                        ORDER BY p.created_at DESC
                    """, (telegram_id,))
                else:
                    # Все плейлисты, к которым есть доступ
                    cursor.execute("""
                        SELECT DISTINCT p.* FROM playlists p
                        LEFT JOIN playlist_access pa ON p.id = pa.playlist_id
                        WHERE p.creator_telegram_id = %s OR pa.telegram_id = %s
                        ORDER BY p.created_at DESC
                    """, (telegram_id, telegram_id))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
    
    def count_user_playlists(self, telegram_id: int) -> int:
        """Подсчитать количество созданных пользователем плейлистов."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM playlists
                    WHERE creator_telegram_id = %s
                """, (telegram_id,))
                row = cursor.fetchone()
                return row["count"] if row else 0
    
    def get_shared_playlists(self, telegram_id: int) -> List[Dict]:
        """Получить плейлисты, куда пользователь добавляет (но не создавал)."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT DISTINCT p.* FROM playlists p
                    INNER JOIN playlist_access pa ON p.id = pa.playlist_id
                    WHERE pa.telegram_id = %s AND p.creator_telegram_id != %s
                    ORDER BY p.created_at DESC
                """, (telegram_id, telegram_id))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
    
    def update_playlist(self, playlist_id: int, title: Optional[str] = None,
                       description: Optional[str] = None, cover_url: Optional[str] = None,
                       share_token: Optional[str] = None, insert_position: Optional[str] = None,
                       uuid: Optional[str] = None):
        """Обновить информацию о плейлисте."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                updates = []
                params = []
                
                if title is not None:
                    updates.append("title = %s")
                    params.append(title)
                if description is not None:
                    updates.append("description = %s")
                    params.append(description)
                if cover_url is not None:
                    updates.append("cover_url = %s")
                    params.append(cover_url)
                if share_token is not None:
                    updates.append("share_token = %s")
                    params.append(share_token)
                if insert_position is not None:
                    updates.append("insert_position = %s")
                    params.append(insert_position)
                if uuid is not None:
                    updates.append("uuid = %s")
                    params.append(uuid)
                
                if updates:
                    updates.append("updated_at = NOW()")
                    params.append(playlist_id)
                    cursor.execute(f"""
                        UPDATE playlists 
                        SET {', '.join(updates)}
                        WHERE id = %s
                    """, params)
    
    def delete_playlist(self, playlist_id: int):
        """Удалить плейлист (каскадно удалит доступы и действия)."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("DELETE FROM playlists WHERE id = %s", (playlist_id,))
    
    # === Работа с доступом ===
    
    def grant_playlist_access(self, playlist_id: int, telegram_id: int,
                             can_add: bool = True, can_edit: bool = False, can_delete: bool = False):
        """Предоставить доступ к плейлисту."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO playlist_access 
                    (playlist_id, telegram_id, can_add, can_edit, can_delete)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (playlist_id, telegram_id)
                    DO UPDATE SET 
                        can_add = EXCLUDED.can_add,
                        can_edit = EXCLUDED.can_edit,
                        can_delete = EXCLUDED.can_delete
                """, (playlist_id, telegram_id, can_add, can_edit, can_delete))
    
    def check_playlist_access(self, playlist_id: int, telegram_id: int,
                             need_add: bool = False, need_edit: bool = False,
                             need_delete: bool = False) -> bool:
        """Проверить доступ пользователя к плейлисту."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT can_add, can_edit, can_delete FROM playlist_access
                    WHERE playlist_id = %s AND telegram_id = %s
                """, (playlist_id, telegram_id))
                row = cursor.fetchone()
                
                if not row:
                    return False
                
                if need_add and not row["can_add"]:
                    return False
                if need_edit and not row["can_edit"]:
                    return False
                if need_delete and not row["can_delete"]:
                    return False
                
                return True
    
    def is_playlist_creator(self, playlist_id: int, telegram_id: int) -> bool:
        """Проверить, является ли пользователь создателем плейлиста."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT creator_telegram_id FROM playlists
                    WHERE id = %s AND creator_telegram_id = %s
                """, (playlist_id, telegram_id))
                row = cursor.fetchone()
                return row is not None
    
    # === Работа с действиями ===
    
    def log_action(self, telegram_id: int, action_type: str, playlist_id: Optional[int] = None,
                   action_data: Optional[str] = None):
        """Записать действие пользователя."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO actions (telegram_id, playlist_id, action_type, action_data)
                    VALUES (%s, %s, %s, %s)
                """, (telegram_id, playlist_id, action_type, action_data))
    
    def get_user_actions(self, telegram_id: int, limit: int = 100) -> List[Dict]:
        """Получить последние действия пользователя."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM actions
                    WHERE telegram_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (telegram_id, limit))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
    
    def get_playlist_actions(self, playlist_id: int, limit: int = 100) -> List[Dict]:
        """Получить последние действия с плейлистом."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM actions
                    WHERE playlist_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (playlist_id, limit))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
    
    # === Работа с подписками и лимитами ===
    
    def get_user_playlist_limit(self, telegram_id: int) -> int:
        """Получить текущий лимит плейлистов для пользователя."""
        import os
        DEFAULT_PLAYLIST_LIMIT = 2
        PLAYLIST_LIMIT = int(os.getenv("PLAYLIST_LIMIT", DEFAULT_PLAYLIST_LIMIT))
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Получаем активную подписку
                cursor.execute("""
                    SELECT subscription_type FROM user_subscriptions
                    WHERE telegram_id = %s AND is_active = TRUE
                    AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY purchased_at DESC
                    LIMIT 1
                """, (telegram_id,))
                row = cursor.fetchone()
                
                if row:
                    subscription_type = row["subscription_type"]
                    # Парсим тип подписки для получения лимита
                    if subscription_type == "playlist_limit_unlimited":
                        return -1
                    elif subscription_type.startswith("playlist_limit_"):
                        try:
                            limit_str = subscription_type.replace("playlist_limit_", "")
                            if limit_str == "unlimited":
                                return -1
                            return int(limit_str)
                        except ValueError:
                            pass
                
                return PLAYLIST_LIMIT
    
    def create_subscription(self, telegram_id: int, subscription_type: str, 
                           stars_amount: int, expires_at: Optional[datetime] = None) -> int:
        """Создать подписку для пользователя."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Деактивируем старые подписки того же типа
                cursor.execute("""
                    UPDATE user_subscriptions
                    SET is_active = FALSE
                    WHERE telegram_id = %s AND subscription_type = %s AND is_active = TRUE
                """, (telegram_id, subscription_type))
                
                # Создаем новую подписку
                cursor.execute("""
                    INSERT INTO user_subscriptions 
                    (telegram_id, subscription_type, stars_amount, expires_at)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (telegram_id, subscription_type, stars_amount, expires_at))
                result = cursor.fetchone()
                return result["id"]
    
    def get_active_subscription(self, telegram_id: int) -> Optional[Dict]:
        """Получить активную подписку пользователя."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM user_subscriptions
                    WHERE telegram_id = %s AND is_active = TRUE
                    AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY purchased_at DESC
                    LIMIT 1
                """, (telegram_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
    
    # === Работа с платежами ===
    
    def create_payment(self, telegram_id: int, invoice_payload: str, 
                      stars_amount: int, subscription_type: str) -> int:
        """Создать запись о платеже."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO payments 
                    (telegram_id, invoice_payload, stars_amount, subscription_type, status)
                    VALUES (%s, %s, %s, %s, 'pending')
                    RETURNING id
                """, (telegram_id, invoice_payload, stars_amount, subscription_type))
                result = cursor.fetchone()
                return result["id"]
    
    def update_payment_status(self, invoice_payload: str, status: str):
        """Обновить статус платежа."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                completed_at = datetime.now() if status == "completed" else None
                cursor.execute("""
                    UPDATE payments
                    SET status = %s, completed_at = %s
                    WHERE invoice_payload = %s
                """, (status, completed_at, invoice_payload))
    
    def get_payment_by_payload(self, invoice_payload: str) -> Optional[Dict]:
        """Получить платеж по payload."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM payments
                    WHERE invoice_payload = %s
                """, (invoice_payload,))
                row = cursor.fetchone()
                return dict(row) if row else None

