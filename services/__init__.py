"""
Модуль с бизнес-логикой приложения.
Все сервисы независимы от Telegram и могут использоваться в консольных скриптах.
"""

from .link_parser import (
    parse_track_link,
    parse_playlist_link,
    parse_album_link,
    parse_share_link,
)

from .yandex_service import YandexService

from .playlist_service import PlaylistService

__all__ = [
    "parse_track_link",
    "parse_playlist_link",
    "parse_album_link",
    "parse_share_link",
    "YandexService",
    "PlaylistService",
]

