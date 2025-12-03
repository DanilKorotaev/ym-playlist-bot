"""
Модуль для создания клавиатур Telegram бота.
"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu_keyboard():
    """Возвращает клавиатуру главного меню."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📁 Мои плейлисты"),
                KeyboardButton(text="📂 Общие плейлисты")
            ],
            [
                KeyboardButton(text="➕ Создать плейлист"),
                KeyboardButton(text="📋 Список треков")
            ],
            [
                KeyboardButton(text="ℹ️ Информация"),
                KeyboardButton(text="🏠 Главное меню")
            ]
        ],
        resize_keyboard=True
    )


def get_cancel_keyboard():
    """Возвращает клавиатуру с кнопкой отмены."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )

