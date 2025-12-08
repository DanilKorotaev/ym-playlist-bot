"""
REST API роуты для Mini App.
"""
import os
import logging
import asyncio
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.responses import JSONResponse

from miniapp.api.auth import validate_telegram_init_data, extract_user_id
from services.playlist_service import PlaylistService
from services.yandex_service import YandexService
from yandex_client_manager import YandexClientManager
from database import DatabaseInterface

logger = logging.getLogger(__name__)

router = APIRouter()

# Глобальные зависимости (будут установлены при запуске)
_db: Optional[DatabaseInterface] = None
_client_manager: Optional[YandexClientManager] = None
_db_factory: Optional[callable] = None  # Функция для создания нового экземпляра БД
_client_manager_factory: Optional[callable] = None  # Функция для создания нового client_manager


def set_dependencies(db: DatabaseInterface, client_manager: YandexClientManager):
    """Установить зависимости для роутов."""
    global _db, _client_manager, _db_factory, _client_manager_factory
    
    # Сохраняем оригинальные зависимости
    _db = db
    _client_manager = client_manager
    
    # Сохраняем фабрику для создания нового экземпляра БД в текущем event loop
    import os
    db_type = os.getenv("DB_TYPE", "sqlite").lower()
    
    if db_type == "postgresql":
        # Для PostgreSQL создаем фабрику, которая создаст новый экземпляр с новым pool
        if hasattr(db, 'host'):
            def create_db():
                from database.postgresql_db import PostgreSQLDatabase
                return PostgreSQLDatabase(
                    host=db.host,
                    port=db.port,
                    database=db.database,
                    user=db.user,
                    password=db.password
                )
        else:
            def create_db():
                from database.postgresql_db import PostgreSQLDatabase
                return PostgreSQLDatabase()
        _db_factory = create_db
    else:
        # Для SQLite используем тот же экземпляр (с блокировкой)
        _db_factory = None
    
    # Сохраняем фабрику для создания нового client_manager с правильной БД
    default_token = client_manager.default_token
    timeout = client_manager.timeout
    
    def create_client_manager(fastapi_db: DatabaseInterface):
        from yandex_client_manager import YandexClientManager
        return YandexClientManager(default_token, fastapi_db, timeout)
    
    _client_manager_factory = create_client_manager


async def get_user_id(x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data")) -> int:
    """
    Извлекает user_id из initData (зависимость для FastAPI).
    
    Args:
        x_telegram_init_data: Заголовок с initData от Telegram Web App
        
    Returns:
        user_id
        
    Raises:
        HTTPException: Если авторизация не прошла
    """
    bot_token = os.getenv("TELEGRAM_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")
    
    try:
        user_id = extract_user_id(x_telegram_init_data, bot_token)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid initData: user_id not found")
        return user_id
    except ValueError as e:
        logger.warning(f"Invalid initData: {e}")
        raise HTTPException(status_code=401, detail="Invalid initData signature")
    except Exception as e:
        logger.error(f"Error validating initData: {e}")
        raise HTTPException(status_code=401, detail="Invalid initData")


# Глобальные экземпляры для текущего event loop (FastAPI)
_fastapi_db: Optional[DatabaseInterface] = None
_fastapi_client_manager: Optional[YandexClientManager] = None


async def init_fastapi_db():
    """Инициализировать БД и client_manager для FastAPI event loop (для PostgreSQL создает новый pool)."""
    global _fastapi_db, _fastapi_client_manager
    
    # Для PostgreSQL создаем новый экземпляр БД с новым pool
    if _db_factory is not None and _fastapi_db is None:
        _fastapi_db = _db_factory()
        # Инициализируем pool
        await _fastapi_db._get_pool()
        
        # Создаем отдельный client_manager для FastAPI с правильной БД
        if _client_manager_factory is not None:
            _fastapi_client_manager = _client_manager_factory(_fastapi_db)
            # Инициализируем дефолтный аккаунт
            await _fastapi_client_manager.init_default_account()


def get_db() -> DatabaseInterface:
    """Получить экземпляр БД для текущего event loop."""
    global _fastapi_db
    
    if _db is None:
        logger.error("Database not initialized! Call set_dependencies() first.")
        raise HTTPException(
            status_code=500,
            detail="Database not initialized. Server may not be fully started."
        )
    
    # Для PostgreSQL создаем отдельный экземпляр с новым pool в текущем event loop
    if _db_factory is not None:
        # Создаем новый экземпляр БД для текущего event loop (если еще не создан)
        if _fastapi_db is None:
            _fastapi_db = _db_factory()
        return _fastapi_db
    
    # Для SQLite используем тот же экземпляр (с блокировкой)
    return _db


def get_client_manager() -> YandexClientManager:
    """Получить менеджер клиентов для текущего event loop."""
    global _fastapi_client_manager
    
    if _client_manager is None:
        logger.error("Client manager not initialized! Call set_dependencies() first.")
        raise HTTPException(
            status_code=500,
            detail="Client manager not initialized. Server may not be fully started."
        )
    
    # Для PostgreSQL используем отдельный client_manager с правильной БД
    if _fastapi_client_manager is not None:
        return _fastapi_client_manager
    
    # Для SQLite используем общий client_manager
    return _client_manager


def get_playlist_service() -> PlaylistService:
    """Получить сервис плейлистов."""
    db = get_db()
    client_manager = get_client_manager()
    return PlaylistService(db, client_manager)


@router.get("/playlists")
async def get_playlists(
    user_id: int = Depends(get_user_id),
    playlist_service: PlaylistService = Depends(get_playlist_service),
    db: DatabaseInterface = Depends(get_db)
):
    """
    Получить список доступных плейлистов пользователя.
    
    Returns:
        JSON с массивом плейлистов
    """
    try:
        # Получаем плейлисты из БД
        user_playlists = await db.get_user_playlists(user_id)
        shared_playlists = await db.get_shared_playlists(user_id)
        
        # Форматируем для ответа
        playlists = []
        
        for pl in user_playlists:
            try:
                track_count = await playlist_service.get_playlist_tracks_count(
                    pl["id"], user_id
                ) or 0
            except Exception as e:
                logger.warning(f"Ошибка при получении количества треков для плейлиста {pl['id']}: {e}")
                track_count = 0  # Используем 0, если не удалось получить
            
            playlists.append({
                "id": pl["id"],
                "title": pl["title"],
                "track_count": track_count,
                "cover_url": pl.get("cover_url"),
                "is_shared": False
            })
        
        for pl in shared_playlists:
            try:
                track_count = await playlist_service.get_playlist_tracks_count(
                    pl["id"], user_id
                ) or 0
            except Exception as e:
                logger.warning(f"Ошибка при получении количества треков для плейлиста {pl['id']}: {e}")
                track_count = 0  # Используем 0, если не удалось получить
            
            playlists.append({
                "id": pl["id"],
                "title": pl["title"],
                "track_count": track_count,
                "cover_url": pl.get("cover_url"),
                "is_shared": True
            })
        
        return {"playlists": playlists}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при получении плейлистов для user_id={user_id}: {e}")
        # В режиме разработки возвращаем детальную информацию об ошибке
        import os
        if os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG":
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {str(e)}"
            )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/playlists/{playlist_id}/tracks")
async def get_playlist_tracks(
    playlist_id: int,
    revision: Optional[int] = None,
    user_id: int = Depends(get_user_id),
    playlist_service: PlaylistService = Depends(get_playlist_service)
):
    """
    Получить список треков из плейлиста.
    
    Args:
        playlist_id: ID плейлиста
        revision: Опциональная версия плейлиста для проверки обновлений
        
    Returns:
        JSON с массивом треков и текущей revision
    """
    try:
        # Получаем треки из плейлиста
        tracks = await playlist_service.get_playlist_tracks(playlist_id, user_id)
        
        if tracks is None:
            raise HTTPException(status_code=404, detail="Playlist not found or access denied")
        
        # Получаем клиент для форматирования треков
        client = await get_client_manager().get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        # Форматируем треки
        formatted_tracks = []
        for i, track_item in enumerate(tracks):
            track_id, track_title = yandex_service.extract_track_info(track_item)
            
            # Получаем артистов как массив
            track_obj = track_item.track if hasattr(track_item, 'track') else track_item
            artists = []
            if getattr(track_obj, "artists", None):
                artists = [a.name for a in getattr(track_obj, "artists", []) if getattr(a, "name", None)]
            
            # Получаем длительность
            duration = getattr(track_obj, 'duration_ms', 0) // 1000
            
            formatted_tracks.append({
                "id": track_id,
                "title": track_title,
                "artists": artists,  # Массив артистов
                "duration": duration,
                "position": i
            })
        
        # Получаем revision из плейлиста
        pl_obj = await playlist_service.get_playlist_object(playlist_id, user_id)
        current_revision = getattr(pl_obj, 'revision', None) if pl_obj else None
        
        return {
            "tracks": formatted_tracks,
            "revision": current_revision
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при получении треков: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/playlists/{playlist_id}/updates")
async def check_playlist_updates(
    playlist_id: int,
    revision: int,
    user_id: int = Depends(get_user_id),
    playlist_service: PlaylistService = Depends(get_playlist_service)
):
    """
    Проверить обновления плейлиста (для polling).
    
    Args:
        playlist_id: ID плейлиста
        revision: Текущая версия плейлиста
        
    Returns:
        JSON с информацией об обновлениях
    """
    try:
        # Получаем текущее состояние плейлиста
        pl_obj = await playlist_service.get_playlist_object(playlist_id, user_id)
        if not pl_obj:
            raise HTTPException(status_code=404, detail="Playlist not found or access denied")
        
        current_revision = getattr(pl_obj, 'revision', None)
        
        # Если revision совпадает, обновлений нет
        if current_revision == revision:
            return {
                "has_updates": False,
                "new_tracks_count": 0,
                "new_revision": current_revision,
                "new_tracks": []
            }
        
        # Если revision изменился, получаем новые треки
        tracks = await playlist_service.get_playlist_tracks(playlist_id, user_id)
        if tracks is None:
            raise HTTPException(status_code=404, detail="Playlist not found or access denied")
        
        # Получаем клиент для форматирования
        client = await get_client_manager().get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        # Форматируем новые треки (все треки, так как мы не знаем, какие именно новые)
        formatted_tracks = []
        for i, track_item in enumerate(tracks):
            track_id, track_title = yandex_service.extract_track_info(track_item)
            
            # Получаем артистов как массив
            track_obj = track_item.track if hasattr(track_item, 'track') else track_item
            artists = []
            if getattr(track_obj, "artists", None):
                artists = [a.name for a in getattr(track_obj, "artists", []) if getattr(a, "name", None)]
            
            duration = getattr(track_obj, 'duration_ms', 0) // 1000
            
            formatted_tracks.append({
                "id": track_id,
                "title": track_title,
                "artists": artists,  # Массив артистов
                "duration": duration,
                "position": i
            })
        
        return {
            "has_updates": True,
            "new_tracks_count": len(formatted_tracks),
            "new_revision": current_revision,
            "new_tracks": formatted_tracks
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при проверке обновлений: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _build_streaming_url(download_info: Any) -> Optional[str]:
    """
    Построить URL для стриминга из download_info.
    
    Args:
        download_info: Объект download_info от API Яндекс.Музыки
        
    Returns:
        URL для стриминга или None
    """
    url = None
    
    # ПРИОРИТЕТ 1: Пробуем получить через get_direct_link()
    if hasattr(download_info, "get_direct_link"):
        try:
            url = download_info.get_direct_link()
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
    
    return url


@router.get("/tracks/{track_id}/stream")
async def get_track_stream_url(
    track_id: int,
    playlist_id: int,
    user_id: int = Depends(get_user_id),
    playlist_service: PlaylistService = Depends(get_playlist_service),
    client_manager: YandexClientManager = Depends(get_client_manager)
):
    """
    Получить URL трека для стриминга.
    
    Args:
        track_id: ID трека
        playlist_id: ID плейлиста (для получения правильного клиента)
        
    Returns:
        JSON с URL трека и временем истечения (если доступно)
    """
    try:
        # Получаем клиент и сервис
        client = await client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        # Получаем трек
        track = await asyncio.to_thread(yandex_service.get_track, track_id)
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Получаем download_info
        download_info = await asyncio.to_thread(track.get_download_info)
        
        if not download_info:
            raise HTTPException(
                status_code=500,
                detail="Failed to get download info for track"
            )
        
        # Строим URL
        url = _build_streaming_url(download_info)
        
        if not url:
            raise HTTPException(
                status_code=500,
                detail="Failed to build streaming URL"
            )
        
        return {
            "url": url,
            "expires_at": None  # Можно добавить, если API предоставляет время истечения
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Ошибка при получении URL трека: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

