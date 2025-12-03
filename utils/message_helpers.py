"""
Утилиты для унифицированной отправки сообщений в Telegram боте.
"""
from typing import Optional, Union
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup

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


# === Функции для унифицированной отправки сообщений ===

async def send_message(
    message: Message,
    text: str,
    reply_markup: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup]] = None,
    use_main_menu: bool = False
) -> Message:
    """
    Унифицированная отправка сообщения через Message.
    
    Args:
        message: Объект Message из aiogram
        text: Текст сообщения
        reply_markup: Клавиатура (опционально)
        use_main_menu: Если True, использует главное меню как reply_markup
        
    Returns:
        Отправленное сообщение
    """
    if use_main_menu:
        from handlers.keyboards import get_main_menu_keyboard
        reply_markup = get_main_menu_keyboard()
    
    return await message.answer(
        text,
        reply_markup=reply_markup
    )


async def edit_message(
    query: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None
) -> Message:
    """
    Редактирование сообщения через callback query.
    
    Args:
        query: CallbackQuery из aiogram
        text: Новый текст сообщения
        reply_markup: Клавиатура (опционально)
        
    Returns:
        Отредактированное сообщение
    """
    return await query.message.edit_text(
        text,
        reply_markup=reply_markup
    )


async def reply_to_message(
    message: Message,
    text: str,
    reply_markup: Optional[Union[InlineKeyboardMarkup, ReplyKeyboardMarkup]] = None,
    use_main_menu: bool = False
) -> Message:
    """
    Отправка ответа на сообщение.
    
    Args:
        message: Объект Message из aiogram
        text: Текст сообщения
        reply_markup: Клавиатура (опционально)
        use_main_menu: Если True, использует главное меню как reply_markup
        
    Returns:
        Отправленное сообщение
    """
    if use_main_menu:
        from handlers.keyboards import get_main_menu_keyboard
        reply_markup = get_main_menu_keyboard()
    
    return await message.answer(
        text,
        reply_markup=reply_markup
    )


# === Вспомогательные функции для частых случаев ===

async def send_no_active_playlist(message: Message, use_main_menu: bool = True) -> Message:
    """Отправка сообщения об отсутствии активного плейлиста."""
    return await send_message(message, NO_ACTIVE_PLAYLIST, use_main_menu=use_main_menu)


async def send_playlist_not_found(query: Optional[CallbackQuery] = None, message: Optional[Message] = None) -> Optional[Message]:
    """Отправка сообщения о том, что плейлист не найден."""
    if query:
        return await edit_message(query, PLAYLIST_NOT_FOUND, reply_markup=None)
    elif message:
        return await send_message(message, PLAYLIST_NOT_FOUND)
    return None


async def send_no_access(query: Optional[CallbackQuery] = None, message: Optional[Message] = None) -> Optional[Message]:
    """Отправка сообщения об отсутствии доступа."""
    if query:
        return await edit_message(query, NO_PLAYLIST_ACCESS, reply_markup=None)
    elif message:
        return await send_message(message, NO_PLAYLIST_ACCESS)
    return None


async def send_only_creator_can_edit(query: Optional[CallbackQuery] = None, message: Optional[Message] = None) -> Optional[Message]:
    """Отправка сообщения о том, что только создатель может редактировать."""
    if query:
        return await edit_message(query, ONLY_CREATOR_CAN_EDIT, reply_markup=None)
    elif message:
        return await send_message(message, ONLY_CREATOR_CAN_EDIT)
    return None


async def send_only_creator_can_delete(query: Optional[CallbackQuery] = None, message: Optional[Message] = None) -> Optional[Message]:
    """Отправка сообщения о том, что только создатель может удалять."""
    if query:
        return await edit_message(query, ONLY_CREATOR_CAN_DELETE, reply_markup=None)
    elif message:
        return await send_message(message, ONLY_CREATOR_CAN_DELETE)
    return None

