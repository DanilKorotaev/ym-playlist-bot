"""
Обработчики для Telegram Web App (Mini App).
Обрабатывает данные, отправленные из Mini App через sendData().
"""
import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any

from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from database import DatabaseInterface
from yandex_client_manager import YandexClientManager
from utils.context import UserContextManager
from utils.message_helpers import send_message
from services.playlist_service import PlaylistService

logger = logging.getLogger(__name__)


class WebAppHandlers:
    """Класс с обработчиками для Web App."""
    
    def __init__(
        self,
        db: DatabaseInterface,
        client_manager: YandexClientManager,
        context_manager: UserContextManager
    ):
        """
        Инициализация обработчиков.
        
        Args:
            db: Интерфейс базы данных
            client_manager: Менеджер клиентов Яндекс.Музыки
            context_manager: Менеджер контекста пользователей
        """
        self.db = db
        self.client_manager = client_manager
        self.context_manager = context_manager
        self.playlist_service = PlaylistService(db, client_manager)
    
    async def handle_web_app_data(self, message: Message, state: FSMContext):
        """
        Обработчик данных от Web App.
        
        Args:
            message: Сообщение с данными от Web App
            state: FSM контекст
        """
        try:
            # В aiogram 3.x данные от Web App приходят в message.web_app_data.data
            if not message.web_app_data:
                logger.warning("Получено сообщение без web_app_data")
                return
            
            data_str = message.web_app_data.data
            
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON от Web App: {e}")
                await send_message(
                    message,
                    "❌ Ошибка: неверный формат данных от приложения.",
                    use_main_menu=True
                )
                return
            
            action = data.get("action")
            telegram_id = message.from_user.id
            
            logger.info(f"Получены данные от Web App от пользователя {telegram_id}: action={action}")
            
            # Обработка различных действий
            if action == "get_playlists":
                await self._handle_get_playlists(message, data)
            elif action == "get_tracks":
                await self._handle_get_tracks(message, data)
            elif action == "get_track_url":
                await self._handle_get_track_url(message, data)
            else:
                logger.warning(f"Неизвестное действие от Web App: {action}")
                await send_message(
                    message,
                    f"❌ Неизвестное действие: {action}",
                    use_main_menu=True
                )
        
        except Exception as e:
            logger.exception(f"Ошибка при обработке данных от Web App: {e}")
            await send_message(
                message,
                "❌ Произошла ошибка при обработке запроса от приложения.",
                use_main_menu=True
            )
    
    async def _handle_get_playlists(self, message: Message, data: Dict[str, Any]):
        """Обработка запроса списка плейлистов."""
        telegram_id = message.from_user.id
        
        try:
            # Получаем плейлисты пользователя
            user_playlists = await self.db.get_user_playlists(telegram_id)
            shared_playlists = await self.db.get_shared_playlists(telegram_id)
            
            # Форматируем плейлисты для ответа
            playlists = []
            
            for pl in user_playlists:
                track_count = await self.playlist_service.get_playlist_tracks_count(
                    pl["id"], telegram_id
                ) or 0
                
                playlists.append({
                    "id": pl["id"],
                    "title": pl["title"],
                    "track_count": track_count,
                    "cover_url": pl.get("cover_url"),
                    "is_shared": False
                })
            
            for pl in shared_playlists:
                track_count = await self.playlist_service.get_playlist_tracks_count(
                    pl["id"], telegram_id
                ) or 0
                
                playlists.append({
                    "id": pl["id"],
                    "title": pl["title"],
                    "track_count": track_count,
                    "cover_url": pl.get("cover_url"),
                    "is_shared": True
                })
            
            # Отправляем ответ обратно в Web App
            # В aiogram 3.x можно отправить ответ через answer_web_app_query
            # Но для MVP используем обычное сообщение (позже перейдем на REST API)
            response_data = {
                "action": "playlists_response",
                "playlists": playlists
            }
            
            await message.answer(
                f"📋 Найдено плейлистов: {len(playlists)}\n\n"
                f"⚠️ В текущей версии данные отправляются через сообщения.\n"
                f"В следующей версии будет использоваться REST API для более удобного взаимодействия.",
                reply_markup=None
            )
            
            logger.info(f"Отправлен список из {len(playlists)} плейлистов пользователю {telegram_id}")
        
        except Exception as e:
            logger.exception(f"Ошибка при получении плейлистов для Web App: {e}")
            await send_message(
                message,
                "❌ Ошибка при получении списка плейлистов.",
                use_main_menu=True
            )
    
    async def _handle_get_tracks(self, message: Message, data: Dict[str, Any]):
        """Обработка запроса списка треков из плейлиста."""
        telegram_id = message.from_user.id
        playlist_id = data.get("playlist_id")
        
        if not playlist_id:
            await send_message(
                message,
                "❌ Не указан ID плейлиста.",
                use_main_menu=True
            )
            return
        
        try:
            # Получаем треки из плейлиста
            tracks = await self.playlist_service.get_playlist_tracks(
                playlist_id, telegram_id
            )
            
            if tracks is None:
                await send_message(
                    message,
                    "❌ Плейлист не найден или нет доступа.",
                    use_main_menu=True
                )
                return
            
            # Форматируем треки для ответа
            formatted_tracks = []
            for i, track_item in enumerate(tracks):
                # Используем YandexService для форматирования
                client = await self.client_manager.get_client_for_playlist(playlist_id)
                from services.yandex_service import YandexService
                yandex_service = YandexService(client)
                
                track_id, track_title = yandex_service.extract_track_info(track_item)
                artists = yandex_service.get_track_artists(track_item)
                
                # Получаем длительность
                track_obj = track_item.track if hasattr(track_item, 'track') else track_item
                duration = getattr(track_obj, 'duration_ms', 0) // 1000
                
                formatted_tracks.append({
                    "id": track_id,
                    "title": track_title,
                    "artists": artists,
                    "duration": duration,
                    "position": i
                })
            
            # Получаем revision
            pl_obj = await self.playlist_service.get_playlist_object(playlist_id, telegram_id)
            current_revision = getattr(pl_obj, 'revision', None) if pl_obj else None
            
            response_data = {
                "action": "tracks_response",
                "tracks": formatted_tracks,
                "revision": current_revision
            }
            
            await message.answer(
                f"🎵 Найдено треков: {len(formatted_tracks)}\n\n"
                f"⚠️ В текущей версии данные отправляются через сообщения.\n"
                f"В следующей версии будет использоваться REST API.",
                reply_markup=None
            )
            
            logger.info(
                f"Отправлен список из {len(formatted_tracks)} треков "
                f"из плейлиста {playlist_id} пользователю {telegram_id}"
            )
        
        except Exception as e:
            logger.exception(f"Ошибка при получении треков для Web App: {e}")
            await send_message(
                message,
                "❌ Ошибка при получении списка треков.",
                use_main_menu=True
            )
    
    async def _handle_get_track_url(self, message: Message, data: Dict[str, Any]):
        """Обработка запроса URL трека для стриминга."""
        telegram_id = message.from_user.id
        track_id = data.get("track_id")
        playlist_id = data.get("playlist_id")
        
        if not track_id or not playlist_id:
            await send_message(
                message,
                "❌ Не указан ID трека или плейлиста.",
                use_main_menu=True
            )
            return
        
        try:
            # Получаем клиент и сервис
            client = await self.client_manager.get_client_for_playlist(playlist_id)
            from services.yandex_service import YandexService
            yandex_service = YandexService(client)
            
            # Получаем трек
            import asyncio
            track = await asyncio.to_thread(yandex_service.get_track, track_id)
            
            if not track:
                await send_message(
                    message,
                    "❌ Трек не найден.",
                    use_main_menu=True
                )
                return
            
            # Получаем download_info
            download_info = await asyncio.to_thread(track.get_download_info)
            
            if not download_info:
                await send_message(
                    message,
                    "❌ Не удалось получить информацию для скачивания трека.",
                    use_main_menu=True
                )
                return
            
            # Логика из tools/test_download_tracks.py
            # ПРИОРИТЕТ 1: Пробуем получить через get_direct_link()
            url = None
            if hasattr(download_info, "get_direct_link"):
                try:
                    url = await asyncio.to_thread(download_info.get_direct_link)
                    # Проверяем, не является ли это XML
                    if url and (url.startswith("<?xml") or url.startswith("<download-info>")):
                        logger.warning("get_direct_link() вернул XML, требуется парсинг")
                        url = None  # Будем строить из host и path
                except Exception as e:
                    logger.warning(f"Ошибка при вызове get_direct_link(): {e}")
                    url = None
            
            # ПРИОРИТЕТ 2: Если get_direct_link() не сработал, строим из host и path
            if not url:
                host = getattr(download_info, "host", None)
                path = getattr(download_info, "path", None)
                
                # Если это вложенный объект
                if not host and hasattr(download_info, "download_info"):
                    nested = download_info.download_info
                    host = getattr(nested, "host", None) if nested else None
                    path = getattr(nested, "path", None) if nested else None
                
                if host and path:
                    # Обработка XML, если нужно
                    if isinstance(host, str) and host.startswith('<'):
                        # Парсим XML
                        try:
                            root = ET.fromstring(host)
                            host_elem = root.find("host")
                            path_elem = root.find("path")
                            if host_elem is not None and path_elem is not None:
                                host = host_elem.text
                                path = path_elem.text
                        except ET.ParseError as e:
                            logger.warning(f"Ошибка парсинга XML: {e}")
                    
                    if host and path:
                        if not host.startswith("http"):
                            host = f"https://{host}"
                        url = f"{host}{path}"
            
            if not url:
                await send_message(
                    message,
                    "❌ Не удалось построить URL для стриминга.",
                    use_main_menu=True
                )
                return
            
            response_data = {
                "action": "track_url_response",
                "url": url,
                "track_id": track_id
            }
            
            await message.answer(
                f"🔗 URL трека получен\n\n"
                f"⚠️ В текущей версии URL отправляется через сообщение.\n"
                f"В следующей версии будет использоваться REST API.",
                reply_markup=None
            )
            
            logger.info(
                f"Отправлен URL трека {track_id} из плейлиста {playlist_id} "
                f"пользователю {telegram_id}"
            )
        
        except Exception as e:
            logger.exception(f"Ошибка при получении URL трека для Web App: {e}")
            await send_message(
                message,
                "❌ Ошибка при получении URL трека.",
                use_main_menu=True
            )

