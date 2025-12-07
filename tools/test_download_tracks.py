#!/usr/bin/env python3
"""
Тестовый скрипт для скачивания треков из плейлиста и исследования стриминга.
Работает напрямую с API Яндекс.Музыки, без использования БД.
Основан на примере player.py из yandex-music-api.

Использование:
    python test_download_tracks.py
    или
    python test_download_tracks.py --token YOUR_TOKEN
    или
    python test_download_tracks.py --streaming  # режим исследования стриминга
"""
import os
import sys
import re
import time
import logging
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

from yandex_music import Client

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, LOG_LEVEL, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Константы
DEFAULT_CACHE_FOLDER = Path(__file__).resolve().parent.parent / '.YMcache'
MAX_ERRORS = 3

# ============================================================================
# ОБЪЯСНЕНИЕ: Стриминг vs Скачивание
# ============================================================================
# 
# СТРИМИНГ (Streaming):
# - Воспроизведение аудио напрямую из интернета без полного скачивания
# - Данные передаются в реальном времени по частям (чанками)
# - Можно начать воспроизведение сразу, не дожидаясь полной загрузки
# - Требует постоянное подключение к интернету
# - Файл не сохраняется на устройстве (или сохраняется временно в кэше)
# - Поддерживает HTTP Range Requests (запросы части файла)
# 
# СКАЧИВАНИЕ (Download):
# - Полная загрузка файла на устройство
# - Файл сохраняется локально и может воспроизводиться офлайн
# - Требует время на полную загрузку перед воспроизведением
# - После скачивания не требует интернет-соединения
# 
# ВОЗМОЖНОСТЬ ИСПОЛЬЗОВАНИЯ ССЫЛКИ ДЛЯ СКАЧИВАНИЯ В СТРИМИНГЕ:
# - Если ссылка поддерживает HTTP Range Requests (заголовок Accept-Ranges: bytes),
#   то её можно использовать для стриминга
# - Медиаплееры могут запрашивать части файла (например, первые 1MB для начала
#   воспроизведения), а затем подгружать остальное по мере необходимости
# - Если в браузере при вставке ссылки открывается встроенный плеер и начинается
#   воспроизведение - это хороший признак поддержки стриминга
# ============================================================================


def get_token() -> Optional[str]:
    """Получить токен Яндекс.Музыки из переменных окружения или запросить у пользователя."""
    # Сначала пробуем из переменных окружения
    token = os.getenv("YANDEX_TOKEN")
    
    if token:
        return token
    
    # Если нет в окружении, запрашиваем у пользователя
    print("\n🔐 Токен Яндекс.Музыки не найден в переменных окружения.")
    print("💡 Вы можете установить его в .env файле как YANDEX_TOKEN")
    token = input("👉 Введите токен Яндекс.Музыки: ").strip()
    
    if not token:
        print("❌ Токен не может быть пустым.")
        return None
    
    return token


def list_playlists(client: Client) -> List:
    """
    Получить список плейлистов пользователя из API.
    
    Returns:
        Список плейлистов пользователя
    """
    print("\n📁 Получаю список плейлистов...\n")
    
    try:
        # Получаем список плейлистов пользователя
        playlists = client.users_playlists_list()
        
        if not playlists:
            print("❌ У вас нет плейлистов.")
            return []
        
        print(f"✅ Найдено плейлистов: {len(playlists)}\n")
        
        for i, pl in enumerate(playlists, 1):
            title = pl.title if hasattr(pl, "title") else f"Плейлист #{i}"
            track_count = pl.track_count if hasattr(pl, "track_count") else 0
            playlist_id = pl.playlist_id if hasattr(pl, "playlist_id") else pl.kind if hasattr(pl, "kind") else "?"
            
            print(f"{i}. {title} ({track_count} треков, ID: {playlist_id})")
        
        return playlists
    except Exception as e:
        logger.error(f"Ошибка при получении плейлистов: {e}")
        print(f"❌ Ошибка при получении плейлистов: {e}")
        return []


def show_playlist_tracks(playlist) -> List:
    """
    Показать список треков в плейлисте и вернуть их.
    
    Args:
        playlist: Объект плейлиста из API
        
    Returns:
        Список треков
    """
    print(f"\n🎵 Плейлист: {playlist.title if hasattr(playlist, 'title') else 'Unknown'}")
    
    # Получаем треки из плейлиста
    tracks = playlist.tracks if hasattr(playlist, "tracks") and playlist.tracks else None
    
    if not tracks:
        # Если треки не загружены, загружаем их
        try:
            tracks = playlist.fetch_tracks()
        except Exception as e:
            logger.error(f"Ошибка при загрузке треков: {e}")
            print(f"❌ Ошибка при загрузке треков: {e}")
            return []
    
    if not tracks:
        print("⚠️  Плейлист пуст.")
        return []
    
    print(f"\n📊 Треков в плейлисте: {len(tracks)}\n")
    
    # Показываем список треков
    for i, track_item in enumerate(tracks, 1):
        # Получаем трек
        track = track_item.track if hasattr(track_item, "track") and track_item.track else track_item
        
        # Если трек не загружен, загружаем его
        if not hasattr(track, "title") or not track.title:
            try:
                track = track_item.fetchTrack() if hasattr(track_item, "fetchTrack") else track
            except:
                pass
        
        track_title = getattr(track, "title", "Unknown")
        artists = []
        if hasattr(track, "artists") and track.artists:
            artists = [a.name for a in track.artists if hasattr(a, "name") and a.name]
        
        artist_line = " / ".join(artists) if artists else "Unknown"
        print(f"{i}. {track_title} — {artist_line}")
    
    return tracks


def download_track(track_item, cache_folder: Path) -> Optional[Path]:
    """
    Скачать трек из плейлиста.
    
    Args:
        track_item: Объект трека из плейлиста
        cache_folder: Папка для кэширования
        
    Returns:
        Путь к скачанному файлу или None при ошибке
    """
    try:
        # Получаем полный объект трека (как в примере player.py)
        track = track_item.track if hasattr(track_item, "track") and track_item.track else track_item
        
        # Если трек не загружен полностью, загружаем его
        if not hasattr(track, "title") or not track.title:
            if hasattr(track_item, "fetchTrack"):
                track = track_item.fetchTrack()
            elif hasattr(track, "fetchTrack"):
                track = track.fetchTrack()
        
        # Формируем информацию о треке
        track_title = getattr(track, "title", "Unknown")
        artists = []
        artist_objects = []
        if hasattr(track, "artists") and track.artists:
            artist_objects = track.artists
            artists = [a.name for a in artist_objects if hasattr(a, "name") and a.name]
        
        # Получаем имя и ID первого артиста
        if artist_objects and len(artist_objects) > 0:
            first_artist = artist_objects[0]
            artist_name = getattr(first_artist, "name", "Unknown")
            artist_id = getattr(first_artist, "id", "0")
        else:
            artist_name = "Unknown"
            artist_id = "0"
        
        albums = []
        if hasattr(track, "albums") and track.albums:
            albums = track.albums
        
        album_title = albums[0].title if albums and hasattr(albums[0], "title") else "Unknown"
        album_id = albums[0].id if albums and hasattr(albums[0], "id") else "0"
        
        track_id = getattr(track, "id", "0")
        
        # Формируем путь к файлу (как в примере player.py)
        artist_dir = Path(f'{artist_name}_{artist_id}'.replace('/', '_'))
        album_dir = Path(f'{album_title}_{album_id}'.replace('/', '_'))
        file_path = cache_folder / artist_dir / album_dir / f'{track_title}_{track_id}.mp3'.replace('/', '_')
        
        # Если файл уже существует, пропускаем
        if file_path.exists():
            logger.info(f"✓ Файл уже существует: {file_path}")
            return file_path
        
        # Создаем директории
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Скачиваем трек
        logger.info(f"⬇️  Скачиваю: {track_title} — {', '.join(artists) if artists else 'Unknown'}")
        
        download_attempts = 0
        while download_attempts < MAX_ERRORS:
            try:
                track.download(file_path)
                logger.info(f"✓ Скачан: {file_path}")
                return file_path
            except Exception as e:
                download_attempts += 1
                logger.warning(f"Ошибка при скачивании (попытка {download_attempts}/{MAX_ERRORS}): {e}")
                if download_attempts < MAX_ERRORS:
                    time.sleep(1)
        
        logger.error(f"❌ Не удалось скачать трек после {MAX_ERRORS} попыток")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка при обработке трека: {e}", exc_info=True)
        return None


def get_track_full_info(track_item) -> Optional[Any]:
    """
    Получить полный объект трека.
    
    Args:
        track_item: Объект трека из плейлиста
        
    Returns:
        Полный объект трека или None
    """
    try:
        # Получаем трек
        track = track_item.track if hasattr(track_item, "track") and track_item.track else track_item
        
        # Если трек не загружен полностью, загружаем его
        if not hasattr(track, "title") or not track.title:
            if hasattr(track_item, "fetchTrack"):
                track = track_item.fetchTrack()
            elif hasattr(track, "fetchTrack"):
                track = track.fetchTrack()
        
        return track
    except Exception as e:
        logger.error(f"Ошибка при получении полной информации о треке: {e}")
        return None


def investigate_streaming_info(track_item, client: Client) -> Optional[Dict[str, Any]]:
    """
    Исследовать информацию о стриминге для трека через get_download_info().
    
    Args:
        track_item: Объект трека из плейлиста
        client: Клиент Яндекс.Музыки
        
    Returns:
        Словарь с информацией о стриминге или None при ошибке
    """
    try:
        # Получаем полный объект трека
        track = get_track_full_info(track_item)
        if not track:
            return None
        
        track_id = getattr(track, "id", None)
        if not track_id:
            logger.error("Не удалось получить ID трека")
            return None
        
        track_title = getattr(track, "title", "Unknown")
        artists = []
        if hasattr(track, "artists") and track.artists:
            artists = [a.name for a in track.artists if hasattr(a, "name") and a.name]
        artist_line = " / ".join(artists) if artists else "Unknown"
        
        logger.info(f"🔍 Исследую стриминг для: {track_title} — {artist_line}")
        logger.info(f"   Track ID: {track_id}")
        
        # Пробуем получить информацию о скачивании через get_download_info()
        download_info = None
        if hasattr(track, "get_download_info"):
            try:
                logger.debug("Вызываю track.get_download_info()...")
                download_info = track.get_download_info()
                logger.debug(f"get_download_info() вернул: {type(download_info)}")
            except Exception as e:
                logger.warning(f"Ошибка при вызове track.get_download_info(): {e}")
        
        # Если метод не найден, пробуем через клиент
        if not download_info:
            try:
                if hasattr(client, "tracks_download_info"):
                    logger.debug("Пробую client.tracks_download_info()...")
                    download_info = client.tracks_download_info(track_id)
                    logger.debug(f"tracks_download_info() вернул: {type(download_info)}")
            except Exception as e:
                logger.warning(f"Ошибка при вызове client.tracks_download_info(): {e}")
        
        if not download_info:
            logger.error("Не удалось получить информацию о скачивании")
            return {
                "track_id": track_id,
                "track_title": track_title,
                "artists": artist_line,
                "error": "Не удалось получить download_info"
            }
        
        # Логируем структуру объекта download_info
        logger.info("=" * 60)
        logger.info(f"📋 СТРУКТУРА download_info:")
        logger.info(f"   Тип: {type(download_info)}")
        
        # Если это список, обрабатываем каждый элемент
        if isinstance(download_info, list):
            logger.info(f"   Количество вариантов: {len(download_info)}")
            result = {
                "track_id": track_id,
                "track_title": track_title,
                "artists": artist_line,
                "variants": []
            }
            
            for idx, variant in enumerate(download_info):
                logger.info(f"\n   --- Вариант {idx + 1} ---")
                variant_info = _analyze_download_variant(variant, client)
                result["variants"].append(variant_info)
            
            return result
        else:
            # Один вариант
            logger.info("\n   --- Единственный вариант ---")
            variant_info = _analyze_download_variant(download_info, client)
            return {
                "track_id": track_id,
                "track_title": track_title,
                "artists": artist_line,
                "variants": [variant_info]
            }
            
    except Exception as e:
        logger.error(f"Ошибка при исследовании стриминга: {e}", exc_info=True)
        return None


def _analyze_download_variant(variant: Any, client: Client) -> Dict[str, Any]:
    """
    Анализировать один вариант download_info.
    
    Args:
        variant: Объект варианта скачивания
        client: Клиент Яндекс.Музыки для получения заголовков авторизации
        
    Returns:
        Словарь с информацией о варианте
    """
    variant_info = {}
    
    # Логируем все атрибуты объекта
    logger.info("   Атрибуты объекта:")
    if hasattr(variant, "__dict__"):
        for attr_name, attr_value in variant.__dict__.items():
            # Ограничиваем длину вывода для длинных значений
            display_value = str(attr_value)
            if len(display_value) > 200:
                display_value = display_value[:200] + "..."
            logger.info(f"     {attr_name}: {display_value}")
            variant_info[attr_name] = str(attr_value) if not isinstance(attr_value, (str, int, float, bool, type(None))) else attr_value
    
    # Также проверяем dir() для всех доступных методов и атрибутов
    logger.info("   Доступные методы и атрибуты (dir):")
    all_attrs = dir(variant)
    relevant_attrs = [attr for attr in all_attrs if not attr.startswith('_')]
    logger.info(f"     {', '.join(relevant_attrs[:20])}...")  # Показываем первые 20
    
    # Пробуем получить URL для скачивания/стриминга
    download_url = None
    
    # ПРИОРИТЕТ 1: Пробуем получить через метод get_direct_link() (это правильный способ)
    if hasattr(variant, "get_direct_link"):
        try:
            logger.info("   🔍 Пробую получить URL через get_direct_link()...")
            download_url = variant.get_direct_link()
            logger.info(f"   ✅ URL получен через get_direct_link()")
            logger.info(f"      Длина URL: {len(download_url)} символов")
            logger.info(f"      Начинается с: {download_url[:50]}...")
            
            # Проверяем, не является ли это XML (как в случае пользователя)
            if download_url.startswith("<?xml") or download_url.startswith("<download-info>"):
                logger.warning("   ⚠️  get_direct_link() вернул XML вместо URL!")
                logger.warning("   💡 Это означает, что нужно обработать XML для получения реального URL")
                # Пробуем извлечь URL из XML или построить его из host и path
                download_url = _extract_url_from_xml_or_build(variant, download_url)
            elif download_url.startswith("http://") or download_url.startswith("https://"):
                logger.info("   ✅ Это похоже на валидный HTTP URL")
            else:
                logger.warning(f"   ⚠️  Неожиданный формат URL: начинается с '{download_url[:20]}...'")
        except Exception as e:
            logger.warning(f"   ⚠️  Ошибка при вызове get_direct_link(): {e}")
            logger.debug(f"      Детали ошибки: {type(e).__name__}: {str(e)}", exc_info=True)
    
    # ПРИОРИТЕТ 2: Если get_direct_link() не сработал, пробуем найти URL в атрибутах
    if not download_url:
        logger.info("   🔍 get_direct_link() не вернул URL, ищу в атрибутах...")
        url_attributes = ["download_info_url", "url", "download_url", "direct_link", "link", "src", "uri"]
        for attr in url_attributes:
            if hasattr(variant, attr):
                url_value = getattr(variant, attr)
                if url_value and isinstance(url_value, str):
                    download_url = url_value
                    logger.info(f"   ✅ Найден URL в атрибуте '{attr}': {download_url[:100]}...")
                    break
    
    # ПРИОРИТЕТ 3: Если URL все еще не найден, пробуем построить из host и path
    if not download_url:
        logger.info("   🔍 URL не найден в атрибутах, пробую построить из host и path...")
        host = getattr(variant, "host", None)
        path = getattr(variant, "path", None)
        if host and path:
            # Строим URL из host и path
            if not host.startswith("http"):
                host = f"https://{host}"
            download_url = f"{host}{path}"
            logger.info(f"   ✅ URL построен из host и path: {download_url[:100]}...")
    
    variant_info["download_url"] = download_url
    
    # Если URL найден, проверяем его на возможность стриминга
    if download_url:
        streaming_check = _check_streaming_capability(download_url, client)
        variant_info["streaming_check"] = streaming_check
        logger.info("   " + "=" * 56)
        logger.info(f"   🔍 ПРОВЕРКА СТРИМИНГА:")
        logger.info(f"      URL: {download_url}")
        logger.info(f"      Поддерживает Range Requests: {streaming_check.get('supports_range', 'N/A')}")
        logger.info(f"      Content-Type: {streaming_check.get('content_type', 'N/A')}")
        logger.info(f"      Content-Length: {streaming_check.get('content_length', 'N/A')}")
        logger.info(f"      Accept-Ranges: {streaming_check.get('accept_ranges', 'N/A')}")
        logger.info(f"      ✅ Подходит для стриминга: {streaming_check.get('suitable_for_streaming', False)}")
        
        # Выводим информацию о проблемах, если они есть
        if "issue" in streaming_check:
            logger.warning(f"      {streaming_check['issue']}")
        
        # Дополнительная информация в зависимости от Content-Type
        content_type = streaming_check.get('content_type', '')
        if content_type == 'application/octet-stream':
            logger.warning("      ⚠️  ВАЖНО: Content-Type = application/octet-stream")
            logger.warning("         Браузер будет скачивать файл вместо воспроизведения!")
            logger.info("      💡 РЕШЕНИЯ:")
            logger.info("         1. Использовать HTML5 <audio> элемент с type='audio/mpeg'")
            logger.info("         2. Использовать прокси-сервер для установки правильного Content-Type")
            logger.info("         3. Использовать Web App с проксированием через бота")
        elif content_type.startswith('audio/'):
            logger.info(f"      ✅ Content-Type правильный: {content_type}")
            logger.info(f"      💡 Тест в браузере: Вставьте URL в адресную строку браузера")
            logger.info(f"         Если откроется плеер и начнется воспроизведение - ссылка подходит для стриминга!")
        else:
            logger.warning(f"      ⚠️  Неожиданный Content-Type: {content_type}")
    else:
        logger.warning("   ⚠️  URL для скачивания не найден")
        variant_info["streaming_check"] = {"error": "URL не найден"}
    
    return variant_info


def _extract_url_from_xml_or_build(variant: Any, xml_content: str) -> Optional[str]:
    """
    Извлечь URL из XML или построить его из атрибутов объекта variant.
    
    Args:
        variant: Объект варианта скачивания
        xml_content: XML содержимое (если get_direct_link вернул XML)
        
    Returns:
        URL или None, если не удалось построить
    """
    try:
        # Пробуем извлечь host и path из атрибутов объекта
        host = getattr(variant, "host", None)
        path = getattr(variant, "path", None)
        
        if host and path:
            # Строим URL
            if not host.startswith("http"):
                host = f"https://{host}"
            url = f"{host}{path}"
            logger.info(f"   ✅ URL построен из атрибутов: {url[:100]}...")
            return url
        
        # Если не получилось из атрибутов, пробуем распарсить XML
        if xml_content and "<download-info>" in xml_content:
            try:
                root = ET.fromstring(xml_content)
                host_elem = root.find("host")
                path_elem = root.find("path")
                
                if host_elem is not None and path_elem is not None:
                    host = host_elem.text
                    path = path_elem.text
                    if host and path:
                        if not host.startswith("http"):
                            host = f"https://{host}"
                        url = f"{host}{path}"
                        logger.info(f"   ✅ URL извлечен из XML: {url[:100]}...")
                        return url
            except ET.ParseError as e:
                logger.warning(f"   ⚠️  Ошибка парсинга XML: {e}")
        
        logger.warning("   ⚠️  Не удалось построить URL из XML или атрибутов")
        return None
    except Exception as e:
        logger.warning(f"   ⚠️  Ошибка при извлечении URL: {e}")
        return None


def _check_streaming_capability(url: str, client: Client) -> Dict[str, Any]:
    """
    Проверить, подходит ли URL для стриминга.
    
    Проверяет:
    - Поддержку HTTP Range Requests (Accept-Ranges: bytes)
    - Content-Type (должен быть audio/*)
    - Размер файла (Content-Length)
    
    Args:
        url: URL для проверки
        client: Клиент Яндекс.Музыки для получения заголовков авторизации
        
    Returns:
        Словарь с результатами проверки
    """
    result = {
        "url": url,
        "supports_range": False,
        "content_type": None,
        "content_length": None,
        "accept_ranges": None,
        "suitable_for_streaming": False
    }
    
    try:
        # Получаем заголовки авторизации из клиента
        headers = {}
        if hasattr(client, "_request") and hasattr(client._request, "headers"):
            headers = client._request.headers.copy()
        
        # Делаем HEAD запрос для проверки заголовков (не скачиваем файл)
        logger.debug(f"Выполняю HEAD запрос к: {url[:80]}...")
        response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        
        result["status_code"] = response.status_code
        result["content_type"] = response.headers.get("Content-Type", "")
        result["content_length"] = response.headers.get("Content-Length")
        result["accept_ranges"] = response.headers.get("Accept-Ranges", "")
        
        # Проверяем поддержку Range Requests
        if result["accept_ranges"].lower() == "bytes":
            result["supports_range"] = True
        
        # Проверяем Content-Type
        is_audio = result["content_type"].startswith("audio/") if result["content_type"] else False
        
        # Определяем, подходит ли для стриминга
        # Критерии:
        # 1. Поддержка Range Requests (можно запрашивать части файла)
        # 2. Content-Type указывает на аудио
        # 3. Статус код 200 (успешный запрос)
        result["suitable_for_streaming"] = (
            result["supports_range"] and
            is_audio and
            response.status_code == 200
        )
        
        # Дополнительная информация о проблемах
        if result["supports_range"] and not is_audio:
            result["issue"] = (
                f"⚠️  ПРОБЛЕМА: Content-Type = '{result['content_type']}' вместо 'audio/*'. "
                f"Браузер будет скачивать файл вместо воспроизведения. "
                f"Возможные решения: использовать HTML5 <audio> с явным указанием типа, "
                f"или прокси-сервер, который установит правильный Content-Type."
            )
        elif not result["supports_range"]:
            result["issue"] = (
                f"⚠️  ПРОБЛЕМА: Не поддерживаются Range Requests. "
                f"Стриминг может быть невозможен или неэффективен."
            )
        
        logger.debug(f"Результат проверки: {result}")
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Ошибка при проверке URL: {e}")
        result["error"] = str(e)
    except Exception as e:
        logger.warning(f"Неожиданная ошибка при проверке URL: {e}")
        result["error"] = str(e)
    
    return result


def investigate_streaming_range(
    tracks: List,
    start_idx: int,
    end_idx: int,
    client: Client
):
    """
    Исследовать возможности стриминга для диапазона треков.
    
    Args:
        tracks: Список треков
        start_idx: Начальный индекс (1-based, включительно)
        end_idx: Конечный индекс (1-based, включительно)
        client: Клиент Яндекс.Музыки
    """
    total_tracks = len(tracks)
    
    # Валидация индексов
    if start_idx < 1:
        start_idx = 1
    if end_idx > total_tracks:
        end_idx = total_tracks
    if start_idx > end_idx:
        print("❌ Начальный индекс больше конечного.")
        return
    
    # Конвертируем в 0-based индексы
    start_0 = start_idx - 1
    end_0 = end_idx
    
    tracks_to_investigate = tracks[start_0:end_0]
    
    print(f"\n🔍 Будет исследовано: {len(tracks_to_investigate)} треков (с {start_idx} по {end_idx})")
    print("=" * 60)
    
    # Исследуем треки
    investigated = 0
    failed = 0
    suitable_for_streaming = 0
    
    for i, track_item in enumerate(tracks_to_investigate, start=start_idx):
        print(f"\n[{i}/{total_tracks}] ", end="")
        
        info = investigate_streaming_info(track_item, client)
        
        if info:
            investigated += 1
            # Проверяем, есть ли хотя бы один вариант, подходящий для стриминга
            if "variants" in info:
                for variant in info["variants"]:
                    streaming_check = variant.get("streaming_check", {})
                    if streaming_check.get("suitable_for_streaming", False):
                        suitable_for_streaming += 1
                        break
        else:
            failed += 1
    
    print(f"\n\n✅ Готово!")
    print(f"📊 Исследовано: {investigated}")
    print(f"✅ Подходит для стриминга: {suitable_for_streaming}")
    print(f"❌ Ошибок: {failed}")


def download_tracks_range(
    tracks: List,
    start_idx: int,
    end_idx: int,
    cache_folder: Path = DEFAULT_CACHE_FOLDER
):
    """
    Скачать диапазон треков из списка.
    
    Args:
        tracks: Список треков
        start_idx: Начальный индекс (1-based, включительно)
        end_idx: Конечный индекс (1-based, включительно)
        cache_folder: Папка для кэширования
    """
    total_tracks = len(tracks)
    
    # Валидация индексов
    if start_idx < 1:
        start_idx = 1
    if end_idx > total_tracks:
        end_idx = total_tracks
    if start_idx > end_idx:
        print("❌ Начальный индекс больше конечного.")
        return
    
    # Конвертируем в 0-based индексы
    start_0 = start_idx - 1
    end_0 = end_idx
    
    tracks_to_download = tracks[start_0:end_0]
    
    print(f"\n⬇️  Будет скачано: {len(tracks_to_download)} треков (с {start_idx} по {end_idx})")
    print(f"📁 Папка для скачивания: {cache_folder}\n")
    
    # Создаем папку для кэша
    cache_folder.mkdir(parents=True, exist_ok=True)
    
    # Скачиваем треки
    downloaded = 0
    failed = 0
    
    for i, track_item in enumerate(tracks_to_download, start=start_idx):
        print(f"\n[{i}/{total_tracks}] ", end="")
        
        file_path = download_track(track_item, cache_folder)
        
        if file_path:
            downloaded += 1
        else:
            failed += 1
    
    print(f"\n\n✅ Готово!")
    print(f"📊 Скачано: {downloaded}")
    print(f"❌ Ошибок: {failed}")
    print(f"📁 Файлы сохранены в: {cache_folder}")


def main():
    """Главная функция."""
    # Проверяем аргументы командной строки
    streaming_mode = "--streaming" in sys.argv or "-s" in sys.argv
    
    print("=" * 60)
    if streaming_mode:
        print("🔍 Тестовый скрипт для исследования стриминга треков")
    else:
        print("🎵 Тестовый скрипт для скачивания треков из плейлиста")
    print("=" * 60)
    
    if streaming_mode:
        print("\n💡 РЕЖИМ ИССЛЕДОВАНИЯ СТРИМИНГА")
        print("   Этот режим исследует возможности стриминга треков")
        print("   через метод get_download_info() API Яндекс.Музыки")
        print("=" * 60)
    
    # Получаем токен
    token = get_token()
    if not token:
        print("❌ Не удалось получить токен.")
        sys.exit(1)
    
    # Инициализируем клиент
    print("\n🔐 Инициализация клиента Яндекс.Музыки...")
    try:
        client = Client(token, report_unknown_fields=False).init()
        print(f"✅ Привет, {client.me.account.first_name}!")
    except Exception as e:
        logger.error(f"Ошибка инициализации клиента: {e}")
        print(f"❌ Ошибка инициализации клиента: {e}")
        print("💡 Проверьте правильность токена.")
        sys.exit(1)
    
    try:
        # Получаем список плейлистов
        playlists = list_playlists(client)
        
        if not playlists:
            print("\n💡 Создайте плейлист в Яндекс.Музыке для тестирования.")
            return
        
        # Выбираем плейлист
        print("\n" + "=" * 60)
        choice = input("\n👉 Введите номер плейлиста (или 'q' для выхода): ").strip()
        
        if choice.lower() == 'q':
            print("👋 До свидания!")
            return
        
        playlist_index = int(choice) - 1
        
        if playlist_index < 0 or playlist_index >= len(playlists):
            print("❌ Неверный номер плейлиста.")
            return
        
        selected_playlist = playlists[playlist_index]
        
        # Показываем треки в плейлисте
        tracks = show_playlist_tracks(selected_playlist)
        
        if not tracks:
            return
        
        # Выбираем диапазон
        print("\n" + "=" * 60)
        if streaming_mode:
            print("\n🔍 Выберите диапазон треков для исследования стриминга:")
        else:
            print("\n📥 Выберите диапазон треков для скачивания:")
        
        start_input = input(f"👉 Начальный трек (1-{len(tracks)}, Enter = 1): ").strip()
        start_idx = int(start_input) if start_input else 1
        
        end_input = input(f"👉 Конечный трек (1-{len(tracks)}, Enter = {len(tracks)}): ").strip()
        end_idx = int(end_input) if end_input else len(tracks)
        
        # Выполняем действие в зависимости от режима
        if streaming_mode:
            investigate_streaming_range(tracks, start_idx, end_idx, client)
        else:
            download_tracks_range(tracks, start_idx, end_idx)
        
    except ValueError:
        print("❌ Неверный ввод. Ожидается число.")
    except KeyboardInterrupt:
        print("\n\n👋 Прервано пользователем.")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        print(f"\n❌ Критическая ошибка: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        logger.exception(f"Ошибка при запуске: {e}")
        sys.exit(1)
