"""
Сервис для работы с API Яндекс.Музыки.
Предоставляет высокоуровневые методы для получения треков, альбомов и плейлистов.
"""
import json
import logging
import urllib.parse
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
    
    def insert_track_to_playlist(
        self,
        playlist_kind: str,
        track_id: Any,
        album_id: Any,
        owner_id: str,
        at: int = 0,
        max_retries: int = 2
    ) -> Tuple[bool, Optional[str]]:
        """
        Добавить трек в плейлист через API Яндекс.Музыки.
        Автоматически получает актуальную revision и делает повторные попытки при ошибках.
        
        Args:
            playlist_kind: ID плейлиста (kind)
            track_id: ID трека
            album_id: ID альбома
            owner_id: ID владельца плейлиста
            at: Позиция для вставки (по умолчанию 0 - в начало)
            max_retries: Максимальное количество попыток при ошибке revision
            
        Returns:
            Кортеж (успех, сообщение об ошибке)
        """
        for attempt in range(max_retries):
            try:
                # Получаем плейлист с актуальной revision
                pl = self.client.users_playlists(playlist_kind, owner_id)
                if pl is None:
                    return False, "Не удалось получить плейлист."
                
                revision = getattr(pl, "revision", 1)
                
                # Пытаемся добавить трек
                self.client.users_playlists_insert_track(
                    playlist_kind, track_id, album_id,
                    at=at, revision=revision, user_id=owner_id
                )
                return True, None
            except Exception as e:
                error_msg = str(e).lower()
                logger.debug(f"Попытка {attempt + 1}/{max_retries}: ошибка вставки трека: {e}")
                
                # Если ошибка связана с revision и есть еще попытки, повторяем
                if ("wrong-revision" in error_msg or "revision" in error_msg) and attempt < max_retries - 1:
                    continue
                
                # Другая ошибка или все попытки исчерпаны
                return False, f"Ошибка вставки: {e}"
        
        return False, "Не удалось добавить трек после нескольких попыток"
    
    def delete_track_from_playlist(
        self,
        playlist_kind: str,
        owner_id: str,
        from_idx: int,
        to_idx: int,
        max_retries: int = 2
    ) -> Tuple[bool, Optional[str]]:
        """
        Удалить трек из плейлиста через API Яндекс.Музыки.
        Автоматически получает актуальную revision и делает повторные попытки при ошибках.
        
        Args:
            playlist_kind: ID плейлиста (kind)
            owner_id: ID владельца плейлиста
            from_idx: Начальный индекс (0-based)
            to_idx: Конечный индекс (0-based)
            max_retries: Максимальное количество попыток при ошибке revision
            
        Returns:
            Кортеж (успех, сообщение об ошибке)
        """
        for attempt in range(max_retries):
            try:
                # Получаем плейлист с актуальной revision
                pl = self.client.users_playlists(playlist_kind, owner_id)
                if pl is None:
                    return False, "Не удалось получить плейлист."
                
                revision = getattr(pl, "revision", 1)
                
                # Формируем diff для удаления
                diff = [{"op": "delete", "from": from_idx, "to": to_idx}]
                diff_str = json.dumps(diff, ensure_ascii=False).replace(" ", "")
                diff_encoded = urllib.parse.quote(diff_str, safe="")
                url = f"{self.client.base_url}/users/{owner_id}/playlists/{playlist_kind}/change-relative?diff={diff_encoded}&revision={revision}"
                result = self.client._request.post(url)
                
                if result:
                    return True, None
                else:
                    return False, "Запрос выполнен, но ответ пустой."
            except Exception as e:
                error_msg = str(e).lower()
                logger.debug(f"Попытка {attempt + 1}/{max_retries}: ошибка удаления трека: {e}")
                
                # Если ошибка связана с revision и есть еще попытки, повторяем
                if ("wrong-revision" in error_msg or "revision" in error_msg) and attempt < max_retries - 1:
                    continue
                
                # Другая ошибка или все попытки исчерпаны
                return False, f"Ошибка удаления: {e}"
        
        return False, "Не удалось удалить трек после нескольких попыток"

