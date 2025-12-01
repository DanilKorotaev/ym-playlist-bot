"""
Утилиты для бота.
"""

from .context import UserContextManager
from .message_helpers import (
    send_message,
    edit_message,
    reply_to_message,
    send_no_active_playlist,
    send_playlist_not_found,
    send_no_access,
    send_only_creator_can_edit,
    send_only_creator_can_delete
)
# Импортируем константы из отдельного модуля
from .messages import (
    NO_ACTIVE_PLAYLIST,
    NO_ACTIVE_PLAYLIST_SELECT,
    NO_ACTIVE_PLAYLIST_SHORT,
    PLAYLIST_NOT_FOUND,
    PLAYLIST_NOT_FOUND_ERROR,
    NO_PLAYLIST_ACCESS,
    NO_ADD_PERMISSION,
    ONLY_CREATOR_CAN_DELETE,
    ONLY_CREATOR_CAN_EDIT,
    ONLY_CREATOR_CAN_CHANGE_NAME,
    ONLY_CREATOR_CAN_CHANGE_COVER,
    GENERAL_ERROR,
    LOADING_PLAYLIST,
    LOADING_ALBUM,
    LOADING_TRACK,
    CREATING_PLAYLIST
)

__all__ = [
    "UserContextManager",
    "send_message",
    "edit_message",
    "reply_to_message",
    "send_no_active_playlist",
    "send_playlist_not_found",
    "send_no_access",
    "send_only_creator_can_edit",
    "send_only_creator_can_delete",
    # Константы
    "NO_ACTIVE_PLAYLIST",
    "NO_ACTIVE_PLAYLIST_SELECT",
    "NO_ACTIVE_PLAYLIST_SHORT",
    "PLAYLIST_NOT_FOUND",
    "PLAYLIST_NOT_FOUND_ERROR",
    "NO_PLAYLIST_ACCESS",
    "NO_ADD_PERMISSION",
    "ONLY_CREATOR_CAN_DELETE",
    "ONLY_CREATOR_CAN_EDIT",
    "ONLY_CREATOR_CAN_CHANGE_NAME",
    "ONLY_CREATOR_CAN_CHANGE_COVER",
    "GENERAL_ERROR",
    "LOADING_PLAYLIST",
    "LOADING_ALBUM",
    "LOADING_TRACK",
    "CREATING_PLAYLIST"
]

