"""
Модуль для работы с базой данных SQLite.
Хранит информацию о пользователях, плейлистах, доступах и действиях.
"""
import sqlite3
import logging
import os
from typing import Optional, List, Dict, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

DB_FILE = "bot.db"


class Database:
    """Класс для работы с базой данных."""
    
    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self.init_db()
    
    def get_connection(self) -> sqlite3.Connection:
        """Получить соединение с БД."""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Инициализировать структуру БД."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей Telegram
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица аккаунтов Яндекс.Музыки
        cursor.execute("""
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
        cursor.execute("""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (creator_telegram_id) REFERENCES users(telegram_id),
                FOREIGN KEY (yandex_account_id) REFERENCES yandex_accounts(id)
            )
        """)
        
        # Таблица доступа к плейлистам (кто может добавлять треки)
        cursor.execute("""
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
        cursor.execute("""
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
        
        # Индексы для ускорения запросов
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_creator ON playlists(creator_telegram_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_share_token ON playlists(share_token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_access_playlist ON playlist_access(playlist_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_access_user ON playlist_access(telegram_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_user ON actions(telegram_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_playlist ON actions(playlist_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_yandex_account_telegram ON yandex_accounts(telegram_id)")
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    
    # === Работа с пользователями ===
    
    def ensure_user(self, telegram_id: int, username: Optional[str] = None):
        """Создать или обновить пользователя."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO users (telegram_id, username, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (telegram_id, username))
        conn.commit()
        conn.close()
    
    def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить информацию о пользователе."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    # === Работа с аккаунтами Яндекс.Музыки ===
    
    def set_default_yandex_account(self, token: str):
        """Установить дефолтный аккаунт Яндекс.Музыки (без привязки к пользователю)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        # Удаляем старый дефолтный аккаунт
        cursor.execute("DELETE FROM yandex_accounts WHERE is_default = 1 AND telegram_id IS NULL")
        # Добавляем новый
        cursor.execute("""
            INSERT INTO yandex_accounts (telegram_id, token, is_default)
            VALUES (NULL, ?, 1)
        """, (token,))
        conn.commit()
        conn.close()
    
    def get_default_yandex_account(self) -> Optional[Dict]:
        """Получить дефолтный аккаунт Яндекс.Музыки."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM yandex_accounts 
            WHERE is_default = 1 AND telegram_id IS NULL
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def set_user_yandex_token(self, telegram_id: int, token: str):
        """Установить токен Яндекс.Музыки для пользователя."""
        conn = self.get_connection()
        cursor = conn.cursor()
        # Удаляем старый токен пользователя
        cursor.execute("DELETE FROM yandex_accounts WHERE telegram_id = ? AND is_default = 0", (telegram_id,))
        # Добавляем новый
        cursor.execute("""
            INSERT INTO yandex_accounts (telegram_id, token, is_default)
            VALUES (?, ?, 0)
        """, (telegram_id, token))
        conn.commit()
        conn.close()
    
    def get_user_yandex_token(self, telegram_id: int) -> Optional[str]:
        """Получить токен Яндекс.Музыки пользователя."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT token FROM yandex_accounts 
            WHERE telegram_id = ? AND is_default = 0
            ORDER BY id DESC LIMIT 1
        """, (telegram_id,))
        row = cursor.fetchone()
        conn.close()
        return row["token"] if row else None
    
    def get_yandex_account_for_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить аккаунт Яндекс.Музыки для пользователя (сначала свой, потом дефолтный)."""
        # Сначала пробуем получить токен пользователя
        user_token = self.get_user_yandex_token(telegram_id)
        if user_token:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM yandex_accounts 
                WHERE telegram_id = ? AND is_default = 0
                ORDER BY id DESC LIMIT 1
            """, (telegram_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(row)
        
        # Если нет своего, возвращаем дефолтный
        return self.get_default_yandex_account()
    
    # === Работа с плейлистами ===
    
    def create_playlist(self, playlist_kind: str, owner_id: str, creator_telegram_id: int,
                       yandex_account_id: Optional[int] = None, title: Optional[str] = None,
                       share_token: Optional[str] = None) -> int:
        """Создать новый плейлист."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO playlists (playlist_kind, owner_id, creator_telegram_id, 
                                 yandex_account_id, title, share_token)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (playlist_kind, owner_id, creator_telegram_id, yandex_account_id, title, share_token))
        playlist_id = cursor.lastrowid
        
        # Автоматически даем создателю полный доступ
        cursor.execute("""
            INSERT INTO playlist_access (playlist_id, telegram_id, can_add, can_edit, can_delete)
            VALUES (?, ?, 1, 1, 1)
        """, (playlist_id, creator_telegram_id))
        
        conn.commit()
        conn.close()
        return playlist_id
    
    def get_playlist(self, playlist_id: int) -> Optional[Dict]:
        """Получить информацию о плейлисте."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM playlists WHERE id = ?", (playlist_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_playlist_by_share_token(self, share_token: str) -> Optional[Dict]:
        """Получить плейлист по токену для шаринга."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM playlists WHERE share_token = ?", (share_token,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_playlist_by_kind_and_owner(self, playlist_kind: str, owner_id: str) -> Optional[Dict]:
        """Получить плейлист по kind и owner_id."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM playlists 
            WHERE playlist_kind = ? AND owner_id = ?
            ORDER BY id DESC LIMIT 1
        """, (playlist_kind, owner_id))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_user_playlists(self, telegram_id: int, only_created: bool = False) -> List[Dict]:
        """Получить плейлисты пользователя."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if only_created:
            # Только созданные пользователем
            cursor.execute("""
                SELECT p.* FROM playlists p
                WHERE p.creator_telegram_id = ?
                ORDER BY p.created_at DESC
            """, (telegram_id,))
        else:
            # Все плейлисты, к которым есть доступ
            cursor.execute("""
                SELECT DISTINCT p.* FROM playlists p
                LEFT JOIN playlist_access pa ON p.id = pa.playlist_id
                WHERE p.creator_telegram_id = ? OR pa.telegram_id = ?
                ORDER BY p.created_at DESC
            """, (telegram_id, telegram_id))
        
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_shared_playlists(self, telegram_id: int) -> List[Dict]:
        """Получить плейлисты, куда пользователь добавляет (но не создавал)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT p.* FROM playlists p
            INNER JOIN playlist_access pa ON p.id = pa.playlist_id
            WHERE pa.telegram_id = ? AND p.creator_telegram_id != ?
            ORDER BY p.created_at DESC
        """, (telegram_id, telegram_id))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def update_playlist(self, playlist_id: int, title: Optional[str] = None,
                       description: Optional[str] = None, cover_url: Optional[str] = None):
        """Обновить информацию о плейлисте."""
        conn = self.get_connection()
        cursor = conn.cursor()
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
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(playlist_id)
            cursor.execute(f"""
                UPDATE playlists 
                SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            conn.commit()
        
        conn.close()
    
    def delete_playlist(self, playlist_id: int):
        """Удалить плейлист (каскадно удалит доступы и действия)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        conn.commit()
        conn.close()
    
    # === Работа с доступом ===
    
    def grant_playlist_access(self, playlist_id: int, telegram_id: int,
                             can_add: bool = True, can_edit: bool = False, can_delete: bool = False):
        """Предоставить доступ к плейлисту."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO playlist_access 
            (playlist_id, telegram_id, can_add, can_edit, can_delete)
            VALUES (?, ?, ?, ?, ?)
        """, (playlist_id, telegram_id, can_add, can_edit, can_delete))
        conn.commit()
        conn.close()
    
    def check_playlist_access(self, playlist_id: int, telegram_id: int,
                             need_add: bool = False, need_edit: bool = False,
                             need_delete: bool = False) -> bool:
        """Проверить доступ пользователя к плейлисту."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT can_add, can_edit, can_delete FROM playlist_access
            WHERE playlist_id = ? AND telegram_id = ?
        """, (playlist_id, telegram_id))
        row = cursor.fetchone()
        conn.close()
        
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
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT creator_telegram_id FROM playlists
            WHERE id = ? AND creator_telegram_id = ?
        """, (playlist_id, telegram_id))
        row = cursor.fetchone()
        conn.close()
        return row is not None
    
    # === Работа с действиями ===
    
    def log_action(self, telegram_id: int, action_type: str, playlist_id: Optional[int] = None,
                   action_data: Optional[str] = None):
        """Записать действие пользователя."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO actions (telegram_id, playlist_id, action_type, action_data)
            VALUES (?, ?, ?, ?)
        """, (telegram_id, playlist_id, action_type, action_data))
        conn.commit()
        conn.close()
    
    def get_user_actions(self, telegram_id: int, limit: int = 100) -> List[Dict]:
        """Получить последние действия пользователя."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM actions
            WHERE telegram_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (telegram_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_playlist_actions(self, playlist_id: int, limit: int = 100) -> List[Dict]:
        """Получить последние действия с плейлистом."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM actions
            WHERE playlist_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (playlist_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

