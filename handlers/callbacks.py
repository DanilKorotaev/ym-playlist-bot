"""
Обработчики callback query для Telegram бота.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from database import DatabaseInterface
from utils.context import UserContextManager
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
        """Обработка нажатий на inline-кнопки."""
        query = update.callback_query
        query.answer()
        
        telegram_id = query.from_user.id
        data = query.data
        
        if data.startswith("select_playlist_"):
            playlist_id = int(data.split("_")[-1])
            playlist = self.db.get_playlist(playlist_id)
            if not playlist:
                query.edit_message_text(
                    "❌ Плейлист не найден.",
                    reply_markup=None
                )
                return
            
            # Проверяем доступ
            if not self.db.check_playlist_access(playlist_id, telegram_id):
                query.edit_message_text(
                    "❌ У вас нет доступа к этому плейлисту.",
                    reply_markup=None
                )
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
        # edit_name_ и delete_track_ обрабатываются через ConversationHandler entry points
        elif data.startswith("delete_playlist_"):
            playlist_id = int(data.split("_")[-1])
            playlist = self.db.get_playlist(playlist_id)
            if not playlist:
                query.edit_message_text("❌ Плейлист не найден.")
                return
            
            if not self.db.is_playlist_creator(playlist_id, telegram_id):
                query.edit_message_text("❌ Только создатель плейлиста может удалять его.")
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
        elif data.startswith("edit_playlist_"):
            playlist_id = int(data.split("_")[-1])
            playlist = self.db.get_playlist(playlist_id)
            if not playlist:
                query.edit_message_text("❌ Плейлист не найден.")
                return
            
            if not self.db.is_playlist_creator(playlist_id, telegram_id):
                query.edit_message_text("❌ Только создатель плейлиста может редактировать его.")
                return
            
            title = playlist.get("title") or "Плейлист"
            insert_position = playlist.get("insert_position", "end")
            position_text = "в начало" if insert_position == "start" else "в конец"
            
            # Создаем клавиатуру с кнопками редактирования
            keyboard = [
                [InlineKeyboardButton("✏️ Изменить имя", callback_data=f"edit_name_{playlist_id}")],
                [InlineKeyboardButton("🖼️ Изменить/установить картинку", callback_data=f"set_cover_{playlist_id}")],
                [InlineKeyboardButton(f"📍 Добавление треков: {position_text}", callback_data=f"toggle_insert_position_{playlist_id}")],
                [InlineKeyboardButton("🗑️ Удалить плейлист", callback_data=f"delete_playlist_{playlist_id}")],
                [InlineKeyboardButton("🗑️ Удалить трек", callback_data=f"delete_track_{playlist_id}")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            query.message.reply_text(
                f"✏️ Редактирование плейлиста «{title}»\n\n"
                f"Выберите действие:",
                reply_markup=reply_markup
            )
        elif data.startswith("toggle_insert_position_"):
            playlist_id = int(data.split("_")[-1])
            playlist = self.db.get_playlist(playlist_id)
            if not playlist:
                query.edit_message_text("❌ Плейлист не найден.")
                return
            
            if not self.db.is_playlist_creator(playlist_id, telegram_id):
                query.edit_message_text("❌ Только создатель плейлиста может редактировать его.")
                return
            
            # Переключаем insert_position
            current_position = playlist.get("insert_position", "end")
            new_position = "start" if current_position == "end" else "end"
            position_text = "в начало" if new_position == "start" else "в конец"
            
            # Обновляем в БД
            self.db.update_playlist(playlist_id, insert_position=new_position)
            self.db.log_action(telegram_id, "playlist_insert_position_changed", playlist_id, f"position={new_position}")
            
            # Обновляем сообщение с меню редактирования
            title = playlist.get("title") or "Плейлист"
            keyboard = [
                [InlineKeyboardButton("✏️ Изменить имя", callback_data=f"edit_name_{playlist_id}")],
                [InlineKeyboardButton("🖼️ Изменить/установить картинку", callback_data=f"set_cover_{playlist_id}")],
                [InlineKeyboardButton(f"📍 Добавление треков: {position_text}", callback_data=f"toggle_insert_position_{playlist_id}")],
                [InlineKeyboardButton("🗑️ Удалить плейлист", callback_data=f"delete_playlist_{playlist_id}")],
                [InlineKeyboardButton("🗑️ Удалить трек", callback_data=f"delete_track_{playlist_id}")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            query.edit_message_text(
                f"✏️ Редактирование плейлиста «{title}»\n\n"
                f"✅ Настройка изменена: треки теперь добавляются {position_text}.\n\n"
                f"Выберите действие:",
                reply_markup=reply_markup
            )

