"""
Сервис для работы с API Яндекс.Музыки.
Предоставляет высокоуровневые методы для получения треков, альбомов и плейлистов.
"""
import io
import json
import logging
import urllib.parse
import requests
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
    
    def set_playlist_name(
        self,
        playlist_kind: str,
        owner_id: str,
        new_name: str,
        max_retries: int = 2
    ) -> Tuple[bool, Optional[str]]:
        """
        Изменить название плейлиста через API Яндекс.Музыки.
        
        Args:
            playlist_kind: ID плейлиста (kind)
            owner_id: ID владельца плейлиста
            new_name: Новое название плейлиста
            max_retries: Максимальное количество попыток при ошибке
            
        Returns:
            Кортеж (успех, сообщение об ошибке)
        """
        for attempt in range(max_retries):
            try:
                # Кодируем название для URL
                encoded_name = urllib.parse.quote(new_name, safe='')
                
                # Формируем URL согласно примеру запроса
                url = f"{self.client.base_url}/users/{owner_id}/playlists/{playlist_kind}/name?value={encoded_name}"
                
                # Выполняем POST запрос с пустым телом
                result = self.client._request.post(url)
                
                if result:
                    return True, None
                else:
                    return False, "Запрос выполнен, но ответ пустой."
            except Exception as e:
                error_msg = str(e).lower()
                logger.debug(f"Попытка {attempt + 1}/{max_retries}: ошибка изменения имени плейлиста: {e}")
                
                # Если ошибка связана с revision и есть еще попытки, повторяем
                if ("wrong-revision" in error_msg or "revision" in error_msg) and attempt < max_retries - 1:
                    continue
                
                # Другая ошибка или все попытки исчерпаны
                return False, f"Ошибка изменения имени: {e}"
        
        return False, "Не удалось изменить имя плейлиста после нескольких попыток"
    
    def extract_track_info(self, track_item: Any) -> Tuple[Optional[Any], Optional[Any]]:
        """
        Извлечь track_id и album_id из объекта трека.
        
        Args:
            track_item: Объект трека (может быть Track или PlaylistTrack)
            
        Returns:
            Кортеж (track_id, album_id) или (None, None) если не удалось извлечь
        """
        # Получаем сам трек (может быть обернут в PlaylistTrack)
        t = track_item.track if hasattr(track_item, "track") and track_item.track else track_item
        
        # Извлекаем track_id
        tr_id = getattr(t, "id", None) or getattr(t, "track_id", None)
        
        # Извлекаем album_id
        alb = getattr(t, "albums", None)
        album_id = alb[0].id if alb and len(alb) > 0 else None
        
        if tr_id is None or album_id is None:
            return None, None
        
        return tr_id, album_id
    
    def format_track(self, track_item: Any) -> str:
        """
        Форматировать трек для отображения (название + артисты).
        
        Args:
            track_item: Объект трека (может быть Track или PlaylistTrack)
            
        Returns:
            Строка вида "Название — Артист1 / Артист2" или "Название"
        """
        # Получаем сам трек (может быть обернут в PlaylistTrack)
        t = track_item.track if hasattr(track_item, "track") and track_item.track else track_item
        
        track_title = getattr(t, "title", None) or "Unknown"
        artists = []
        if getattr(t, "artists", None):
            artists = [a.name for a in getattr(t, "artists", []) if getattr(a, "name", None)]
        
        artist_line = " / ".join(artists) if artists else ""
        if artist_line:
            return f"{track_title} — {artist_line}"
        return track_title
    
    def get_track_artists(self, track_item: Any) -> str:
        """
        Получить строку с артистами трека.
        
        Args:
            track_item: Объект трека (может быть Track или PlaylistTrack)
            
        Returns:
            Строка с артистами, разделенными запятыми
        """
        # Получаем сам трек (может быть обернут в PlaylistTrack)
        t = track_item.track if hasattr(track_item, "track") and track_item.track else track_item
        
        if getattr(t, "artists", None):
            artists = [a.name for a in getattr(t, "artists", []) if getattr(a, "name", None)]
            return ", ".join(artists) if artists else ""
        return ""
    
    def set_playlist_cover(
        self,
        playlist_kind: str,
        owner_id: str,
        image_file: Any,
        max_retries: int = 2
    ) -> Tuple[bool, Optional[str]]:
        """
        Установить обложку для плейлиста через API Яндекс.Музыки.
        
        Args:
            playlist_kind: ID плейлиста (kind)
            owner_id: ID владельца плейлиста
            image_file: Файл изображения (file-like object или bytes)
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
                
                # Подготавливаем файл для загрузки
                if hasattr(image_file, 'read'):
                    # Это file-like object
                    image_data = image_file.read()
                    image_file.seek(0)  # Возвращаем указатель в начало
                elif isinstance(image_file, (bytes, bytearray)):
                    # bytes или bytearray - конвертируем в bytes
                    image_data = bytes(image_file) if isinstance(image_file, bytearray) else image_file
                else:
                    return False, "Неверный формат файла изображения."
                
                # Пытаемся загрузить обложку через API
                # Используем прямой HTTP запрос, так как в библиотеке может не быть готового метода
                # URL должен быть /cover/upload, а не просто /cover
                url = f"{self.client.base_url}/users/{owner_id}/playlists/{playlist_kind}/cover/upload"
                
                # Формируем multipart/form-data запрос используя requests
                # Используем requests напрямую, так как _request может не поддерживать files
                headers = self.client._request.headers.copy()
                
                # Удаляем Content-Type из заголовков, чтобы requests сам установил правильный boundary
                headers.pop('Content-Type', None)
                
                # Формируем multipart/form-data с помощью request
                # revision не передается в запросе на /cover/upload
                # Используем io.BytesIO для создания file-like object из bytes
                image_file_obj = io.BytesIO(image_data)
                files = {
                    'image': ('cover.jpg', image_file_obj, 'image/jpeg')
                }
                
                logger.debug(f"Загружаем обложку на URL: {url}")
                logger.debug(f"Размер файла: {len(image_data)} байт")
                response = requests.post(url, files=files, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    logger.debug("Обложка успешно загружена")
                    return True, None
                else:
                    # Логируем полные детали ошибки для отладки
                    error_detail = response.text if response.text else "Нет деталей"
                    logger.debug(f"Ошибка загрузки обложки: статус {response.status_code}")
                    logger.debug(f"URL: {url}")
                    logger.debug(f"Заголовки запроса: {dict(headers)}")
                    logger.debug(f"Размер файла: {len(image_data)} байт")
                    logger.debug(f"Полный ответ от API: {error_detail}")
                    # Возвращаем сокращенную версию для пользователя
                    error_short = error_detail[:500] if len(error_detail) > 500 else error_detail
                    return False, f"Ошибка загрузки: статус {response.status_code}. {error_short}"
                    
            except Exception as e:
                error_msg = str(e).lower()
                logger.debug(f"Попытка {attempt + 1}/{max_retries}: ошибка установки обложки: {e}")
                
                # Если ошибка связана с revision и есть еще попытки, повторяем
                if ("wrong-revision" in error_msg or "revision" in error_msg) and attempt < max_retries - 1:
                    continue
                
                # Другая ошибка или все попытки исчерпаны
                return False, f"Ошибка установки обложки: {e}"
        
        return False, "Не удалось установить обложку после нескольких попыток"
    
    def get_playlist_cover_url(self, playlist_id: str, owner: Optional[str] = None, only_custom: bool = True) -> Optional[str]:
        """
        Получить URL обложки плейлиста.
        
        Args:
            playlist_id: ID плейлиста
            owner: ID владельца (опционально)
            only_custom: Если True, возвращать URL только для пользовательских обложек (custom=True)
            
        Returns:
            URL обложки или None, если обложка не найдена или не является пользовательской
        """
        pl_obj, err = self.get_playlist(playlist_id, owner)
        if pl_obj is None:
            return None
        
        # Пытаемся получить обложку из различных атрибутов
        cover = getattr(pl_obj, "cover", None)
        if cover:
            # Проверяем, является ли обложка пользовательской (custom)
            is_custom = getattr(cover, "custom", False)
            if only_custom and not is_custom:
                # Если нужна только пользовательская, а эта не пользовательская - возвращаем None
                return None
            
            # Обложка может быть объектом с различными размерами
            if hasattr(cover, "uri"):
                # Формируем полный URL
                uri = cover.uri
                if uri.startswith("//"):
                    return f"https:{uri}"
                elif uri.startswith("/"):
                    return f"https://music.yandex.ru{uri}"
                return uri
            elif hasattr(cover, "items") and cover.items:
                # Может быть список обложек (мозаика)
                # Для мозаики обычно custom = False, поэтому если only_custom = True, не возвращаем
                if only_custom:
                    return None
                first_item = cover.items[0]
                if hasattr(first_item, "uri"):
                    uri = first_item.uri
                    if uri.startswith("//"):
                        return f"https:{uri}"
                    elif uri.startswith("/"):
                        return f"https://music.yandex.ru{uri}"
                    return uri
        
        # Пробуем другие возможные атрибуты (og_image и т.д.)
        # Но только если не требуется только custom
        if not only_custom:
            for attr_name in ["cover_uri", "og_image", "image"]:
                attr = getattr(pl_obj, attr_name, None)
                if attr:
                    if isinstance(attr, str):
                        if attr.startswith("//"):
                            return f"https:{attr}"
                        elif attr.startswith("/"):
                            return f"https://music.yandex.ru{attr}"
                        return attr
        
        return None
    
    def get_playlist_info_for_sync(self, playlist_id: str, owner: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Получить информацию о плейлисте для синхронизации с БД.
        
        Args:
            playlist_id: ID плейлиста
            owner: ID владельца (опционально)
            
        Returns:
            Кортеж (title, cover_url, None) или (None, None, error_message)
            cover_url будет None, если обложка не является пользовательской (custom=False)
        """
        pl_obj, err = self.get_playlist(playlist_id, owner)
        if pl_obj is None:
            return None, None, err or "Не удалось получить плейлист"
        
        # Получаем название
        title = getattr(pl_obj, "title", None)
        
        # Получаем URL обложки (только для пользовательских)
        cover_url = self.get_playlist_cover_url(playlist_id, owner, only_custom=True)
        
        return title, cover_url, None

