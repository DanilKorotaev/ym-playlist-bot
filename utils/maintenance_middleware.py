"""
Middleware для проверки режима технических работ.
"""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

from utils.maintenance import is_maintenance_mode, get_maintenance_message
from utils.message_helpers import send_message

logger = logging.getLogger(__name__)


class MaintenanceMiddleware(BaseMiddleware):
    """
    Middleware для проверки режима технических работ.
    
    Если режим техработ включен, все запросы (кроме админских) 
    будут перехвачены и возвращать сообщение о техработах.
    """
    
    def __init__(self, admin_ids: list[int] = None):
        """
        Инициализация middleware.
        
        Args:
            admin_ids: Список ID администраторов, которые могут использовать бота даже в режиме техработ
        """
        self.admin_ids = admin_ids or []
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """
        Проверяет режим техработ перед обработкой обновления.
        
        Args:
            handler: Обработчик обновления
            event: Обновление от Telegram
            data: Данные для обработчика
            
        Returns:
            Результат обработки или сообщение о техработах
        """
        # Проверяем, включен ли режим техработ
        if not is_maintenance_mode():
            # Режим техработ выключен - пропускаем обновление дальше
            return await handler(event, data)
        
        # Режим техработ включен
        # Проверяем, является ли пользователь админом
        user_id = None
        message = None
        callback_query = None
        
        # Получаем информацию о пользователе из обновления
        if event.message:
            message = event.message
            user_id = message.from_user.id if message.from_user else None
        elif event.callback_query:
            callback_query = event.callback_query
            user_id = callback_query.from_user.id if callback_query.from_user else None
        elif event.edited_message:
            message = event.edited_message
            user_id = message.from_user.id if message.from_user else None
        elif event.channel_post:
            message = event.channel_post
            user_id = message.from_user.id if message.from_user else None
        
        # Если пользователь - админ, пропускаем обновление
        if user_id and user_id in self.admin_ids:
            logger.debug(f"Пользователь {user_id} является админом, пропускаем обновление в режиме техработ")
            return await handler(event, data)
        
        # Отправляем сообщение о техработах
        maintenance_message = get_maintenance_message()
        
        if message:
            # Это текстовое сообщение или команда
            try:
                await send_message(message, maintenance_message, use_main_menu=False)
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения о техработах: {e}")
        elif callback_query:
            # Это callback query (нажатие на кнопку)
            try:
                await callback_query.answer(maintenance_message, show_alert=True)
            except Exception as e:
                logger.error(f"Ошибка при отправке ответа на callback query о техработах: {e}")
        else:
            # Для других типов обновлений просто логируем
            logger.debug(f"Обновление типа {type(event).__name__} в режиме техработ, пропускаем")
        
        # Прерываем обработку обновления
        return None

