"""
Модуль для создания клавиатур Telegram бота.
"""
import os
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo


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
    ]
    
    # Добавляем кнопку Web App, если URL указан
    if web_app_url is None:
        web_app_url = os.getenv("MINIAPP_URL")
    
    if web_app_url:
        keyboard.append([
            KeyboardButton(
                text="🎵 Открыть плеер",
                web_app=WebAppInfo(url=web_app_url)
            )
        ])
    
    keyboard.append([
        KeyboardButton(text="ℹ️ Информация"),
        KeyboardButton(text="🏠 Главное меню")
    ])
    
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

