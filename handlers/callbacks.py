"""
Обработчики callback query для Telegram бота.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import CallbackContext

from database import DatabaseInterface
from utils.context import UserContextManager
from utils.message_helpers import (
    edit_message,
    reply_to_message,
    PLAYLIST_NOT_FOUND,
    NO_PLAYLIST_ACCESS,
    ONLY_CREATOR_CAN_DELETE,
    ONLY_CREATOR_CAN_EDIT
)
from services.payment_service import PaymentService
from .keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)


class CallbackHandlers:
    """Класс с обработчиками callback query."""
    
    def __init__(
        self,
        db: DatabaseInterface,
        context_manager: UserContextManager
    ):
        """
        Инициализация обработчиков.
        
        Args:
            db: Интерфейс базы данных
            context_manager: Менеджер контекста пользователей
        """
        self.db = db
        self.context_manager = context_manager
    
    def button_callback(self, update: Update, context: CallbackContext):
        """
        Роутер для обработки нажатий на inline-кнопки.
        
        Перенаправляет вызовы на соответствующие методы-обработчики
        в зависимости от префикса callback_data.
        """
        query = update.callback_query
        query.answer()
        
        telegram_id = query.from_user.id
        data = query.data
        
        if data.startswith("select_playlist_"):
            playlist_id = int(data.split("_")[-1])
            self._handle_select_playlist(query, playlist_id, telegram_id)
        elif data.startswith("delete_playlist_"):
            playlist_id = int(data.split("_")[-1])
            self._handle_delete_playlist(query, playlist_id, telegram_id)
        elif data.startswith("edit_playlist_"):
            playlist_id = int(data.split("_")[-1])
            self._handle_edit_playlist(query, playlist_id, telegram_id)
        elif data.startswith("toggle_insert_position_"):
            playlist_id = int(data.split("_")[-1])
            self._handle_toggle_insert_position(query, playlist_id, telegram_id)
        elif data.startswith("buy_"):
            plan_id = data.replace("buy_", "")
            self._handle_buy_payment(query, context, telegram_id, plan_id)
        elif data == "cancel_payment":
            self._handle_cancel_payment(query)
        # edit_name_ и delete_track_ обрабатываются через ConversationHandler entry points
    
    def _handle_select_playlist(self, query, playlist_id: int, telegram_id: int):
        """Обработка выбора плейлиста."""
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            edit_message(query, PLAYLIST_NOT_FOUND, reply_markup=None)
            return
        
        # Проверяем доступ
        if not self.db.check_playlist_access(playlist_id, telegram_id):
            edit_message(query, NO_PLAYLIST_ACCESS, reply_markup=None)
            return
        
        # Устанавливаем как активный
        self.context_manager.set_active_playlist(telegram_id, playlist_id)
        
        title = playlist.get("title") or "Плейлист"
        is_creator = self.db.is_playlist_creator(playlist_id, telegram_id)
        status = "Создатель" if is_creator else "Участник"
        
        query.edit_message_text(
            f"✅ Выбран плейлист: «{title}»\n"
            f"👤 Статус: {status}\n\n"
            f"💡 Теперь отправляйте ссылки на треки, альбомы или плейлисты, чтобы добавить их в этот плейлист."
        )
    
    def _handle_delete_playlist(self, query, playlist_id: int, telegram_id: int):
        """Обработка удаления плейлиста."""
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            edit_message(query, PLAYLIST_NOT_FOUND)
            return
        
        if not self.db.is_playlist_creator(playlist_id, telegram_id):
            edit_message(query, ONLY_CREATOR_CAN_DELETE)
            return
        
        title = playlist.get("title") or "плейлист"
        self.db.delete_playlist(playlist_id)
        
        # Удаляем из контекста
        self.context_manager.clear_active_playlist(telegram_id)
        
        query.edit_message_text(
            f"✅ Плейлист «{title}» удален из базы данных бота.\n\n"
            f"💡 Плейлист остался в Яндекс.Музыке, но бот больше не имеет к нему доступа.",
            reply_markup=None
        )
        self.db.log_action(telegram_id, "playlist_deleted", playlist_id, None)
    
    def _handle_edit_playlist(self, query, playlist_id: int, telegram_id: int):
        """Обработка открытия меню редактирования плейлиста."""
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            edit_message(query, PLAYLIST_NOT_FOUND)
            return
        
        if not self.db.is_playlist_creator(playlist_id, telegram_id):
            edit_message(query, ONLY_CREATOR_CAN_EDIT)
            return
        
        title = playlist.get("title") or "Плейлист"
        reply_markup = self._create_edit_playlist_keyboard(playlist_id, playlist)
        
        reply_to_message(
            query.message,
            f"✏️ Редактирование плейлиста «{title}»\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup
        )
    
    def _handle_toggle_insert_position(self, query, playlist_id: int, telegram_id: int):
        """Обработка переключения позиции вставки треков."""
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            edit_message(query, PLAYLIST_NOT_FOUND)
            return
        
        if not self.db.is_playlist_creator(playlist_id, telegram_id):
            edit_message(query, ONLY_CREATOR_CAN_EDIT)
            return
        
        # Переключаем insert_position
        current_position = playlist.get("insert_position", "end")
        new_position = "start" if current_position == "end" else "end"
        
        # Обновляем в БД
        self.db.update_playlist(playlist_id, insert_position=new_position)
        self.db.log_action(telegram_id, "playlist_insert_position_changed", playlist_id, f"position={new_position}")
        
        # Обновляем плейлист для получения актуальных данных
        playlist["insert_position"] = new_position
        position_text = "в начало" if new_position == "start" else "в конец"
        
        # Обновляем сообщение с меню редактирования
        title = playlist.get("title") or "Плейлист"
        reply_markup = self._create_edit_playlist_keyboard(playlist_id, playlist)
        
        query.edit_message_text(
            f"✏️ Редактирование плейлиста «{title}»\n\n"
            f"✅ Настройка изменена: треки теперь добавляются {position_text}.\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup
        )
    
    def _handle_buy_payment(self, query, context: CallbackContext, telegram_id: int, plan_id: str):
        """Обработка покупки подписки."""
        payment_service = PaymentService(self.db)
        payment_data = payment_service.create_payment(telegram_id, plan_id)
        
        if not payment_data:
            query.answer("Ошибка при создании платежа", show_alert=True)
            return
        
        plan = payment_service.get_available_plans()[plan_id]
        
        # Создаем инвойс
        try:
            invoice_link = context.bot.create_invoice_link(
                title=f"Расширенный лимит: {plan['name']}",
                description=f"Увеличьте лимит плейлистов до {plan['name']}",
                payload=payment_data['payload'],
                provider_token="",  # Не требуется для Stars
                currency="XTR",  # Telegram Stars
                prices=[LabeledPrice(label=plan['name'], amount=plan['stars'])]
            )
            
            # Отправляем сообщение с кнопкой оплаты
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("💳 Оплатить", url=invoice_link)
            ], [
                InlineKeyboardButton("❌ Отмена", callback_data="cancel_payment")
            ]])
            
            reply_to_message(
                query.message,
                f"💳 Оплата: {plan['name']}\n\n"
                f"💰 Стоимость: {plan['stars']} Stars\n\n"
                f"Нажмите кнопку ниже для оплаты:",
                reply_markup=keyboard
            )
            
            query.answer()
        except Exception as e:
            logger.error(f"Ошибка при создании инвойса: {e}")
            query.answer("Ошибка при создании платежа", show_alert=True)
    
    def _handle_cancel_payment(self, query):
        """Обработка отмены покупки."""
        query.answer()
        reply_to_message(
            query.message,
            "❌ Покупка отменена.",
            use_main_menu=True
        )
    
    def _create_edit_playlist_keyboard(self, playlist_id: int, playlist: dict) -> InlineKeyboardMarkup:
        """
        Создает клавиатуру для редактирования плейлиста.
        
        Args:
            playlist_id: ID плейлиста
            playlist: Словарь с данными плейлиста
            
        Returns:
            InlineKeyboardMarkup с кнопками редактирования
        """
        insert_position = playlist.get("insert_position", "end")
        position_text = "в начало" if insert_position == "start" else "в конец"
        
        keyboard = [
            [InlineKeyboardButton("✏️ Изменить имя", callback_data=f"edit_name_{playlist_id}")],
            [InlineKeyboardButton("🖼️ Изменить/установить картинку", callback_data=f"set_cover_{playlist_id}")],
            [InlineKeyboardButton(f"📍 Добавление треков: {position_text}", callback_data=f"toggle_insert_position_{playlist_id}")],
            [InlineKeyboardButton("🗑️ Удалить плейлист", callback_data=f"delete_playlist_{playlist_id}")],
            [InlineKeyboardButton("🗑️ Удалить трек", callback_data=f"delete_track_{playlist_id}")]
        ]
        
        return InlineKeyboardMarkup(keyboard)

