"""
Сервис для работы с плейлистами.
Содержит бизнес-логику добавления и удаления треков из плейлистов.
"""
import logging
import asyncio
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
    
    async def add_track(
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
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            return False, "Плейлист не найден."
        
        # Проверяем права доступа
        if not await self.db.check_playlist_access(playlist_id, telegram_id, need_add=True):
            return False, "У вас нет прав на добавление треков в этот плейлист."
        
        # Получаем клиент и создаем сервис для работы с API
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Получаем настройку insert_position из БД (по умолчанию 'end')
        insert_position = playlist.get("insert_position", "end")
        
        # Вызываем метод API - он сам получит revision и сделает повторные попытки
        # Обертываем синхронный вызов в thread
        ok, error = await asyncio.to_thread(
            yandex_service.insert_track_to_playlist,
            playlist_kind, track_id, album_id, owner_id, insert_position=insert_position
        )
        
        if ok:
            # Логируем действие
            await asyncio.to_thread(
                self.db.log_action, telegram_id, "track_added", playlist_id, 
                f"track_id={track_id}, position={insert_position}"
            )
            return True, None
        
        return False, error or "Ошибка вставки трека"
    
    async def delete_track(
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
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            return False, "Плейлист не найден."
        
        # Проверяем права доступа
        if not await self.db.check_playlist_access(playlist_id, telegram_id, need_edit=True):
            return False, "У вас нет прав на удаление треков из этого плейлиста."
        
        # Получаем клиент и создаем сервис для работы с API
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Вызываем метод API - он сам получит revision и сделает повторные попытки
        # Обертываем синхронный вызов в thread
        ok, error = await asyncio.to_thread(
            yandex_service.delete_track_from_playlist,
            playlist_kind, owner_id, from_idx, to_idx
        )
        
        if ok:
            # Логируем действие
            await asyncio.to_thread(
                self.db.log_action, telegram_id, "track_deleted", playlist_id, 
                f"from={from_idx}, to={to_idx}"
            )
            return True, "Трек успешно удалён."
        
        return False, error or "Ошибка удаления трека"
    
    async def get_playlist_object(self, playlist_id: int, telegram_id: int) -> Optional[Any]:
        """
        Получить объект плейлиста из Яндекс.Музыки.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            
        Returns:
            Объект плейлиста или None
        """
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            return None
        
        # Получаем клиент и создаем сервис для работы с API
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Используем метод из YandexService (обертываем синхронный вызов)
        pl_obj, err = await asyncio.to_thread(yandex_service.get_playlist, playlist_kind, owner_id)
        if pl_obj is None:
            logger.debug(f"Ошибка получения плейлиста {playlist_id}: {err}")
            return None
        
        return pl_obj
    
    async def get_playlist_tracks(self, playlist_id: int, telegram_id: int) -> Optional[List[Any]]:
        """
        Получить список треков из плейлиста.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            
        Returns:
            Список треков или None, если плейлист не найден
        """
        pl_obj = await self.get_playlist_object(playlist_id, telegram_id)
        if pl_obj is None:
            return None
        
        tracks = getattr(pl_obj, "tracks", []) or []
        return tracks
    
    async def get_playlist_tracks_count(self, playlist_id: int, telegram_id: int) -> Optional[int]:
        """
        Получить количество треков в плейлисте.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            
        Returns:
            Количество треков или None, если плейлист не найден
        """
        tracks = await self.get_playlist_tracks(playlist_id, telegram_id)
        if tracks is None:
            return None
        return len(tracks)
    
    async def get_share_link(self, playlist_id: int, bot_username: str) -> Optional[str]:
        """
        Получить ссылку для шаринга плейлиста.
        
        Args:
            playlist_id: ID плейлиста в БД
            bot_username: Имя бота в Telegram
            
        Returns:
            Ссылка для шаринга или None, если токен не найден
        """
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            return None
        
        share_token = playlist.get("share_token")
        if not share_token:
            return None
        
        return f"https://t.me/{bot_username}?start={share_token}"
    
    async def get_yandex_link(self, playlist_id: int) -> Optional[str]:
        """
        Получить ссылку на плейлист в Яндекс.Музыке.
        Использует короткий формат с UUID, если доступен, иначе старый формат.
        
        Args:
            playlist_id: ID плейлиста в БД
            
        Returns:
            Ссылка на плейлист в Яндекс.Музыке или None
        """
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            return None
        
        # Пробуем использовать UUID для короткой ссылки
        playlist_uuid = playlist.get("uuid")
        if playlist_uuid:
            return f"https://music.yandex.ru/playlists/{playlist_uuid}"
        
        # Fallback на старый формат, если UUID нет
        owner_id = playlist.get("owner_id")
        playlist_kind = playlist.get("playlist_kind")
        
        if not owner_id or not playlist_kind:
            return None
        
        return f"https://music.yandex.ru/users/{owner_id}/playlists/{playlist_kind}"
    
    async def set_playlist_cover(
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
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            return False, "Плейлист не найден."
        
        # Проверяем права доступа (только создатель может менять обложку)
        if not await self.db.is_playlist_creator(playlist_id, telegram_id):
            return False, "Только создатель плейлиста может изменять обложку."
        
        # Получаем клиент и создаем сервис для работы с API
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Вызываем метод API (обертываем синхронный вызов)
        ok, error = await asyncio.to_thread(
            yandex_service.set_playlist_cover,
            playlist_kind, owner_id, image_file
        )
        
        if ok:
            # Логируем действие
            await self.db.log_action(telegram_id, "playlist_cover_set", playlist_id, None)
            return True, None
        
        return False, error or "Ошибка установки обложки"
    
    async def edit_playlist_name(
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
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            return False, "Плейлист не найден."
        
        # Проверяем права доступа (только создатель может менять имя)
        if not await self.db.is_playlist_creator(playlist_id, telegram_id):
            return False, "Только создатель плейлиста может изменять его название."
        
        # Получаем клиент и создаем сервис для работы с API
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Вызываем метод API для изменения имени в Яндекс.Музыке (обертываем синхронный вызов)
        ok, error = await asyncio.to_thread(
            yandex_service.set_playlist_name,
            playlist_kind, owner_id, new_name
        )
        
        if ok:
            # Обновляем название в БД
            await self.db.update_playlist(playlist_id, title=new_name)
            # Логируем действие
            await self.db.log_action(
                telegram_id, "playlist_name_edited", playlist_id, 
                f"new_title={new_name}"
            )
            return True, None
        
        return False, error or "Ошибка изменения имени плейлиста"
    
    async def get_playlist_cover_url(self, playlist_id: int, telegram_id: int, only_custom: bool = True) -> Optional[str]:
        """
        Получить URL обложки плейлиста из БД или API.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            only_custom: Если True, возвращать URL только для пользовательских обложек (custom=True)
            
        Returns:
            URL обложки или None, если обложка не найдена
        """
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            return None
        
        # Сначала проверяем, есть ли сохраненный URL в БД (только если нужна custom обложка)
        if only_custom:
            cover_url = playlist.get("cover_url")
            if cover_url:
                return cover_url
        
        # Если нет в БД или нужна любая обложка, получаем из API
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Используем метод из YandexService (обертываем синхронный вызов)
        return await asyncio.to_thread(
            yandex_service.get_playlist_cover_url, playlist_kind, owner_id, only_custom=only_custom
        )
    
    async def get_playlist_cover_image(self, playlist_id: int, telegram_id: int) -> Optional[bytes]:
        """
        Получить изображение обложки плейлиста в виде байтов.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            
        Returns:
            Байты изображения или None, если обложка не найдена
        """
        # Получаем URL обложки (любую, не только custom)
        cover_url = await self.get_playlist_cover_url(playlist_id, telegram_id, only_custom=False)
        logger.debug(f"Получен URL обложки для плейлиста {playlist_id}: {cover_url}")
        if not cover_url:
            logger.debug(f"URL обложки не найден для плейлиста {playlist_id}")
            return None
        
        # Получаем клиент и создаем сервис для работы с API
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        # Скачиваем обложку с авторизацией (обертываем синхронный вызов)
        result = await asyncio.to_thread(yandex_service.download_playlist_cover, cover_url)
        if result:
            logger.debug(f"Обложка успешно получена для плейлиста {playlist_id}, размер: {len(result)} байт")
        else:
            logger.debug(f"Не удалось получить обложку для плейлиста {playlist_id}")
        return result
    
    async def sync_playlist_from_api(self, playlist_id: int, telegram_id: int) -> Tuple[bool, Optional[str]]:
        """
        Синхронизировать данные плейлиста из API Яндекс.Музыки с БД.
        Обновляет название, URL обложки (только для пользовательских обложек) и UUID.
        
        Args:
            playlist_id: ID плейлиста в БД
            telegram_id: ID пользователя Telegram (не используется, но оставлен для совместимости)
            
        Returns:
            Кортеж (успех, сообщение об ошибке)
        """
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            return False, "Плейлист не найден в БД"
        
        # Получаем клиент и создаем сервис для работы с API
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        playlist_kind = playlist["playlist_kind"]
        owner_id = playlist["owner_id"]
        
        # Получаем актуальные данные из API (обертываем синхронный вызов)
        title, cover_url, playlist_uuid, error = await asyncio.to_thread(
            yandex_service.get_playlist_info_for_sync, playlist_kind, owner_id
        )
        
        if error:
            return False, error
        
        # Обновляем данные в БД
        updates = {}
        if title and title != playlist.get("title"):
            updates["title"] = title
        if cover_url != playlist.get("cover_url"):
            # Обновляем cover_url (может быть None, если обложка не пользовательская)
            updates["cover_url"] = cover_url
        if playlist_uuid and playlist_uuid != playlist.get("uuid"):
            # Обновляем UUID, если он доступен и изменился
            updates["uuid"] = playlist_uuid
        
        if updates:
            await self.db.update_playlist(playlist_id, **updates)
            logger.debug(f"Синхронизированы данные плейлиста {playlist_id}: {updates}")
        
        return True, None

