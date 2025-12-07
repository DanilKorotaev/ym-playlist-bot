#!/usr/bin/env python3
"""
Тестовый скрипт для скачивания треков из плейлиста.
Работает напрямую с API Яндекс.Музыки, без использования БД.
Основан на примере player.py из yandex-music-api.

Использование:
    python test_download_tracks.py
    или
    python test_download_tracks.py --token YOUR_TOKEN
"""
import os
import sys
import re
import time
import logging
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

from yandex_music import Client

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Константы
DEFAULT_CACHE_FOLDER = Path(__file__).resolve().parent.parent / '.YMcache'
MAX_ERRORS = 3


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
    print("=" * 60)
    print("🎵 Тестовый скрипт для скачивания треков из плейлиста")
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
        
        # Выбираем диапазон для скачивания
        print("\n" + "=" * 60)
        print("\n📥 Выберите диапазон треков для скачивания:")
        
        start_input = input(f"👉 Начальный трек (1-{len(tracks)}, Enter = 1): ").strip()
        start_idx = int(start_input) if start_input else 1
        
        end_input = input(f"👉 Конечный трек (1-{len(tracks)}, Enter = {len(tracks)}): ").strip()
        end_idx = int(end_input) if end_input else len(tracks)
        
        # Скачиваем треки
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
