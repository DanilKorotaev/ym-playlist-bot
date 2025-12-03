"""
Абстрактный базовый класс для работы с базой данных.
Определяет интерфейс, который должны реализовывать все конкретные реализации БД.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict


class DatabaseInterface(ABC):
    """Абстрактный интерфейс для работы с базой данных."""
    
    @abstractmethod
    async def init_db(self):
        """Инициализировать структуру БД."""
        pass
    
    # === Работа с пользователями ===
    
    @abstractmethod
    async def ensure_user(self, telegram_id: int, username: Optional[str] = None):
        """Создать или обновить пользователя."""
        pass
    
    @abstractmethod
    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить информацию о пользователе."""
        pass
    
    # === Работа с аккаунтами Яндекс.Музыки ===
    
    @abstractmethod
    async def set_default_yandex_account(self, token: str):
        """Установить дефолтный аккаунт Яндекс.Музыки (без привязки к пользователю)."""
        pass
    
    @abstractmethod
    async def get_default_yandex_account(self) -> Optional[Dict]:
        """Получить дефолтный аккаунт Яндекс.Музыки."""
        pass
    
    @abstractmethod
    async def set_user_yandex_token(self, telegram_id: int, token: str):
        """Установить токен Яндекс.Музыки для пользователя."""
        pass
    
    @abstractmethod
    async def get_user_yandex_token(self, telegram_id: int) -> Optional[str]:
        """Получить токен Яндекс.Музыки пользователя."""
        pass
    
    @abstractmethod
    async def get_yandex_account_for_user(self, telegram_id: int) -> Optional[Dict]:
        """Получить аккаунт Яндекс.Музыки для пользователя (сначала свой, потом дефолтный)."""
        pass
    
    @abstractmethod
    async def get_yandex_account_by_id(self, account_id: int) -> Optional[Dict]:
        """Получить аккаунт Яндекс.Музыки по ID."""
        pass
    
    # === Работа с плейлистами ===
    
    @abstractmethod
    async def create_playlist(self, playlist_kind: str, owner_id: str, creator_telegram_id: int,
                       yandex_account_id: Optional[int] = None, title: Optional[str] = None,
                       share_token: Optional[str] = None, insert_position: str = 'end',
                       uuid: Optional[str] = None) -> int:
        """Создать новый плейлист.
        
        Args:
            insert_position: 'start' для добавления в начало, 'end' для добавления в конец (по умолчанию 'end')
            uuid: UUID плейлиста для короткой ссылки
        """
        pass
    
    @abstractmethod
    async def get_playlist(self, playlist_id: int) -> Optional[Dict]:
        """Получить информацию о плейлисте."""
        pass
    
    @abstractmethod
    async def get_playlist_by_share_token(self, share_token: str) -> Optional[Dict]:
        """Получить плейлист по токену для шаринга."""
        pass
    
    @abstractmethod
    async def get_playlist_by_kind_and_owner(self, playlist_kind: str, owner_id: str) -> Optional[Dict]:
        """Получить плейлист по kind и owner_id."""
        pass
    
    @abstractmethod
    async def get_user_playlists(self, telegram_id: int, only_created: bool = False) -> List[Dict]:
        """Получить плейлисты пользователя."""
        pass
    
    @abstractmethod
    async def count_user_playlists(self, telegram_id: int) -> int:
        """Подсчитать количество созданных пользователем плейлистов."""
        pass
    
    @abstractmethod
    async def get_shared_playlists(self, telegram_id: int) -> List[Dict]:
        """Получить плейлисты, куда пользователь добавляет (но не создавал)."""
        pass
    
    @abstractmethod
    async def update_playlist(self, playlist_id: int, title: Optional[str] = None,
                       description: Optional[str] = None, cover_url: Optional[str] = None,
                       share_token: Optional[str] = None, insert_position: Optional[str] = None,
                       uuid: Optional[str] = None):
        """Обновить информацию о плейлисте.
        
        Args:
            insert_position: 'start' для добавления в начало, 'end' для добавления в конец (None - не обновлять)
            uuid: UUID плейлиста для короткой ссылки (None - не обновлять)
        """
        pass
    
    @abstractmethod
    async def delete_playlist(self, playlist_id: int):
        """Удалить плейлист (каскадно удалит доступы и действия)."""
        pass
    
    # === Работа с доступом ===
    
    @abstractmethod
    async def grant_playlist_access(self, playlist_id: int, telegram_id: int,
                             can_add: bool = True, can_edit: bool = False, can_delete: bool = False):
        """Предоставить доступ к плейлисту."""
        pass
    
    @abstractmethod
    async def check_playlist_access(self, playlist_id: int, telegram_id: int,
                             need_add: bool = False, need_edit: bool = False,
                             need_delete: bool = False) -> bool:
        """Проверить доступ пользователя к плейлисту."""
        pass
    
    @abstractmethod
    async def is_playlist_creator(self, playlist_id: int, telegram_id: int) -> bool:
        """Проверить, является ли пользователь создателем плейлиста."""
        pass
    
    # === Работа с действиями ===
    
    @abstractmethod
    async def log_action(self, telegram_id: int, action_type: str, playlist_id: Optional[int] = None,
                   action_data: Optional[str] = None):
        """Записать действие пользователя."""
        pass
    
    @abstractmethod
    async def get_user_actions(self, telegram_id: int, limit: int = 100) -> List[Dict]:
        """Получить последние действия пользователя."""
        pass
    
    @abstractmethod
    async def get_playlist_actions(self, playlist_id: int, limit: int = 100) -> List[Dict]:
        """Получить последние действия с плейлистом."""
        pass
    
    # === Работа с подписками и лимитами ===
    
    @abstractmethod
    async def get_user_playlist_limit(self, telegram_id: int) -> int:
        """Получить текущий лимит плейлистов для пользователя.
        
        Возвращает:
            - Базовый лимит (PLAYLIST_LIMIT), если нет активной подписки
            - Лимит из активной подписки, если есть
            - -1 для unlimited
        """
        pass
    
    @abstractmethod
    async def create_subscription(self, telegram_id: int, subscription_type: str, 
                           stars_amount: int, expires_at: Optional['datetime'] = None) -> int:
        """Создать подписку для пользователя.
        
        Args:
            telegram_id: ID пользователя Telegram
            subscription_type: Тип подписки (например, 'playlist_limit_5')
            stars_amount: Количество Stars, заплаченных за подписку
            expires_at: Дата истечения подписки (None для бессрочных)
        
        Returns:
            ID созданной подписки
        """
        pass
    
    @abstractmethod
    async def get_active_subscription(self, telegram_id: int) -> Optional[Dict]:
        """Получить активную подписку пользователя.
        
        Returns:
            Словарь с данными подписки или None, если нет активной подписки
        """
        pass
    
    # === Работа с платежами ===
    
    @abstractmethod
    async def create_payment(self, telegram_id: int, invoice_payload: str, 
                      stars_amount: int, subscription_type: str) -> int:
        """Создать запись о платеже.
        
        Args:
            telegram_id: ID пользователя Telegram
            invoice_payload: Уникальный идентификатор платежа
            stars_amount: Количество Stars
            subscription_type: Тип подписки
        
        Returns:
            ID созданного платежа
        """
        pass
    
    @abstractmethod
    async def update_payment_status(self, invoice_payload: str, status: str):
        """Обновить статус платежа.
        
        Args:
            invoice_payload: Уникальный идентификатор платежа
            status: Новый статус ('pending', 'completed', 'failed')
        """
        pass
    
    @abstractmethod
    async def get_payment_by_payload(self, invoice_payload: str) -> Optional[Dict]:
        """Получить платеж по payload.
        
        Args:
            invoice_payload: Уникальный идентификатор платежа
        
        Returns:
            Словарь с данными платежа или None, если не найден
        """
        pass

