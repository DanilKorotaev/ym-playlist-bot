"""
REST API роуты для Mini App.
"""
import os
import logging
import asyncio
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Header, HTTPException, Depends, Request
from fastapi.responses import JSONResponse

from miniapp.api.auth import validate_telegram_init_data, extract_user_id
from services.playlist_service import PlaylistService
from services.yandex_service import YandexService
from yandex_client_manager import YandexClientManager
from database import DatabaseInterface

# Настройка логгера с учетом переменной окружения
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, LOG_LEVEL, logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(log_level)

# Логируем уровень при инициализации модуля (только для DEBUG)
if log_level <= logging.DEBUG:
    logger.debug(f"Логгер routes.py инициализирован с уровнем {LOG_LEVEL} ({log_level})")

router = APIRouter()


# ============================================================================
# Dependency Injection для FastAPI
# ============================================================================

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


def get_db(request: Request) -> DatabaseInterface:
    """
    Получить экземпляр БД для текущего запроса.
    
    Использует app.state для хранения зависимостей, что позволяет
    правильно управлять жизненным циклом для разных типов БД:
    - PostgreSQL: отдельный connection pool для FastAPI event loop
    - SQLite: общий экземпляр с блокировкой
    
    Args:
        request: FastAPI Request объект для доступа к app.state
        
    Returns:
        Экземпляр DatabaseInterface
        
    Raises:
        HTTPException: Если БД не инициализирована
    """
    if not hasattr(request.app.state, 'db'):
        logger.error("Database not initialized! Check lifespan events.")
        raise HTTPException(
            status_code=500,
            detail="Database not initialized. Server may not be fully started."
        )
    
    return request.app.state.db


def get_client_manager(request: Request) -> YandexClientManager:
    """
    Получить менеджер клиентов для текущего запроса.
    
    Args:
        request: FastAPI Request объект для доступа к app.state
        
    Returns:
        Экземпляр YandexClientManager
        
    Raises:
        HTTPException: Если client_manager не инициализирован
    """
    if not hasattr(request.app.state, 'client_manager'):
        logger.error("Client manager not initialized! Check lifespan events.")
        raise HTTPException(
            status_code=500,
            detail="Client manager not initialized. Server may not be fully started."
        )
    
    return request.app.state.client_manager


def get_playlist_service(
    db: DatabaseInterface = Depends(get_db),
    client_manager: YandexClientManager = Depends(get_client_manager)
) -> PlaylistService:
    """
    Получить сервис плейлистов.
    
    Args:
        db: Экземпляр БД (внедряется через Depends)
        client_manager: Менеджер клиентов (внедряется через Depends)
        
    Returns:
        Экземпляр PlaylistService
    """
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
    playlist_service: PlaylistService = Depends(get_playlist_service),
    client_manager: YandexClientManager = Depends(get_client_manager)
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
        client = await client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        # Форматируем треки
        formatted_tracks = []
        for i, track_item in enumerate(tracks):
            track_id, _ = yandex_service.extract_track_info(track_item)
            
            # Получаем сам трек (может быть обернут в PlaylistTrack)
            track_obj = track_item.track if hasattr(track_item, 'track') else track_item
            
            # Получаем название трека
            track_title = getattr(track_obj, "title", None) or "Без названия"
            
            # Получаем артистов как массив
            artists = []
            if getattr(track_obj, "artists", None):
                artists = [a.name for a in getattr(track_obj, "artists", []) if getattr(a, "name", None)]
            
            # Получаем длительность
            duration = getattr(track_obj, 'duration_ms', 0) // 1000
            
            # Получаем обложку трека (из альбома или самого трека)
            cover_url = None
            if getattr(track_obj, 'albums', None) and len(track_obj.albums) > 0:
                album = track_obj.albums[0]
                if hasattr(album, 'cover_uri') and album.cover_uri:
                    cover_uri = album.cover_uri.replace('%%', '300x300')
                    if cover_uri.startswith('//'):
                        cover_url = f'https:{cover_uri}'
                    elif cover_uri.startswith('/'):
                        cover_url = f'https://music.yandex.ru{cover_uri}'
                    elif cover_uri.startswith('http://') or cover_uri.startswith('https://'):
                        cover_url = cover_uri
            
            formatted_tracks.append({
                "id": track_id,
                "title": track_title,
                "artists": artists,  # Массив артистов
                "duration": duration,
                "cover_url": cover_url,
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
    playlist_service: PlaylistService = Depends(get_playlist_service),
    client_manager: YandexClientManager = Depends(get_client_manager)
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
        client = await client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        # Форматируем новые треки (все треки, так как мы не знаем, какие именно новые)
        formatted_tracks = []
        for i, track_item in enumerate(tracks):
            track_id, _ = yandex_service.extract_track_info(track_item)
            
            # Получаем сам трек (может быть обернут в PlaylistTrack)
            track_obj = track_item.track if hasattr(track_item, 'track') else track_item
            
            # Получаем название трека
            track_title = getattr(track_obj, "title", None) or "Без названия"
            
            # Получаем артистов как массив
            artists = []
            if getattr(track_obj, "artists", None):
                artists = [a.name for a in getattr(track_obj, "artists", []) if getattr(a, "name", None)]
            
            duration = getattr(track_obj, 'duration_ms', 0) // 1000
            
            # Получаем обложку трека (из альбома или самого трека)
            cover_url = None
            if getattr(track_obj, 'albums', None) and len(track_obj.albums) > 0:
                album = track_obj.albums[0]
                if hasattr(album, 'cover_uri') and album.cover_uri:
                    cover_uri = album.cover_uri.replace('%%', '300x300')
                    if cover_uri.startswith('//'):
                        cover_url = f'https:{cover_uri}'
                    elif cover_uri.startswith('/'):
                        cover_url = f'https://music.yandex.ru{cover_uri}'
                    elif cover_uri.startswith('http://') or cover_uri.startswith('https://'):
                        cover_url = cover_uri
            
            formatted_tracks.append({
                "id": track_id,
                "title": track_title,
                "artists": artists,  # Массив артистов
                "duration": duration,
                "cover_url": cover_url,
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
        download_info: Объект download_info от API Яндекс.Музыки (может быть объектом или списком)
        
    Returns:
        URL для стриминга или None
    """
    # Если это список вариантов, выбираем первый (обычно лучший)
    if isinstance(download_info, list):
        if not download_info:
            logger.warning("download_info - пустой список")
            return None
        logger.debug(f"download_info - список из {len(download_info)} вариантов, выбираю первый")
        download_info = download_info[0]
    
    url = None
    
    # ПРИОРИТЕТ 1: Пробуем получить через get_direct_link()
    if hasattr(download_info, "get_direct_link"):
        try:
            url = download_info.get_direct_link()
            logger.debug(f"get_direct_link() вернул: {type(url)}, длина: {len(str(url)) if url else 0}")
            
            # Проверяем, не является ли это XML
            if url and isinstance(url, str):
                if url.startswith("<?xml") or url.startswith("<download-info>"):
                    logger.warning("get_direct_link() вернул XML вместо URL, требуется парсинг")
                    # Пробуем извлечь URL из XML
                    url = _extract_url_from_xml(url)
                    if not url:
                        url = None  # Будем строить из host и path
                elif not (url.startswith("http://") or url.startswith("https://")):
                    logger.warning(f"get_direct_link() вернул неожиданный формат: {url[:50]}...")
                    url = None
        except Exception as e:
            logger.warning(f"Ошибка при вызове get_direct_link(): {e}", exc_info=True)
            url = None
    
    # ПРИОРИТЕТ 2: Если get_direct_link() не сработал, строим из host и path
    if not url:
        host = getattr(download_info, "host", None)
        path = getattr(download_info, "path", None)
        
        logger.debug(f"Пробую построить URL из host и path: host={type(host)}, path={type(path)}")
        
        # Если это вложенный объект
        if not host and hasattr(download_info, "download_info"):
            nested = download_info.download_info
            if nested:
                host = getattr(nested, "host", None)
                path = getattr(nested, "path", None)
                logger.debug("Использую вложенный download_info")
        
        # Обработка XML в host или path
        if isinstance(host, str) and host.startswith('<'):
            logger.debug("host содержит XML, парсю...")
            try:
                root = ET.fromstring(host)
                host_elem = root.find("host")
                path_elem = root.find("path")
                if host_elem is not None and path_elem is not None:
                    host = host_elem.text
                    path = path_elem.text
                    logger.debug(f"Извлечено из XML: host={host[:50] if host else None}...")
            except ET.ParseError as e:
                logger.warning(f"Ошибка парсинга XML в host: {e}")
        
        if isinstance(path, str) and path.startswith('<'):
            logger.debug("path содержит XML, парсю...")
            try:
                root = ET.fromstring(path)
                host_elem = root.find("host")
                path_elem = root.find("path")
                if host_elem is not None and path_elem is not None:
                    host = host_elem.text
                    path = path_elem.text
                    logger.debug(f"Извлечено из XML в path: host={host[:50] if host else None}...")
            except ET.ParseError as e:
                logger.warning(f"Ошибка парсинга XML в path: {e}")
        
        if host and path:
            # Преобразуем в строки, если это не строки
            host = str(host).strip()
            path = str(path).strip()
            
            if not host.startswith("http://") and not host.startswith("https://"):
                host = f"https://{host}"
            
            url = f"{host}{path}"
            logger.debug(f"URL построен из host и path: {url[:100]}...")
        else:
            logger.warning(f"Не удалось построить URL: host={host}, path={path}")
    
    if url:
        logger.debug(f"Итоговый URL: {url[:100]}...")
    else:
        logger.error("Не удалось построить streaming URL из download_info")
        # Логируем структуру объекта для отладки
        if hasattr(download_info, "__dict__"):
            logger.debug(f"Атрибуты download_info: {list(download_info.__dict__.keys())}")
    
    return url


def _extract_url_from_xml(xml_content: str) -> Optional[str]:
    """
    Извлечь URL из XML содержимого.
    
    Args:
        xml_content: XML строка с информацией о скачивании
        
    Returns:
        URL или None, если не удалось извлечь
    """
    try:
        root = ET.fromstring(xml_content)
        host_elem = root.find("host")
        path_elem = root.find("path")
        
        if host_elem is not None and path_elem is not None:
            host = host_elem.text
            path = path_elem.text
            
            if host and path:
                if not host.startswith("http://") and not host.startswith("https://"):
                    host = f"https://{host}"
                url = f"{host}{path}"
                logger.debug(f"URL извлечен из XML: {url[:100]}...")
                return url
    except ET.ParseError as e:
        logger.warning(f"Ошибка парсинга XML: {e}")
    except Exception as e:
        logger.warning(f"Ошибка при извлечении URL из XML: {e}")
    
    return None


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
        logger.debug(f"Запрос URL для трека {track_id} из плейлиста {playlist_id} (user_id={user_id})")
        
        # Получаем клиент и сервис
        client = await client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        # Получаем трек
        logger.debug(f"Получаю трек {track_id}...")
        track = await asyncio.to_thread(yandex_service.get_track, track_id)
        
        if not track:
            logger.warning(f"Трек {track_id} не найден")
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Получаем download_info
        logger.debug(f"Получаю download_info для трека {track_id}...")
        try:
            download_info = await asyncio.to_thread(track.get_download_info)
        except AttributeError:
            logger.error(f"Трек {track_id} не имеет метода get_download_info")
            raise HTTPException(
                status_code=500,
                detail="Track does not support download info"
            )
        except Exception as e:
            logger.error(f"Ошибка при вызове get_download_info() для трека {track_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get download info: {str(e)}"
            )
        
        if not download_info:
            logger.warning(f"download_info для трека {track_id} вернул None или пустое значение")
            raise HTTPException(
                status_code=500,
                detail="Failed to get download info for track (empty response)"
            )
        
        logger.debug(f"download_info получен: тип={type(download_info)}")
        
        # Строим URL
        logger.debug(f"Строю streaming URL из download_info...")
        url = _build_streaming_url(download_info)
        
        if not url:
            logger.error(f"Не удалось построить streaming URL для трека {track_id}")
            # Логируем дополнительную информацию для отладки
            if hasattr(download_info, "__dict__"):
                logger.debug(f"Атрибуты download_info: {list(download_info.__dict__.keys())}")
            raise HTTPException(
                status_code=500,
                detail="Failed to build streaming URL. Track may be unavailable or restricted."
            )
        
        logger.info(f"Streaming URL успешно построен для трека {track_id}")
        return {
            "url": url,
            "expires_at": None  # Можно добавить, если API предоставляет время истечения
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Неожиданная ошибка при получении URL трека {track_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

