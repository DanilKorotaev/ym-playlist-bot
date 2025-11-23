"""
Сервис для работы с плейлистами.
Содержит бизнес-логику добавления и удаления треков из плейлистов.
"""
import logging
from typing import Tuple, Optional, Any

from database import DatabaseInterface
from yandex_client_manager import YandexClientManager
from .yandex_service import YandexService

logger = logging.getLogger(__name__)


class PlaylistService:
    """Сервис для работы с плейлистами."""
    
    def __init__(self, db: DatabaseInterface, client_manager: YandexClientManager):
        """
        Инициализация сервиса.
        
        Args:
            db: Интерфейс базы данных
            client_manager: Менеджер клиентов Яндекс.Музыки
        """
        self.db = db
        self.client_manager = client_manager
    
    def add_track(
        self, 
        playlist_id: int, 
        track_id: Any, 
        album_id: Any, 
        telegram_id: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Добавить трек в плейлист.
        
        Args:
            playlist_id: ID плейлиста в БД
            track_id: ID трека
            album_id: ID альбома
            telegram_id: ID пользователя Telegram
            
        Returns:
            Кортеж (успех, сообщение об ошибке)
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return False, "Плейлист не найден."
        
        # Проверяем права доступа
        if not self.db.check_playlist_access(playlist_id, telegram_id, need_add=True):
            return False, "У вас нет прав на добавление треков в этот плейлист."
        
        # Получаем клиент и создаем сервис для работы с API
        client = self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Вызываем метод API - он сам получит revision и сделает повторные попытки
        ok, error = yandex_service.insert_track_to_playlist(
            playlist_kind, track_id, album_id, owner_id
        )
        
        if ok:
            # Логируем действие
            self.db.log_action(telegram_id, "track_added", playlist_id, f"track_id={track_id}")
            return True, None
        
        return False, error or "Ошибка вставки трека"
    
    def delete_track(
        self, 
        playlist_id: int, 
        from_idx: int, 
        to_idx: int, 
        telegram_id: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Удалить трек из плейлиста.
        
        Args:
            playlist_id: ID плейлиста в БД
            from_idx: Начальный индекс (0-based)
            to_idx: Конечный индекс (0-based)
            telegram_id: ID пользователя Telegram
            
        Returns:
            Кортеж (успех, сообщение об ошибке)
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return False, "Плейлист не найден."
        
        # Проверяем права доступа
        if not self.db.check_playlist_access(playlist_id, telegram_id, need_edit=True):
            return False, "У вас нет прав на удаление треков из этого плейлиста."
        
        # Получаем клиент и создаем сервис для работы с API
        client = self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Вызываем метод API - он сам получит revision и сделает повторные попытки
        ok, error = yandex_service.delete_track_from_playlist(
            playlist_kind, owner_id, from_idx, to_idx
        )
        
        if ok:
            # Логируем действие
            self.db.log_action(telegram_id, "track_deleted", playlist_id, f"from={from_idx}, to={to_idx}")
            return True, "Трек успешно удалён."
        
        return False, error or "Ошибка удаления трека"
    
    def get_playlist_object(self, playlist_id: int, telegram_id: int) -> Optional[Any]:
        """
        Получить объект плейлиста из Яндекс.Музыки.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            
        Returns:
            Объект плейлиста или None
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return None
        
        # Получаем клиент и создаем сервис для работы с API
        client = self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Используем метод из YandexService
        pl_obj, err = yandex_service.get_playlist(playlist_kind, owner_id)
        if pl_obj is None:
            logger.debug(f"Ошибка получения плейлиста {playlist_id}: {err}")
            return None
        
        return pl_obj

