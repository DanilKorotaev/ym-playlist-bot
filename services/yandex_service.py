"""
Сервис для работы с API Яндекс.Музыки.
Предоставляет высокоуровневые методы для получения треков, альбомов и плейлистов.
"""
import logging
from typing import List, Optional, Tuple, Any
from yandex_music import Client
from yandex_music.exceptions import YandexMusicError

logger = logging.getLogger(__name__)


class YandexService:
    """Сервис для работы с API Яндекс.Музыки."""
    
    def __init__(self, client: Client):
        """
        Инициализация сервиса.
        
        Args:
            client: Клиент Яндекс.Музыки
        """
        self.client = client
    
    def get_track(self, track_id: Any) -> Optional[Any]:
        """
        Получить трек по ID.
        
        Args:
            track_id: ID трека (int или str)
            
        Returns:
            Объект трека или None при ошибке
        """
        try:
            tracks = self.client.tracks(track_id)
            if tracks and len(tracks) > 0:
                return tracks[0]
            return None
        except YandexMusicError as e:
            logger.exception(f"Ошибка при получении трека {track_id}: {e}")
            return None
    
    def get_album_tracks(self, album_id: Any) -> List[Any]:
        """
        Получить список треков из альбома.
        
        Args:
            album_id: ID альбома (int или str)
            
        Returns:
            Список треков (может быть пустым)
        """
        try:
            # Пробуем разные методы получения альбома
            if hasattr(self.client, "albums_with_tracks"):
                alb = self.client.albums_with_tracks(album_id)
            else:
                if hasattr(self.client, "albums"):
                    maybe = self.client.albums([album_id])
                    alb = maybe[0] if isinstance(maybe, list) and maybe else maybe
                else:
                    alb = self.client.album(album_id)
            
            if alb is None:
                return []
            
            # Извлекаем треки из альбома
            if hasattr(alb, "tracks") and alb.tracks:
                return alb.tracks
            
            # Пробуем volumes
            vols = getattr(alb, "volumes", None)
            if vols:
                tracks = []
                for vol in vols:
                    tracks.extend(vol)
                return tracks
            
            # Пробуем другие атрибуты
            for attr in ["tracklist", "items", "results"]:
                maybe = getattr(alb, attr, None)
                if maybe and isinstance(maybe, list):
                    return maybe
                    
        except YandexMusicError as e:
            logger.exception(f"Ошибка при получении альбома {album_id}: {e}")
        
        return []
    
    def get_playlist(self, playlist_id: str, owner: Optional[str] = None) -> Tuple[Optional[Any], Optional[str]]:
        """
        Получить плейлист по ID и владельцу.
        
        Args:
            playlist_id: ID плейлиста
            owner: ID владельца (опционально)
            
        Returns:
            Кортеж (объект плейлиста, сообщение об ошибке)
        """
        if owner:
            try:
                pl = self.client.users_playlists(playlist_id, owner)
                return pl, None
            except Exception as e:
                logger.debug(f"users_playlists(pid,owner) failed: {e}")
        
        try:
            pl = self.client.users_playlists(playlist_id)
            return pl, None
        except Exception as e:
            logger.debug(f"users_playlists(pid) failed: {e}")
            return None, f"Не удалось получить плейлист {playlist_id}"
    
    def get_playlist_tracks(self, playlist_id: str, owner: Optional[str] = None) -> List[Any]:
        """
        Получить список треков из плейлиста.
        
        Args:
            playlist_id: ID плейлиста
            owner: ID владельца (опционально)
            
        Returns:
            Список треков (может быть пустым)
        """
        pl_obj, err = self.get_playlist(playlist_id, owner)
        if pl_obj is None:
            return []
        
        tracks = getattr(pl_obj, "tracks", []) or []
        return tracks

