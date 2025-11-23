"""
Сервис для работы с плейлистами.
Содержит бизнес-логику добавления и удаления треков из плейлистов.
"""
import json
import logging
import urllib.parse
from typing import Tuple, Optional, Any, Dict
from yandex_music import Client

from database import DatabaseInterface
from yandex_client_manager import YandexClientManager

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
        
        client = self.client_manager.get_client_for_playlist(playlist_id)
        last_err = None
        
        for attempt in range(2):
            try:
                pl = client.users_playlists(playlist["playlist_kind"], playlist["owner_id"])
                if pl is None:
                    return False, "Не удалось получить плейлист."
                revision = getattr(pl, "revision", 1)
                client.users_playlists_insert_track(
                    playlist["playlist_kind"], track_id, album_id, 
                    at=0, revision=revision, user_id=playlist["owner_id"]
                )
                # Логируем действие
                self.db.log_action(telegram_id, "track_added", playlist_id, f"track_id={track_id}")
                return True, None
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                logger.debug(f"insert attempt failed: {e}")
                if "wrong-revision" in msg or "revision" in msg:
                    continue
        return False, f"Ошибка вставки: {last_err}"
    
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
        
        client = self.client_manager.get_client_for_playlist(playlist_id)
        last_err = None
        
        for attempt in range(2):
            try:
                pl = client.users_playlists(playlist["playlist_kind"], playlist["owner_id"])
                if pl is None:
                    return False, "Не удалось получить плейлист."
                revision = getattr(pl, "revision", 1)
                diff = [{"op": "delete", "from": from_idx, "to": to_idx}]
                diff_str = json.dumps(diff, ensure_ascii=False).replace(" ", "")
                diff_encoded = urllib.parse.quote(diff_str, safe="")
                url = f"{client.base_url}/users/{playlist['owner_id']}/playlists/{playlist['playlist_kind']}/change-relative?diff={diff_encoded}&revision={revision}"
                result = client._request.post(url)
                # Логируем действие
                self.db.log_action(telegram_id, "track_deleted", playlist_id, f"from={from_idx}, to={to_idx}")
                return True, "Трек успешно удалён." if result else "Запрос выполнен, но ответ пустой."
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                logger.debug(f"delete attempt failed: {e}")
                if "wrong-revision" in msg or "revision" in msg:
                    continue
        return False, f"Ошибка удаления: {last_err}"
    
    def get_playlist_object(self, playlist_id: int, telegram_id: int) -> Optional[Any]:
        """
        Получить объект плейлиста из Яндекс.Музыки.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram
            
        Returns:
            Объект плейлиста или None
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return None
        
        client = self.client_manager.get_client_for_playlist(playlist_id)
        try:
            pl = client.users_playlists(playlist["playlist_kind"], playlist["owner_id"])
            return pl
        except Exception as e:
            logger.exception(f"Ошибка получения плейлиста {playlist_id}: {e}")
            return None

