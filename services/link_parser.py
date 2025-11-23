"""
Модуль для парсинга ссылок Яндекс.Музыки.
Поддерживает треки, альбомы, плейлисты и токены для шаринга.
"""
import re
from typing import Optional, Tuple, Any


def parse_track_link(link: str) -> Optional[Any]:
    """
    Парсит ссылку на трек Яндекс.Музыки.
    
    Args:
        link: Ссылка на трек или ID трека
        
    Returns:
        ID трека (int или str) или None, если не удалось распарсить
        
    Examples:
        >>> parse_track_link("https://music.yandex.ru/track/123456")
        123456
        >>> parse_track_link("track/123456")
        123456
        >>> parse_track_link("123456")
        123456
    """
    if not link:
        return None
    m = re.search(r"track/(\d+)", link)
    if m:
        return int(m.group(1))
    m = re.search(r"track/([0-9a-fA-F-]{8,})", link)
    if m:
        return m.group(1)
    m = re.match(r"^\d+$", link.strip())
    if m:
        return int(link.strip())
    return None


def parse_playlist_link(link: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Парсит ссылку на плейлист Яндекс.Музыки.
    
    Args:
        link: Ссылка на плейлист
        
    Returns:
        Кортеж (owner, playlist_id) или (None, None), если не удалось распарсить
        
    Examples:
        >>> parse_playlist_link("https://music.yandex.ru/users/user123/playlists/456")
        ('user123', '456')
        >>> parse_playlist_link("https://music.yandex.ru/playlists/456")
        (None, '456')
    """
    if not link:
        return None, None
    m = re.search(r"users/([^/]+)/playlists/([0-9a-fA-F-]+)", link)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"/playlists?/([0-9a-fA-F-]+)", link)
    if m:
        return None, m.group(1)
    return None, None


def parse_album_link(link: str) -> Optional[Any]:
    """
    Парсит ссылку на альбом Яндекс.Музыки.
    
    Args:
        link: Ссылка на альбом или ID альбома
        
    Returns:
        ID альбома (int или str) или None, если не удалось распарсить
        
    Examples:
        >>> parse_album_link("https://music.yandex.ru/album/123456")
        123456
        >>> parse_album_link("album/123456")
        123456
    """
    if not link:
        return None
    m = re.search(r"album/(\d+)", link)
    if m:
        return int(m.group(1))
    m = re.search(r"album/([0-9a-fA-F-]+)", link)
    if m:
        return m.group(1)
    return None


def parse_share_link(link: str) -> Optional[str]:
    """
    Парсит ссылку для шаринга плейлиста или токен.
    
    Args:
        link: Ссылка вида https://t.me/bot?start=TOKEN или просто TOKEN
        
    Returns:
        Токен или None, если не удалось распарсить
        
    Examples:
        >>> parse_share_link("https://t.me/bot?start=abc123")
        'abc123'
        >>> parse_share_link("abc123")
        'abc123'
    """
    if not link:
        return None
    # Если это полная ссылка
    m = re.search(r"[?&]start=([A-Za-z0-9_-]+)", link)
    if m:
        return m.group(1)
    # Если это просто токен (безопасные символы)
    if re.match(r"^[A-Za-z0-9_-]+$", link.strip()):
        return link.strip()
    return None

