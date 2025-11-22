"""
Абстрактный базовый класс для работы с базой данных.
Определяет интерфейс, который должны реализовывать все конкретные реализации БД.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict


class DatabaseInterface(ABC):
    """Абстрактный интерфейс для работы с базой данных."""
    
    @abstractmethod
    def init_db(self):
        """Инициализировать структуру БД."""
        pass
    
    # === Работа с пользователями ===
    
    @abstractmethod
    def ensure_user(self, telegram_id: int, username: Optional[str] = None):
        """Создать или обновить пользователя."""
        pass
    
    @abstractmethod
    def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить информацию о пользователе."""
        pass
    
    # === Работа с аккаунтами Яндекс.Музыки ===
    
    @abstractmethod
    def set_default_yandex_account(self, token: str):
        """Установить дефолтный аккаунт Яндекс.Музыки (без привязки к пользователю)."""
        pass
    
    @abstractmethod
    def get_default_yandex_account(self) -> Optional[Dict]:
        """Получить дефолтный аккаунт Яндекс.Музыки."""
        pass
    
    @abstractmethod
    def set_user_yandex_token(self, telegram_id: int, token: str):
        """Установить токен Яндекс.Музыки для пользователя."""
        pass
    
    @abstractmethod
    def get_user_yandex_token(self, telegram_id: int) -> Optional[str]:
        """Получить токен Яндекс.Музыки пользователя."""
        pass
    
    @abstractmethod
    def get_yandex_account_for_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить аккаунт Яндекс.Музыки для пользователя (сначала свой, потом дефолтный)."""
        pass
    
    @abstractmethod
    def get_yandex_account_by_id(self, account_id: int) -> Optional[Dict]:
        """Получить аккаунт Яндекс.Музыки по ID."""
        pass
    
    # === Работа с плейлистами ===
    
    @abstractmethod
    def create_playlist(self, playlist_kind: str, owner_id: str, creator_telegram_id: int,
                       yandex_account_id: Optional[int] = None, title: Optional[str] = None,
                       share_token: Optional[str] = None) -> int:
        """Создать новый плейлист."""
        pass
    
    @abstractmethod
    def get_playlist(self, playlist_id: int) -> Optional[Dict]:
        """Получить информацию о плейлисте."""
        pass
    
    @abstractmethod
    def get_playlist_by_share_token(self, share_token: str) -> Optional[Dict]:
        """Получить плейлист по токену для шаринга."""
        pass
    
    @abstractmethod
    def get_playlist_by_kind_and_owner(self, playlist_kind: str, owner_id: str) -> Optional[Dict]:
        """Получить плейлист по kind и owner_id."""
        pass
    
    @abstractmethod
    def get_user_playlists(self, telegram_id: int, only_created: bool = False) -> List[Dict]:
        """Получить плейлисты пользователя."""
        pass
    
    @abstractmethod
    def get_shared_playlists(self, telegram_id: int) -> List[Dict]:
        """Получить плейлисты, куда пользователь добавляет (но не создавал)."""
        pass
    
    @abstractmethod
    def update_playlist(self, playlist_id: int, title: Optional[str] = None,
                       description: Optional[str] = None, cover_url: Optional[str] = None,
                       share_token: Optional[str] = None):
        """Обновить информацию о плейлисте."""
        pass
    
    @abstractmethod
    def delete_playlist(self, playlist_id: int):
        """Удалить плейлист (каскадно удалит доступы и действия)."""
        pass
    
    # === Работа с доступом ===
    
    @abstractmethod
    def grant_playlist_access(self, playlist_id: int, telegram_id: int,
                             can_add: bool = True, can_edit: bool = False, can_delete: bool = False):
        """Предоставить доступ к плейлисту."""
        pass
    
    @abstractmethod
    def check_playlist_access(self, playlist_id: int, telegram_id: int,
                             need_add: bool = False, need_edit: bool = False,
                             need_delete: bool = False) -> bool:
        """Проверить доступ пользователя к плейлисту."""
        pass
    
    @abstractmethod
    def is_playlist_creator(self, playlist_id: int, telegram_id: int) -> bool:
        """Проверить, является ли пользователь создателем плейлиста."""
        pass
    
    # === Работа с действиями ===
    
    @abstractmethod
    def log_action(self, telegram_id: int, action_type: str, playlist_id: Optional[int] = None,
                   action_data: Optional[str] = None):
        """Записать действие пользователя."""
        pass
    
    @abstractmethod
    def get_user_actions(self, telegram_id: int, limit: int = 100) -> List[Dict]:
        """Получить последние действия пользователя."""
        pass
    
    @abstractmethod
    def get_playlist_actions(self, playlist_id: int, limit: int = 100) -> List[Dict]:
        """Получить последние действия с плейлистом."""
        pass

