"""
Сервис для работы с плейлистами.
Содержит бизнес-логику добавления и удаления треков из плейлистов.
"""
import logging
from typing import Tuple, Optional, Any, List

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
    
    def get_playlist_tracks(self, playlist_id: int, telegram_id: int) -> Optional[List[Any]]:
        """
        Получить список треков из плейлиста.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            
        Returns:
            Список треков или None, если плейлист не найден
        """
        pl_obj = self.get_playlist_object(playlist_id, telegram_id)
        if pl_obj is None:
            return None
        
        tracks = getattr(pl_obj, "tracks", []) or []
        return tracks
    
    def get_playlist_tracks_count(self, playlist_id: int, telegram_id: int) -> Optional[int]:
        """
        Получить количество треков в плейлисте.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            
        Returns:
            Количество треков или None, если плейлист не найден
        """
        tracks = self.get_playlist_tracks(playlist_id, telegram_id)
        if tracks is None:
            return None
        return len(tracks)
    
    def get_share_link(self, playlist_id: int, bot_username: str) -> Optional[str]:
        """
        Получить ссылку для шаринга плейлиста.
        
        Args:
            playlist_id: ID плейлиста в БД
            bot_username: Имя бота в Telegram
            
        Returns:
            Ссылка для шаринга или None, если токен не найден
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return None
        
        share_token = playlist.get("share_token")
        if not share_token:
            return None
        
        return f"https://t.me/{bot_username}?start={share_token}"
    
    def get_yandex_link(self, playlist_id: int) -> Optional[str]:
        """
        Получить ссылку на плейлист в Яндекс.Музыке.
        
        Args:
            playlist_id: ID плейлиста в БД
            
        Returns:
            Ссылка на плейлист в Яндекс.Музыке или None
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return None
        
        owner_id = playlist.get("owner_id")
        playlist_kind = playlist.get("playlist_kind")
        
        if not owner_id or not playlist_kind:
            return None
        
        return f"https://music.yandex.ru/users/{owner_id}/playlists/{playlist_kind}"
    
    def set_playlist_cover(
        self,
        playlist_id: int,
        image_file: Any,
        telegram_id: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Установить обложку для плейлиста.
        
        Args:
            playlist_id: ID плейлиста в БД
            image_file: Файл изображения (file-like object или bytes)
            telegram_id: ID пользователя Telegram
            
        Returns:
            Кортеж (успех, сообщение об ошибке)
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return False, "Плейлист не найден."
        
        # Проверяем права доступа (только создатель может менять обложку)
        if not self.db.is_playlist_creator(playlist_id, telegram_id):
            return False, "Только создатель плейлиста может изменять обложку."
        
        # Получаем клиент и создаем сервис для работы с API
        client = self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Вызываем метод API
        ok, error = yandex_service.set_playlist_cover(
            playlist_kind, owner_id, image_file
        )
        
        if ok:
            # Логируем действие
            self.db.log_action(telegram_id, "playlist_cover_set", playlist_id, None)
            return True, None
        
        return False, error or "Ошибка установки обложки"
    
    def edit_playlist_name(
        self,
        playlist_id: int,
        new_name: str,
        telegram_id: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Изменить название плейлиста в Яндекс.Музыке и обновить в БД.
        
        Args:
            playlist_id: ID плейлиста в БД
            new_name: Новое название плейлиста
            telegram_id: ID пользователя Telegram
            
        Returns:
            Кортеж (успех, сообщение об ошибке)
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return False, "Плейлист не найден."
        
        # Проверяем права доступа (только создатель может менять имя)
        if not self.db.is_playlist_creator(playlist_id, telegram_id):
            return False, "Только создатель плейлиста может изменять его название."
        
        # Получаем клиент и создаем сервис для работы с API
        client = self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Вызываем метод API для изменения имени в Яндекс.Музыке
        ok, error = yandex_service.set_playlist_name(
            playlist_kind, owner_id, new_name
        )
        
        if ok:
            # Обновляем название в БД
            self.db.update_playlist(playlist_id, title=new_name)
            # Логируем действие
            self.db.log_action(telegram_id, "playlist_name_edited", playlist_id, f"new_title={new_name}")
            return True, None
        
        return False, error or "Ошибка изменения имени плейлиста"
    
    def get_playlist_cover_url(self, playlist_id: int, telegram_id: int) -> Optional[str]:
        """
        Получить URL обложки плейлиста из БД или API.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            
        Returns:
            URL обложки или None, если обложка не найдена
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return None
        
        # Сначала проверяем, есть ли сохраненный URL в БД
        cover_url = playlist.get("cover_url")
        if cover_url:
            return cover_url
        
        # Если нет в БД, получаем из API
        client = self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Используем метод из YandexService (только пользовательские обложки)
        return yandex_service.get_playlist_cover_url(playlist_kind, owner_id, only_custom=True)
    
    def sync_playlist_from_api(self, playlist_id: int, telegram_id: int) -> Tuple[bool, Optional[str]]:
        """
        Синхронизировать данные плейлиста из API Яндекс.Музыки с БД.
        Обновляет название и URL обложки (только для пользовательских обложек).
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            
        Returns:
            Кортеж (успех, сообщение об ошибке)
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return False, "Плейлист не найден в БД"
        
        # Получаем клиент и создаем сервис для работы с API
        client = self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Получаем актуальные данные из API
        title, cover_url, error = yandex_service.get_playlist_info_for_sync(playlist_kind, owner_id)
        
        if error:
            return False, error
        
        # Обновляем данные в БД
        updates = {}
        if title and title != playlist.get("title"):
            updates["title"] = title
        if cover_url != playlist.get("cover_url"):
            # Обновляем cover_url (может быть None, если обложка не пользовательская)
            updates["cover_url"] = cover_url
        
        if updates:
            self.db.update_playlist(playlist_id, **updates)
            logger.debug(f"Синхронизированы данные плейлиста {playlist_id}: {updates}")
        
        return True, None

