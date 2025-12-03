"""
Реализация базы данных для SQLite с использованием aiosqlite.
"""
import aiosqlite
import logging
import os
from typing import Optional, List, Dict
from datetime import datetime

from .base import DatabaseInterface

logger = logging.getLogger(__name__)

DB_FILE_DEFAULT = "bot.db"


class SQLiteDatabase(DatabaseInterface):
    """Класс для работы с базой данных SQLite."""
    
    def __init__(self, db_file: Optional[str] = None):
        """
        Инициализация подключения к SQLite.
        
        Args:
            db_file: Путь к файлу БД. Если не указан, берется из DB_FILE или используется bot.db
        """
        self.db_file = db_file or os.getenv("DB_FILE", DB_FILE_DEFAULT)
    
    async def _execute(self, query: str, *args):
        """Выполнить запрос без возврата результата."""
        async with aiosqlite.connect(self.db_file) as conn:
            await conn.execute(query, args)
            await conn.commit()
    
    async def _fetchrow(self, query: str, *args) -> Optional[aiosqlite.Row]:
        """Выполнить запрос и вернуть одну строку."""
        async with aiosqlite.connect(self.db_file) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, args) as cursor:
                row = await cursor.fetchone()
                return row
    
    async def _fetch(self, query: str, *args) -> List[aiosqlite.Row]:
        """Выполнить запрос и вернуть все строки."""
        async with aiosqlite.connect(self.db_file) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, args) as cursor:
                rows = await cursor.fetchall()
                return rows
    
    async def init_db(self):
        """Инициализировать структуру БД."""
        async with aiosqlite.connect(self.db_file) as conn:
            # Таблица пользователей Telegram
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица аккаунтов Яндекс.Музыки
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS yandex_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER,
                    token TEXT NOT NULL,
                    is_default BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id),
                    UNIQUE(telegram_id, is_default)
                )
            """)
            
            # Таблица плейлистов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_kind TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    creator_telegram_id INTEGER NOT NULL,
                    yandex_account_id INTEGER,
                    title TEXT,
                    description TEXT,
                    cover_url TEXT,
                    share_token TEXT UNIQUE,
                    insert_position TEXT DEFAULT 'end' CHECK (insert_position IN ('start', 'end')),
                    uuid TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (creator_telegram_id) REFERENCES users(telegram_id),
                    FOREIGN KEY (yandex_account_id) REFERENCES yandex_accounts(id)
                )
            """)
            
            # Миграция: добавляем поле insert_position если его нет
            try:
                await conn.execute("ALTER TABLE playlists ADD COLUMN insert_position TEXT DEFAULT 'end'")
            except aiosqlite.OperationalError:
                # Колонка уже существует
                pass
            
            # Миграция: добавляем поле uuid если его нет
            try:
                await conn.execute("ALTER TABLE playlists ADD COLUMN uuid TEXT")
            except aiosqlite.OperationalError:
                # Колонка уже существует
                pass
            
            # Таблица доступа к плейлистам (кто может добавлять треки)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS playlist_access (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER NOT NULL,
                    telegram_id INTEGER NOT NULL,
                    can_add BOOLEAN DEFAULT 1,
                    can_edit BOOLEAN DEFAULT 0,
                    can_delete BOOLEAN DEFAULT 0,
                    first_access_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id),
                    UNIQUE(playlist_id, telegram_id)
                )
            """)
            
            # Таблица действий пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    playlist_id INTEGER,
                    action_type TEXT NOT NULL,
                    action_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id),
                    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE SET NULL
                )
            """)
            
            # Таблица подписок пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    subscription_type TEXT NOT NULL,
                    stars_amount INTEGER NOT NULL,
                    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                )
            """)
            
            # Таблица платежей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    invoice_payload TEXT NOT NULL UNIQUE,
                    stars_amount INTEGER NOT NULL,
                    subscription_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                )
            """)
            
            # Индексы для ускорения запросов
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_playlist_creator ON playlists(creator_telegram_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_playlist_share_token ON playlists(share_token)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_access_playlist ON playlist_access(playlist_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_access_user ON playlist_access(telegram_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_user ON actions(telegram_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_actions_playlist ON actions(playlist_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_yandex_account_telegram ON yandex_accounts(telegram_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_subscriptions_telegram_id ON user_subscriptions(telegram_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_subscriptions_active ON user_subscriptions(telegram_id, is_active)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_telegram_id ON payments(telegram_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_payload ON payments(invoice_payload)")
            
            await conn.commit()
            logger.info("База данных SQLite инициализирована")
    
    # === Работа с пользователями ===
    
    async def ensure_user(self, telegram_id: int, username: Optional[str] = None):
        """Создать или обновить пользователя."""
        await self._execute("""
            INSERT OR REPLACE INTO users (telegram_id, username, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, telegram_id, username)
    
    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить информацию о пользователе."""
        row = await self._fetchrow("SELECT * FROM users WHERE telegram_id = ?", telegram_id)
        return dict(row) if row else None
    
    # === Работа с аккаунтами Яндекс.Музыки ===
    
    async def set_default_yandex_account(self, token: str):
        """Установить дефолтный аккаунт Яндекс.Музыки (без привязки к пользователю)."""
        async with aiosqlite.connect(self.db_file) as conn:
            # Удаляем старый дефолтный аккаунт
            await conn.execute("DELETE FROM yandex_accounts WHERE is_default = 1 AND telegram_id IS NULL")
            # Добавляем новый
            await conn.execute("""
                INSERT INTO yandex_accounts (telegram_id, token, is_default)
                VALUES (NULL, ?, 1)
            """, (token,))
            await conn.commit()
    
    async def get_default_yandex_account(self) -> Optional[Dict]:
        """Получить дефолтный аккаунт Яндекс.Музыки."""
        row = await self._fetchrow("""
            SELECT * FROM yandex_accounts 
            WHERE is_default = 1 AND telegram_id IS NULL
            ORDER BY id DESC LIMIT 1
        """)
        return dict(row) if row else None
    
    async def set_user_yandex_token(self, telegram_id: int, token: str):
        """Установить токен Яндекс.Музыки для пользователя."""
        async with aiosqlite.connect(self.db_file) as conn:
            # Удаляем старый токен пользователя
            await conn.execute("DELETE FROM yandex_accounts WHERE telegram_id = ? AND is_default = 0", (telegram_id,))
            # Добавляем новый
            await conn.execute("""
                INSERT INTO yandex_accounts (telegram_id, token, is_default)
                VALUES (?, ?, 0)
            """, (telegram_id, token))
            await conn.commit()
    
    async def get_user_yandex_token(self, telegram_id: int) -> Optional[str]:
        """Получить токен Яндекс.Музыки пользователя."""
        row = await self._fetchrow("""
            SELECT token FROM yandex_accounts 
            WHERE telegram_id = ? AND is_default = 0
            ORDER BY id DESC LIMIT 1
        """, telegram_id)
        return row["token"] if row else None
    
    async def get_yandex_account_for_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить аккаунт Яндекс.Музыки для пользователя (сначала свой, потом дефолтный)."""
        # Сначала пробуем получить токен пользователя
        user_token = await self.get_user_yandex_token(telegram_id)
        if user_token:
            row = await self._fetchrow("""
                SELECT * FROM yandex_accounts 
                WHERE telegram_id = ? AND is_default = 0
                ORDER BY id DESC LIMIT 1
            """, telegram_id)
            if row:
                return dict(row)
        
        # Если нет своего, возвращаем дефолтный
        return await self.get_default_yandex_account()
    
    async def get_yandex_account_by_id(self, account_id: int) -> Optional[Dict]:
        """Получить аккаунт Яндекс.Музыки по ID."""
        row = await self._fetchrow("SELECT * FROM yandex_accounts WHERE id = ?", account_id)
        return dict(row) if row else None
    
    # === Работа с плейлистами ===
    
    async def create_playlist(self, playlist_kind: str, owner_id: str, creator_telegram_id: int,
                       yandex_account_id: Optional[int] = None, title: Optional[str] = None,
                       share_token: Optional[str] = None, insert_position: str = 'end',
                       uuid: Optional[str] = None) -> int:
        """Создать новый плейлист."""
        async with aiosqlite.connect(self.db_file) as conn:
            cursor = await conn.execute("""
                INSERT INTO playlists (playlist_kind, owner_id, creator_telegram_id, 
                                     yandex_account_id, title, share_token, insert_position, uuid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (playlist_kind, owner_id, creator_telegram_id, yandex_account_id, title, share_token, insert_position, uuid))
            playlist_id = cursor.lastrowid
            
            # Автоматически даем создателю полный доступ
            await conn.execute("""
                INSERT INTO playlist_access (playlist_id, telegram_id, can_add, can_edit, can_delete)
                VALUES (?, ?, 1, 1, 1)
            """, (playlist_id, creator_telegram_id))
            
            await conn.commit()
            return playlist_id
    
    async def get_playlist(self, playlist_id: int) -> Optional[Dict]:
        """Получить информацию о плейлисте."""
        row = await self._fetchrow("SELECT * FROM playlists WHERE id = ?", playlist_id)
        return dict(row) if row else None
    
    async def get_playlist_by_share_token(self, share_token: str) -> Optional[Dict]:
        """Получить плейлист по токену для шаринга."""
        row = await self._fetchrow("SELECT * FROM playlists WHERE share_token = ?", share_token)
        return dict(row) if row else None
    
    async def get_playlist_by_kind_and_owner(self, playlist_kind: str, owner_id: str) -> Optional[Dict]:
        """Получить плейлист по kind и owner_id."""
        row = await self._fetchrow("""
            SELECT * FROM playlists 
            WHERE playlist_kind = ? AND owner_id = ?
            ORDER BY id DESC LIMIT 1
        """, playlist_kind, owner_id)
        return dict(row) if row else None
    
    async def get_user_playlists(self, telegram_id: int, only_created: bool = False) -> List[Dict]:
        """Получить плейлисты пользователя."""
        if only_created:
            # Только созданные пользователем
            rows = await self._fetch("""
                SELECT p.* FROM playlists p
                WHERE p.creator_telegram_id = ?
                ORDER BY p.created_at DESC
            """, telegram_id)
        else:
            # Все плейлисты, к которым есть доступ
            rows = await self._fetch("""
                SELECT DISTINCT p.* FROM playlists p
                LEFT JOIN playlist_access pa ON p.id = pa.playlist_id
                WHERE p.creator_telegram_id = ? OR pa.telegram_id = ?
                ORDER BY p.created_at DESC
            """, telegram_id, telegram_id)
        
        return [dict(row) for row in rows]
    
    async def count_user_playlists(self, telegram_id: int) -> int:
        """Подсчитать количество созданных пользователем плейлистов."""
        row = await self._fetchrow("""
            SELECT COUNT(*) as count FROM playlists
            WHERE creator_telegram_id = ?
        """, telegram_id)
        return row["count"] if row else 0
    
    async def get_shared_playlists(self, telegram_id: int) -> List[Dict]:
        """Получить плейлисты, куда пользователь добавляет (но не создавал)."""
        rows = await self._fetch("""
            SELECT DISTINCT p.* FROM playlists p
            INNER JOIN playlist_access pa ON p.id = pa.playlist_id
            WHERE pa.telegram_id = ? AND p.creator_telegram_id != ?
            ORDER BY p.created_at DESC
        """, telegram_id, telegram_id)
        return [dict(row) for row in rows]
    
    async def update_playlist(self, playlist_id: int, title: Optional[str] = None,
                       description: Optional[str] = None, cover_url: Optional[str] = None,
                       share_token: Optional[str] = None, insert_position: Optional[str] = None,
                       uuid: Optional[str] = None):
        """Обновить информацию о плейлисте."""
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if cover_url is not None:
            updates.append("cover_url = ?")
            params.append(cover_url)
        if share_token is not None:
            updates.append("share_token = ?")
            params.append(share_token)
        if insert_position is not None:
            updates.append("insert_position = ?")
            params.append(insert_position)
        if uuid is not None:
            updates.append("uuid = ?")
            params.append(uuid)
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(playlist_id)
            await self._execute(f"""
                UPDATE playlists 
                SET {', '.join(updates)}
                WHERE id = ?
            """, *params)
    
    async def delete_playlist(self, playlist_id: int):
        """Удалить плейлист (каскадно удалит доступы и действия)."""
        await self._execute("DELETE FROM playlists WHERE id = ?", playlist_id)
    
    # === Работа с доступом ===
    
    async def grant_playlist_access(self, playlist_id: int, telegram_id: int,
                             can_add: bool = True, can_edit: bool = False, can_delete: bool = False):
        """Предоставить доступ к плейлисту."""
        await self._execute("""
            INSERT OR REPLACE INTO playlist_access 
            (playlist_id, telegram_id, can_add, can_edit, can_delete)
            VALUES (?, ?, ?, ?, ?)
        """, playlist_id, telegram_id, can_add, can_edit, can_delete)
    
    async def check_playlist_access(self, playlist_id: int, telegram_id: int,
                             need_add: bool = False, need_edit: bool = False,
                             need_delete: bool = False) -> bool:
        """Проверить доступ пользователя к плейлисту."""
        row = await self._fetchrow("""
            SELECT can_add, can_edit, can_delete FROM playlist_access
            WHERE playlist_id = ? AND telegram_id = ?
        """, playlist_id, telegram_id)
        
        if not row:
            return False
        
        if need_add and not row["can_add"]:
            return False
        if need_edit and not row["can_edit"]:
            return False
        if need_delete and not row["can_delete"]:
            return False
        
        return True
    
    async def is_playlist_creator(self, playlist_id: int, telegram_id: int) -> bool:
        """Проверить, является ли пользователь создателем плейлиста."""
        row = await self._fetchrow("""
            SELECT creator_telegram_id FROM playlists
            WHERE id = ? AND creator_telegram_id = ?
        """, playlist_id, telegram_id)
        return row is not None
    
    # === Работа с действиями ===
    
    async def log_action(self, telegram_id: int, action_type: str, playlist_id: Optional[int] = None,
                   action_data: Optional[str] = None):
        """Записать действие пользователя."""
        await self._execute("""
            INSERT INTO actions (telegram_id, playlist_id, action_type, action_data)
            VALUES (?, ?, ?, ?)
        """, telegram_id, playlist_id, action_type, action_data)
    
    async def get_user_actions(self, telegram_id: int, limit: int = 100) -> List[Dict]:
        """Получить последние действия пользователя."""
        rows = await self._fetch("""
            SELECT * FROM actions
            WHERE telegram_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, telegram_id, limit)
        return [dict(row) for row in rows]
    
    async def get_playlist_actions(self, playlist_id: int, limit: int = 100) -> List[Dict]:
        """Получить последние действия с плейлистом."""
        rows = await self._fetch("""
            SELECT * FROM actions
            WHERE playlist_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, playlist_id, limit)
        return [dict(row) for row in rows]
    
    # === Работа с подписками и лимитами ===
    
    async def get_user_playlist_limit(self, telegram_id: int) -> int:
        """Получить текущий лимит плейлистов для пользователя."""
        import os
        DEFAULT_PLAYLIST_LIMIT = 2
        PLAYLIST_LIMIT = int(os.getenv("PLAYLIST_LIMIT", DEFAULT_PLAYLIST_LIMIT))
        
        row = await self._fetchrow("""
            SELECT subscription_type FROM user_subscriptions
            WHERE telegram_id = ? AND is_active = 1
            AND (expires_at IS NULL OR expires_at > datetime('now'))
            ORDER BY purchased_at DESC
            LIMIT 1
        """, telegram_id)
        
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
    
    async def create_subscription(self, telegram_id: int, subscription_type: str, 
                           stars_amount: int, expires_at: Optional[datetime] = None) -> int:
        """Создать подписку для пользователя."""
        async with aiosqlite.connect(self.db_file) as conn:
            # Деактивируем старые подписки того же типа
            await conn.execute("""
                UPDATE user_subscriptions
                SET is_active = 0
                WHERE telegram_id = ? AND subscription_type = ? AND is_active = 1
            """, (telegram_id, subscription_type))
            
            # Создаем новую подписку
            expires_at_str = expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else None
            cursor = await conn.execute("""
                INSERT INTO user_subscriptions 
                (telegram_id, subscription_type, stars_amount, expires_at)
                VALUES (?, ?, ?, ?)
            """, (telegram_id, subscription_type, stars_amount, expires_at_str))
            await conn.commit()
            return cursor.lastrowid
    
    async def get_active_subscription(self, telegram_id: int) -> Optional[Dict]:
        """Получить активную подписку пользователя."""
        row = await self._fetchrow("""
            SELECT * FROM user_subscriptions
            WHERE telegram_id = ? AND is_active = 1
            AND (expires_at IS NULL OR expires_at > datetime('now'))
            ORDER BY purchased_at DESC
            LIMIT 1
        """, telegram_id)
        return dict(row) if row else None
    
    # === Работа с платежами ===
    
    async def create_payment(self, telegram_id: int, invoice_payload: str, 
                      stars_amount: int, subscription_type: str) -> int:
        """Создать запись о платеже."""
        async with aiosqlite.connect(self.db_file) as conn:
            cursor = await conn.execute("""
                INSERT INTO payments 
                (telegram_id, invoice_payload, stars_amount, subscription_type, status)
                VALUES (?, ?, ?, ?, 'pending')
            """, (telegram_id, invoice_payload, stars_amount, subscription_type))
            await conn.commit()
            return cursor.lastrowid
    
    async def update_payment_status(self, invoice_payload: str, status: str):
        """Обновить статус платежа."""
        completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status == "completed" else None
        await self._execute("""
            UPDATE payments
            SET status = ?, completed_at = ?
            WHERE invoice_payload = ?
        """, status, completed_at, invoice_payload)
    
    async def get_payment_by_payload(self, invoice_payload: str) -> Optional[Dict]:
        """Получить платеж по payload."""
        row = await self._fetchrow("""
            SELECT * FROM payments
            WHERE invoice_payload = ?
        """, invoice_payload)
        return dict(row) if row else None
