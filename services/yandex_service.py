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
from yandex_music.exceptions import YandexMusicError, TimedOutError

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
        insert_position: str = 'end',
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
            insert_position: 'start' для добавления в начало, 'end' для добавления в конец (по умолчанию 'end')
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
                
                # Рассчитываем позицию для вставки
                if insert_position == 'start':
                    at = 0
                else:  # 'end'
                    # Получаем текущее количество треков в плейлисте
                    tracks = getattr(pl, "tracks", []) or []
                    at = len(tracks)
                
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
        Проверяет количество треков до и после удаления для валидации успешности операции.
        
        Args:
            playlist_kind: ID плейлиста (kind)
            owner_id: ID владельца плейлиста
            from_idx: Начальный индекс (0-based, включительный)
            to_idx: Конечный индекс (0-based, включительный)
            max_retries: Максимальное количество попыток при ошибке revision
            
        Returns:
            Кортеж (успех, сообщение об ошибке)
            
        Note:
            API использует 'to' как исключительный индекс (exclusive), поэтому при формировании
            запроса to_idx увеличивается на 1. Например, для удаления трека с индексом 7
            отправляется from:7, to:8.
        """
        for attempt in range(max_retries):
            try:
                # Получаем плейлист с актуальной revision
                pl = self.client.users_playlists(playlist_kind, owner_id)
                if pl is None:
                    return False, "Не удалось получить плейлист."
                
                # Получаем треки до удаления
                tracks_before = getattr(pl, "tracks", []) or []
                tracks_count_before = len(tracks_before)
                
                # Валидация индексов
                if from_idx < 0 or to_idx < 0:
                    return False, f"Неверные индексы: from_idx={from_idx}, to_idx={to_idx}"
                
                if from_idx >= tracks_count_before or to_idx >= tracks_count_before:
                    return False, f"Индексы выходят за границы плейлиста (треков: {tracks_count_before}, индексы: {from_idx}-{to_idx})"
                
                if from_idx > to_idx:
                    return False, f"Неверный диапазон: from_idx ({from_idx}) > to_idx ({to_idx})"
                
                # Вычисляем ожидаемое количество треков после удаления
                # to_idx - включительный индекс (inclusive), поэтому +1 для подсчета
                expected_deleted_count = to_idx - from_idx + 1
                expected_tracks_count_after = tracks_count_before - expected_deleted_count
                
                revision = getattr(pl, "revision", 1)
                
                # API использует 'to' как исключительный индекс (exclusive), поэтому увеличиваем на 1
                # Например, для удаления трека с индексом 7 нужно from:7, to:8
                api_to_idx = to_idx + 1
                
                logger.debug(
                    f"Удаление треков из плейлиста {playlist_kind}: "
                    f"индексы {from_idx}-{to_idx} (включительно), API to: {api_to_idx} (исключительно), "
                    f"треков до: {tracks_count_before}, ожидается после: {expected_tracks_count_after}, revision: {revision}"
                )
                
                # Формируем diff для удаления
                # API использует 'to' как исключительный индекс (exclusive end)
                diff = [{"op": "delete", "from": from_idx, "to": api_to_idx}]
                diff_str = json.dumps(diff, ensure_ascii=False).replace(" ", "")
                diff_encoded = urllib.parse.quote(diff_str, safe="")
                url = f"{self.client.base_url}/users/{owner_id}/playlists/{playlist_kind}/change-relative?diff={diff_encoded}&revision={revision}"
                
                # Копируем заголовки из клиента и добавляем необходимые
                headers = self.client._request.headers.copy()
                # Добавляем заголовок, который требуется API (как в curl запросе)
                headers['x-yandex-music-without-invocation-info'] = '1'
                
                logger.debug(f"Запрос на удаление трека: URL={url}")
                logger.debug(f"Diff (декодированный): {diff_str}")
                logger.debug(f"Заголовки: {dict(headers)}")
                
                # Выполняем запрос на удаление через requests напрямую
                # (как в set_playlist_cover) для контроля заголовков
                try:
                    response = requests.post(url, headers=headers, timeout=30)
                    
                    # Проверяем статус код ответа
                    if response.status_code != 200:
                        error_detail = response.text if response.text else "Нет деталей"
                        logger.warning(
                            f"Ошибка при удалении трека: статус {response.status_code}, "
                            f"ответ: {error_detail[:200]}"
                        )
                        
                        error_msg = error_detail.lower()
                        # Если ошибка связана с revision и есть еще попытки, повторяем
                        if ("wrong-revision" in error_msg or "revision" in error_msg) and attempt < max_retries - 1:
                            logger.debug(f"Ошибка revision, повторяем попытку {attempt + 2}/{max_retries}")
                            continue
                        
                        return False, f"Ошибка API: статус {response.status_code}. {error_detail[:200]}"
                    
                    # Запрос успешен (статус 200)
                    logger.debug(f"Запрос на удаление выполнен успешно (статус {response.status_code})")
                    
                except requests.exceptions.RequestException as request_error:
                    # Если запрос упал с исключением, это явная ошибка
                    error_msg = str(request_error).lower()
                    logger.warning(f"Ошибка при выполнении запроса удаления: {request_error}")
                    
                    # Если ошибка связана с revision и есть еще попытки, повторяем
                    if ("wrong-revision" in error_msg or "revision" in error_msg) and attempt < max_retries - 1:
                        logger.debug(f"Ошибка revision, повторяем попытку {attempt + 2}/{max_retries}")
                        continue
                    
                    return False, f"Ошибка при выполнении запроса: {request_error}"
                except Exception as request_error:
                    # Другие исключения
                    error_msg = str(request_error).lower()
                    logger.warning(f"Неожиданная ошибка при выполнении запроса удаления: {request_error}")
                    
                    if ("wrong-revision" in error_msg or "revision" in error_msg) and attempt < max_retries - 1:
                        logger.debug(f"Ошибка revision, повторяем попытку {attempt + 2}/{max_retries}")
                        continue
                    
                    return False, f"Ошибка при выполнении запроса: {request_error}"
                
                # Получаем плейлист после удаления для проверки
                # Небольшая задержка, чтобы API успел обработать изменения
                import time
                time.sleep(0.5)
                
                pl_after = self.client.users_playlists(playlist_kind, owner_id)
                if pl_after is None:
                    logger.warning("Не удалось получить плейлист после удаления для проверки")
                    # Если не удалось получить плейлист, но запрос выполнен, считаем успешным
                    # (возможно, это временная проблема с получением данных)
                    return True, None
                
                tracks_after = getattr(pl_after, "tracks", []) or []
                tracks_count_after = len(tracks_after)
                
                logger.debug(
                    f"Проверка удаления: треков до: {tracks_count_before}, "
                    f"после: {tracks_count_after}, ожидалось: {expected_tracks_count_after}"
                )
                
                # Проверяем, что количество треков изменилось как ожидалось
                if tracks_count_after == tracks_count_before:
                    # Количество не изменилось - удаление не сработало
                    logger.warning(
                        f"Удаление не сработало: количество треков не изменилось "
                        f"({tracks_count_before} -> {tracks_count_after})"
                    )
                    if attempt < max_retries - 1:
                        logger.debug(f"Повторяем попытку {attempt + 2}/{max_retries}")
                        continue
                    return False, (
                        f"Удаление не выполнено: количество треков не изменилось "
                        f"({tracks_count_before} треков до и после удаления). "
                        f"Возможно, проблема с правами доступа или состоянием плейлиста."
                    )
                
                # Проверяем, что количество изменилось хотя бы на 1 (может быть удалено меньше, чем ожидалось)
                if tracks_count_after >= tracks_count_before:
                    logger.warning(
                        f"Количество треков не уменьшилось: "
                        f"{tracks_count_before} -> {tracks_count_after}"
                    )
                    if attempt < max_retries - 1:
                        continue
                    return False, (
                        f"Удаление не выполнено: количество треков не уменьшилось "
                        f"({tracks_count_before} -> {tracks_count_after})"
                    )
                
                # Удаление успешно - количество треков уменьшилось
                actual_deleted_count = tracks_count_before - tracks_count_after
                if actual_deleted_count != expected_deleted_count:
                    logger.info(
                        f"Удалено {actual_deleted_count} треков вместо ожидаемых {expected_deleted_count}. "
                        f"Возможно, часть треков уже была удалена."
                    )
                
                logger.debug(f"Успешно удалено {actual_deleted_count} треков из плейлиста")
                return True, None
                
            except Exception as e:
                error_msg = str(e).lower()
                logger.exception(f"Попытка {attempt + 1}/{max_retries}: ошибка удаления трека: {e}")
                
                # Если ошибка связана с revision и есть еще попытки, повторяем
                if ("wrong-revision" in error_msg or "revision" in error_msg) and attempt < max_retries - 1:
                    logger.debug(f"Ошибка revision, повторяем попытку {attempt + 2}/{max_retries}")
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
            Tuple[bool, Optional[str]]: (успех, понятное сообщение об ошибке)
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
            except YandexMusicError as e:
                error_message = str(e).lower()
                error_str = str(e)
                logger.debug(f"Попытка {attempt + 1}/{max_retries}: ошибка изменения имени плейлиста: {e}")
                
                # Если ошибка связана с revision и есть еще попытки, повторяем
                if ("wrong-revision" in error_message or "revision" in error_message) and attempt < max_retries - 1:
                    continue
                
                # Проверяем на ошибки модерации
                if any(keyword in error_message for keyword in ["moderation", "модерац", "name", "title", "invalid", "некорректн"]):
                    logger.warning(
                        f"Ошибка модерации названия плейлиста: title='{new_name}', "
                        f"playlist_kind={playlist_kind}, owner_id={owner_id}, error={error_str}"
                    )
                    return False, "Название плейлиста не прошло модерацию. Пожалуйста, используйте другое название."
                
                # Проверяем на ошибки авторизации (401)
                if "unauthorized" in error_message or "401" in error_str or "недействителен" in error_message:
                    logger.warning(f"Ошибка авторизации при изменении названия: playlist_kind={playlist_kind}, error={error_str}")
                    return False, "Токен Яндекс.Музыки недействителен. Используйте /set_token для обновления."
                
                # Проверяем на ошибки доступа (403)
                if "forbidden" in error_message or "403" in error_str or "недостаточно прав" in error_message:
                    logger.warning(f"Ошибка доступа при изменении названия: playlist_kind={playlist_kind}, error={error_str}")
                    return False, "Недостаточно прав для изменения названия или название не прошло модерацию."
                
                # Проверяем на ошибки некорректного запроса (400)
                if "bad request" in error_message or "400" in error_str:
                    logger.warning(f"Некорректный запрос при изменении названия: playlist_kind={playlist_kind}, error={error_str}")
                    return False, "Некорректное название плейлиста."
                
                # Другие ошибки API
                logger.error(f"Ошибка API при изменении названия: playlist_kind={playlist_kind}, error={error_str}")
                return False, "Ошибка при изменении названия плейлиста. Попробуйте еще раз."
            except TimedOutError as e:
                logger.warning(f"Таймаут при изменении названия плейлиста: {e}")
                if attempt < max_retries - 1:
                    continue
                return False, "Превышено время ожидания ответа. Попробуйте еще раз."
            except (ConnectionError, OSError) as e:
                logger.warning(f"Сетевая ошибка при изменении названия: {e}")
                if attempt < max_retries - 1:
                    continue
                return False, "Проблема с подключением к Яндекс.Музыке. Попробуйте позже."
            except Exception as e:
                error_msg = str(e).lower()
                logger.debug(f"Попытка {attempt + 1}/{max_retries}: ошибка изменения имени плейлиста: {e}")
                
                # Если ошибка связана с revision и есть еще попытки, повторяем
                if ("wrong-revision" in error_msg or "revision" in error_msg) and attempt < max_retries - 1:
                    continue
                
                # Другая ошибка или все попытки исчерпаны
                logger.exception(f"Неожиданная ошибка при изменении названия: {e}")
                return False, "Ошибка при изменении названия плейлиста. Попробуйте еще раз."
        
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
        logger.debug(f"Получение URL обложки для плейлиста {playlist_id}, owner={owner}, only_custom={only_custom}")
        pl_obj, err = self.get_playlist(playlist_id, owner)
        if pl_obj is None:
            logger.debug(f"Плейлист {playlist_id} не найден: {err}")
            return None
        
        # Пытаемся получить обложку из различных атрибутов
        cover = getattr(pl_obj, "cover", None)
        logger.debug(f"Атрибут cover для плейлиста {playlist_id}: {cover is not None}")
        if cover:
            # Проверяем, является ли обложка пользовательской (custom)
            is_custom = getattr(cover, "custom", False)
            logger.debug(f"Обложка custom для плейлиста {playlist_id}: {is_custom}, only_custom={only_custom}")
            if only_custom and not is_custom:
                # Если нужна только пользовательская, а эта не пользовательская - возвращаем None
                logger.debug(f"Пропускаем обложку (не custom, а требуется only_custom=True)")
                return None
            
            # Обложка может быть объектом с различными размерами
            logger.debug(f"Проверка cover.uri для плейлиста {playlist_id}: hasattr={hasattr(cover, 'uri')}")
            if hasattr(cover, "uri"):
                # Формируем полный URL
                uri = cover.uri
                logger.debug(f"cover.uri для плейлиста {playlist_id}: {uri}")
                if not uri:
                    logger.debug(f"cover.uri пустой для плейлиста {playlist_id}")
                    return None
                # Заменяем %% на конкретный размер (300x300 для Telegram)
                uri = uri.replace("%%", "300x300")
                logger.debug(f"Обработан URI обложки из cover.uri: {uri}")
                if uri.startswith("//"):
                    result = f"https:{uri}"
                    logger.debug(f"Возвращаем URL обложки (протокол-относительный): {result}")
                    return result
                elif uri.startswith("/"):
                    result = f"https://music.yandex.ru{uri}"
                    logger.debug(f"Возвращаем URL обложки (относительный путь): {result}")
                    return result
                elif uri.startswith("http://") or uri.startswith("https://"):
                    logger.debug(f"Возвращаем URL обложки (полный): {uri}")
                    return uri
                elif not uri.startswith("/") and "." in uri.split("/")[0]:  # Если начинается с домена (например, avatars.yandex.net)
                    result = f"https://{uri}"
                    logger.debug(f"Возвращаем URL обложки (домен без схемы): {result}")
                    return result
                logger.debug(f"Возвращаем URI обложки как есть: {uri}")
                return uri
            elif hasattr(cover, "items") and cover.items:
                # Может быть список обложек (мозаика)
                # Для мозаики обычно custom = False, поэтому если only_custom = True, не возвращаем
                logger.debug(f"Найдена мозаика обложек для плейлиста {playlist_id}, количество items: {len(cover.items) if cover.items else 0}")
                if only_custom:
                    logger.debug(f"Пропускаем мозаику (only_custom=True)")
                    return None
                first_item = cover.items[0]
                if hasattr(first_item, "uri"):
                    uri = first_item.uri
                    if not uri:
                        return None
                    # Заменяем %% на конкретный размер (300x300 для Telegram)
                    uri = uri.replace("%%", "300x300")
                    logger.debug(f"Обработан URI обложки из items: {uri}")
                    if uri.startswith("//"):
                        result = f"https:{uri}"
                        logger.debug(f"Возвращаем URL обложки (протокол-относительный): {result}")
                        return result
                    elif uri.startswith("/"):
                        result = f"https://music.yandex.ru{uri}"
                        logger.debug(f"Возвращаем URL обложки (относительный путь): {result}")
                        return result
                    elif uri.startswith("http://") or uri.startswith("https://"):
                        logger.debug(f"Возвращаем URL обложки (полный): {uri}")
                        return uri
                    elif not uri.startswith("/") and "." in uri.split("/")[0]:  # Если начинается с домена (например, avatars.yandex.net)
                        result = f"https://{uri}"
                        logger.debug(f"Возвращаем URL обложки (домен без схемы): {result}")
                        return result
                    logger.debug(f"Возвращаем URI обложки как есть: {uri}")
                    return uri
        else:
            logger.debug(f"Атрибут cover отсутствует или пустой для плейлиста {playlist_id}")
        
        # Пробуем другие возможные атрибуты (og_image и т.д.)
        # Но только если не требуется только custom
        logger.debug(f"Проверка других атрибутов для плейлиста {playlist_id}, only_custom={only_custom}")
        if not only_custom:
            for attr_name in ["cover_uri", "og_image", "image"]:
                attr = getattr(pl_obj, attr_name, None)
                logger.debug(f"Атрибут {attr_name} для плейлиста {playlist_id}: {attr is not None}, значение: {attr if isinstance(attr, str) else type(attr)}")
                if attr:
                    if isinstance(attr, str) and attr:
                        # Заменяем %% на конкретный размер (300x300 для Telegram)
                        attr = attr.replace("%%", "300x300")
                        logger.debug(f"Обработан атрибут {attr_name} обложки: {attr}")
                        if attr.startswith("//"):
                            return f"https:{attr}"
                        elif attr.startswith("/"):
                            return f"https://music.yandex.ru{attr}"
                        elif attr.startswith("http://") or attr.startswith("https://"):
                            return attr
                        elif not attr.startswith("/") and "." in attr.split("/")[0]:  # Если начинается с домена (например, avatars.yandex.net)
                            result = f"https://{attr}"
                            logger.debug(f"Возвращаем URL обложки из {attr_name} (домен без схемы): {result}")
                            return result
                        logger.debug(f"Возвращаем атрибут {attr_name} обложки как есть: {attr}")
                        return attr
        
        logger.debug(f"Обложка не найдена для плейлиста {playlist_id}")
        return None
    
    def download_playlist_cover(self, cover_url: str) -> Optional[bytes]:
        """
        Скачать обложку плейлиста по URL с авторизацией.
        
        Args:
            cover_url: URL обложки плейлиста
            
        Returns:
            Байты изображения или None при ошибке
        """
        try:
            logger.debug(f"Попытка скачать обложку по URL: {cover_url}")
            # Используем заголовки авторизации из клиента
            headers = self.client._request.headers.copy()
            
            # Скачиваем изображение
            response = requests.get(cover_url, headers=headers, timeout=10)
            
            logger.debug(f"Ответ при скачивании обложки: статус {response.status_code}, размер контента: {len(response.content) if response.content else 0} байт")
            
            if response.status_code == 200:
                logger.debug(f"Обложка успешно скачана, размер: {len(response.content)} байт")
                return response.content
            else:
                logger.warning(f"Ошибка скачивания обложки: статус {response.status_code}, ответ: {response.text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"Ошибка при скачивании обложки: {e}", exc_info=True)
            return None
    
    def get_playlist_info_for_sync(self, playlist_id: str, owner: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Получить информацию о плейлисте для синхронизации с БД.
        
        Args:
            playlist_id: ID плейлиста
            owner: ID владельца (опционально)
            
        Returns:
            Кортеж (title, cover_url, uuid, None) или (None, None, None, error_message)
            cover_url будет None, если обложка не является пользовательской (custom=False)
            uuid будет None, если UUID недоступен
        """
        pl_obj, err = self.get_playlist(playlist_id, owner)
        if pl_obj is None:
            return None, None, None, err or "Не удалось получить плейлист"
        
        # Получаем название
        title = getattr(pl_obj, "title", None)
        
        # Получаем URL обложки (только для пользовательских)
        cover_url = self.get_playlist_cover_url(playlist_id, owner, only_custom=True)
        
        # Получаем UUID плейлиста (может быть в разных атрибутах)
        playlist_uuid = getattr(pl_obj, "uuid", None) or getattr(pl_obj, "playlist_uuid", None)
        if playlist_uuid:
            playlist_uuid = str(playlist_uuid)
        
        return title, cover_url, playlist_uuid, None

