"""
Модуль для создания клавиатур Telegram бота.
"""
import os
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu_keyboard(web_app_url: str = None):
    """
    Возвращает клавиатуру главного меню.
    
    Args:
        web_app_url: URL для Mini App (опционально). Если не указан, 
                     берется из переменной окружения MINIAPP_URL.
    """
    keyboard = [
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
    ]
    
    # Кнопка Web App убрана из ReplyKeyboard из-за проблем с initData в Telegram Desktop
    # Используйте inline-кнопку через get_miniapp_inline_keyboard()
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
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


def get_miniapp_inline_keyboard(web_app_url: str = None, button_text: str = "🎵 Открыть плеер"):
    """
    Возвращает inline-клавиатуру с кнопкой Web App.
    Inline-кнопки более надежно передают initData в Telegram Desktop.
    
    Args:
        web_app_url: URL для Mini App (опционально). Если не указан, 
                     берется из переменной окружения MINIAPP_URL.
        button_text: Текст кнопки (по умолчанию "🎵 Открыть плеер").
    """
    if web_app_url is None:
        web_app_url = os.getenv("MINIAPP_URL")
    
    if not web_app_url:
        return None
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=button_text,
                    web_app=WebAppInfo(url=web_app_url)
                )
            ]
        ]
    )

