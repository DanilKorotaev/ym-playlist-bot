"""
Обработчики команд Telegram бота.
"""
import logging
import os
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

from database import DatabaseInterface
from yandex_client_manager import YandexClientManager
from utils.context import UserContextManager
from services.playlist_service import PlaylistService
from services.yandex_service import YandexService
from services.payment_service import PaymentService
from .keyboards import get_main_menu_keyboard, get_cancel_keyboard

logger = logging.getLogger(__name__)

# Лимит плейлистов на пользователя (можно задать через переменную окружения)
DEFAULT_PLAYLIST_LIMIT = 2
PLAYLIST_LIMIT = int(os.getenv("PLAYLIST_LIMIT", DEFAULT_PLAYLIST_LIMIT))

# FSM States
WAITING_PLAYLIST_NAME = 1
WAITING_TOKEN = 2
WAITING_EDIT_NAME = 3
WAITING_TRACK_NUMBER = 4
WAITING_PLAYLIST_COVER = 5


class CommandHandlers:
    """Класс с обработчиками команд бота."""
    
    def __init__(
        self,
        db: DatabaseInterface,
        client_manager: YandexClientManager,
        context_manager: UserContextManager
    ):
        """
        Инициализация обработчиков.
        
        Args:
            db: Интерфейс базы данных
            client_manager: Менеджер клиентов Яндекс.Музыки
            context_manager: Менеджер контекста пользователей
        """
        self.db = db
        self.client_manager = client_manager
        self.context_manager = context_manager
        self.playlist_service = PlaylistService(db, client_manager)
    
    def start(self, update: Update, context: CallbackContext):
        """Команда /start."""
        telegram_id = update.effective_user.id
        username = update.effective_user.username
        self.db.ensure_user(telegram_id, username)
        
        # Проверяем, есть ли параметр start (для шаринга плейлистов)
        if context.args:
            share_token = context.args[0]
            playlist = self.db.get_playlist_by_share_token(share_token)
            if playlist:
                # Предоставляем доступ к плейлисту
                self.db.grant_playlist_access(playlist["id"], telegram_id, can_add=True)
                # Устанавливаем как активный
                self.context_manager.set_active_playlist(telegram_id, playlist["id"])
                
                update.effective_message.reply_text(
                    f"✅ Вы получили доступ к плейлисту «{playlist.get('title', 'Без названия')}»!\n\n"
                    f"Теперь вы можете добавлять треки в этот плейлист, отправляя ссылки на треки, альбомы или плейлисты.",
                    reply_markup=get_main_menu_keyboard()
                )
                self.db.log_action(telegram_id, "playlist_shared_access", playlist["id"], f"via_token={share_token}")
                return
        
        # Показываем информацию об активном плейлисте, если есть
        active_info = self.context_manager.get_active_playlist_info(telegram_id)
        
        help_text = (
            "Привет! Я бот для управления плейлистами Яндекс.Музыки 🎵\n\n"
        )
        
        if active_info:
            help_text += f"{active_info}\n\n"
        
        help_text += (
            "📋 Основные команды:\n"
            "• Используйте кнопки меню для навигации\n"
            "• Отправьте ссылку на трек/альбом/плейлист, чтобы добавить в активный плейлист\n\n"
            "💡 Совет: Сначала создайте плейлист или получите доступ к существующему!"
        )
        
        update.effective_message.reply_text(
            help_text,
            reply_markup=get_main_menu_keyboard()
        )
        self.db.log_action(telegram_id, "command_start", None, None)
    
    def main_menu(self, update: Update, context: CallbackContext):
        """Главное меню."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        active_info = self.context_manager.get_active_playlist_info(telegram_id)
        text = "🏠 Главное меню\n\n"
        
        if active_info:
            text += f"{active_info}\n\n"
        else:
            text += "⚠️ У вас нет активного плейлиста.\n"
            text += "Создайте новый или получите доступ к существующему.\n\n"
        
        text += "Выберите действие из меню ниже:"
        
        update.effective_message.reply_text(
            text,
            reply_markup=get_main_menu_keyboard()
        )
    
    def create_playlist_start(self, update: Update, context: CallbackContext) -> int:
        """Начало создания плейлиста (FSM)."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        # FSM диалог
        update.effective_message.reply_text(
            "📝 Создание нового плейлиста\n\n"
            "Введите название плейлиста (максимум 100 символов):\n\n"
            "💡 Пример: Моя музыка",
            reply_markup=get_cancel_keyboard()
        )
        return WAITING_PLAYLIST_NAME
    
    def create_playlist_name(self, update: Update, context: CallbackContext) -> int:
        """Обработка названия плейлиста."""
        telegram_id = update.effective_user.id
        title = update.effective_message.text.strip()
        
        # Проверка на отмену
        if title.lower() in ["отмена", "❌ отмена", "/cancel", "/start"]:
            return self.cancel_operation(update, context)
        
        # Валидация
        if not title:
            update.effective_message.reply_text(
                "❌ Название не может быть пустым. Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_PLAYLIST_NAME
        
        if len(title) > 100:
            update.effective_message.reply_text(
                "❌ Название слишком длинное (максимум 100 символов).\n\n"
                "Введите более короткое название:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_PLAYLIST_NAME
        
        # Проверяем лимит плейлистов (с учетом подписки)
        user_limit = self.db.get_user_playlist_limit(telegram_id)
        current_count = self.db.count_user_playlists(telegram_id)
        
        # Проверка лимита
        if user_limit == -1:
            # Unlimited - пропускаем проверку
            pass
        elif current_count >= user_limit:
            # Показываем предложение купить расширенный лимит
            limit_text = "безлимитно" if user_limit == -1 else f"{user_limit} плейлистов"
            update.effective_message.reply_text(
                f"❌ Достигнут лимит плейлистов!\n\n"
                f"📊 У вас уже создано {current_count} из {user_limit} плейлистов.\n\n"
                f"💡 Хотите увеличить лимит? Используйте /buy_limit",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        # Создаем плейлист
        update.effective_message.reply_text("⏳ Создаю плейлист...")
        result = self.client_manager.create_playlist(telegram_id, title)
        
        if result:
            playlist_id = result["id"]
            share_link = self.playlist_service.get_share_link(playlist_id, context.bot.username)
            
            self.context_manager.set_active_playlist(telegram_id, playlist_id)
            
            update.effective_message.reply_text(
                f"✅ Плейлист «{title}» успешно создан!\n\n"
                f"🔗 Ссылка для шаринга:\n{share_link}\n\n"
                f"Отправьте эту ссылку другим пользователям, чтобы они могли добавлять треки в ваш плейлист.",
                reply_markup=get_main_menu_keyboard()
            )
            self.db.log_action(telegram_id, "playlist_created", playlist_id, f"title={title}")
        else:
            update.effective_message.reply_text(
                "❌ Не удалось создать плейлист.\n\n"
                "Возможные причины:\n"
                "• Не установлен токен Яндекс.Музыки\n"
                "• Токен недействителен\n\n"
                "Используйте /set_token для установки своего токена.",
                reply_markup=get_main_menu_keyboard()
            )
        
        return ConversationHandler.END
    
    def my_playlists(self, update: Update, context: CallbackContext):
        """Команда /my_playlists."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        playlists = self.db.get_user_playlists(telegram_id, only_created=True)
        
        # Получаем информацию о лимите (с учетом подписки)
        current_count = len(playlists)
        user_limit = self.db.get_user_playlist_limit(telegram_id)
        limit_text = "∞" if user_limit == -1 else str(user_limit)
        limit_info = f"📊 {current_count}/{limit_text} плейлистов"
        
        if not playlists:
            update.effective_message.reply_text(
                f"📁 У вас пока нет созданных плейлистов.\n\n"
                f"{limit_info}\n\n"
                f"💡 Создайте новый плейлист, используя кнопку «➕ Создать плейлист» или команду /create_playlist",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Получаем активный плейлист
        active_id = self.context_manager.get_active_playlist_id(telegram_id)
        
        lines = [f"📁 Ваши плейлисты:\n{limit_info}\n"]
        keyboard = []
        
        for i, pl in enumerate(playlists[:10], 1):  # Ограничиваем 10 плейлистами
            title = pl.get("title") or f"Плейлист #{pl['id']}"
            is_active = "🎵 " if pl['id'] == active_id else ""
            lines.append(f"{i}. {is_active}{title}")
            keyboard.append([InlineKeyboardButton(
                f"{'✓ ' if pl['id'] == active_id else ''}{i}. {title}",
                callback_data=f"select_playlist_{pl['id']}"
            )])
        
        if len(playlists) > 10:
            lines.append(f"\n... и еще {len(playlists) - 10} плейлистов")
        
        if active_id:
            lines.append(f"\nАктивный плейлист отмечен 🎵 ")
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=reply_markup
        )
    
    def shared_playlists(self, update: Update, context: CallbackContext):
        """Команда /shared_playlists."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        playlists = self.db.get_shared_playlists(telegram_id)
        
        if not playlists:
            update.effective_message.reply_text(
                "📂 У вас пока нет общих плейлистов, куда вы добавляете треки.\n\n"
                "💡 Попросите у друзей ссылку на их плейлист или создайте свой и поделитесь ссылкой!",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Получаем активный плейлист
        active_id = self.context_manager.get_active_playlist_id(telegram_id)
        
        lines = ["📂 Плейлисты, куда вы добавляете:\n"]
        keyboard = []
        
        for i, pl in enumerate(playlists[:10], 1):
            title = pl.get("title") or f"Плейлист #{pl['id']}"
            is_active = "🎵 " if pl['id'] == active_id else ""
            lines.append(f"{i}. {is_active}{title}")
            keyboard.append([InlineKeyboardButton(
                f"{'✓ ' if pl['id'] == active_id else ''}{i}. {title}",
                callback_data=f"select_playlist_{pl['id']}"
            )])
        
        if len(playlists) > 10:
            lines.append(f"\n... и еще {len(playlists) - 10} плейлистов")
        
        if active_id:
            lines.append(f"\n🎵 Активный плейлист отмечен")
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=reply_markup
        )
    
    def playlist_info(self, update: Update, context: CallbackContext):
        """Команда /playlist_info."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        playlist_id = self.context_manager.get_active_playlist_id(telegram_id)
        
        if not playlist_id:
            update.effective_message.reply_text(
                "❌ У вас нет активного плейлиста.\n\n"
                "💡 Используйте кнопки «📁 Мои плейлисты» или «📂 Общие плейлисты», чтобы выбрать плейлист.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            update.effective_message.reply_text(
                "❌ Плейлист не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Проверяем доступ
        if not self.db.check_playlist_access(playlist_id, telegram_id):
            update.effective_message.reply_text(
                "❌ У вас нет доступа к этому плейлисту.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Синхронизируем данные плейлиста из API (обновляем название и обложку)
        sync_ok, sync_error = self.playlist_service.sync_playlist_from_api(playlist_id, telegram_id)
        if sync_ok:
            # Обновляем объект плейлиста из БД после синхронизации
            playlist = self.db.get_playlist(playlist_id)
        
        title = playlist.get("title") or "Без названия"
        is_creator = self.db.is_playlist_creator(playlist_id, telegram_id)
        share_link = self.playlist_service.get_share_link(playlist_id, context.bot.username)
        yandex_link = self.playlist_service.get_yandex_link(playlist_id)
        
        # Получаем информацию о количестве треков
        tracks_count = self.playlist_service.get_playlist_tracks_count(playlist_id, telegram_id)
        tracks_count_display = tracks_count if tracks_count is not None else 0
        
        # Получаем информацию о том, куда добавляются треки
        insert_position = playlist.get("insert_position", "end")
        position_text = "в начало" if insert_position == "start" else "в конец"
        
        lines = [
            f"📋 Информация о плейлисте\n",
            f"🎵 Название: {title}",
            f"👤 Ваш статус: {'Создатель' if is_creator else 'Участник'}",
            f"🎶 Треков: {tracks_count_display}",
            f"📍 Треки добавляются: {position_text}",
        ]
        
        if yandex_link:
            lines.append(f"\n🔗 Плейлист в Яндекс.Музыке:\n{yandex_link}")
        
        if share_link:
            lines.append(f"\n🔗 Ссылка для шаринга:\n{share_link}")
            lines.append("\n💡 Отправьте эту ссылку другим пользователям, чтобы они могли добавлять треки.")
        
        # Создаем inline-кнопки для действий
        keyboard = []
        
        # Кнопка "Редактировать" для создателя
        if is_creator:
            keyboard.append([InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_playlist_{playlist_id}")])
        
        # Кнопка удаления трека (для всех, кто имеет права редактирования, и если есть треки)
        can_edit = self.db.check_playlist_access(playlist_id, telegram_id, need_edit=True)
        if can_edit and tracks_count is not None and tracks_count > 0:
            keyboard.append([InlineKeyboardButton("🗑️ Удалить трек", callback_data=f"delete_track_{playlist_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=reply_markup
        )
    
    def show_list(self, update: Update, context: CallbackContext):
        """Команда /list."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        playlist_id = self.context_manager.get_active_playlist_id(telegram_id)
        
        if not playlist_id:
            update.effective_message.reply_text(
                "❌ У вас нет активного плейлиста.\n\n"
                "💡 Используйте кнопки «📁 Мои плейлисты» или «📂 Общие плейлисты», чтобы выбрать плейлист.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            update.effective_message.reply_text(
                "❌ Плейлист не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Проверяем доступ
        if not self.db.check_playlist_access(playlist_id, telegram_id):
            update.effective_message.reply_text(
                "❌ У вас нет доступа к этому плейлисту.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        tracks = self.playlist_service.get_playlist_tracks(playlist_id, telegram_id)
        if tracks is None:
            update.effective_message.reply_text(
                "❌ Не удалось загрузить плейлист. Возможно, проблема с доступом к Яндекс.Музыке.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        if not tracks:
            title = playlist.get("title") or "Плейлист"
            update.effective_message.reply_text(
                f"📋 Плейлист «{title}» пуст.\n\n"
                f"💡 Отправьте ссылку на трек, альбом или плейлист, чтобы добавить треки.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        title = playlist.get("title") or "Плейлист"
        lines = [f"🎵 {title} ({len(tracks)} треков):\n"]
        
        # Получаем клиент для создания YandexService
        client = self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        for i, item in enumerate(tracks, start=1):
            track_display = yandex_service.format_track(item)
            lines.append(f"{i}. {track_display}")
        
        chunk = 50
        for i in range(0, len(lines), chunk):
            part = "\n".join(lines[i:i+chunk])
            update.effective_message.reply_text(part)
    
    def set_token_start(self, update: Update, context: CallbackContext) -> int:
        """Начало установки токена (FSM)."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        # FSM диалог
        update.effective_message.reply_text(
            "🔑 Установка токена Яндекс.Музыки\n\n"
            "⚠️ ВНИМАНИЕ: Вы передаете боту свой токен на свой страх и риск!\n\n"
            "Токен можно получить здесь:\n"
            "https://yandex-music.readthedocs.io/en/main/token.html\n\n"
            "Введите ваш токен:",
            reply_markup=get_cancel_keyboard()
        )
        return WAITING_TOKEN
    
    def set_token_input(self, update: Update, context: CallbackContext) -> int:
        """Обработка ввода токена."""
        telegram_id = update.effective_user.id
        token = update.effective_message.text.strip()
        
        # Проверка на отмену
        if token.lower() in ["отмена", "❌ отмена", "/cancel", "/start"]:
            return self.cancel_operation(update, context)
        
        # Валидация
        if not token:
            update.effective_message.reply_text(
                "❌ Токен не может быть пустым. Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_TOKEN
        
        if self.client_manager.set_user_token(telegram_id, token):
            update.effective_message.reply_text(
                "✅ Токен успешно установлен!\n\n"
                "Теперь ваши плейлисты будут создаваться в вашем аккаунте Яндекс.Музыки.",
                reply_markup=get_main_menu_keyboard()
            )
            self.db.log_action(telegram_id, "token_set", None, None)
        else:
            update.effective_message.reply_text(
                "❌ Не удалось установить токен.\n\n"
                "Возможные причины:\n"
                "• Токен недействителен\n"
                "• Токен истек\n"
                "• Проблема с подключением к Яндекс.Музыке\n\n"
                "Проверьте правильность токена и попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_TOKEN
        
        return ConversationHandler.END
    
    def edit_name_start(self, update: Update, context: CallbackContext) -> int:
        """Начало редактирования названия (FSM)."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        # Если это callback query, извлекаем playlist_id из data
        playlist_id = None
        if update.callback_query:
            data = update.callback_query.data
            if data.startswith("edit_name_"):
                try:
                    playlist_id = int(data.split("_")[-1])
                except (ValueError, IndexError):
                    if update.callback_query.message:
                        update.callback_query.message.reply_text(
                            "❌ Ошибка: неверный формат данных.",
                            reply_markup=get_main_menu_keyboard()
                        )
                    return ConversationHandler.END
        else:
            # Проверяем, есть ли playlist_id в контексте
            playlist_id = context.user_data.get('edit_playlist_id')
        
        # FSM диалог
        if not playlist_id:
            playlist_id = self.context_manager.get_active_playlist_id(telegram_id)
        if not playlist_id:
            update.effective_message.reply_text(
                "❌ У вас нет активного плейлиста.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        # Проверяем, что плейлист существует
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            if update.callback_query:
                update.callback_query.message.reply_text(
                    "❌ Плейлист не найден.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.effective_message.reply_text(
                    "❌ Плейлист не найден.",
                    reply_markup=get_main_menu_keyboard()
                )
            return ConversationHandler.END
        
        if not self.db.is_playlist_creator(playlist_id, telegram_id):
            if update.callback_query:
                update.callback_query.message.reply_text(
                    "❌ Только создатель плейлиста может изменять название.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.effective_message.reply_text(
                    "❌ Только создатель плейлиста может изменять название.",
                    reply_markup=get_main_menu_keyboard()
                )
            return ConversationHandler.END
        
        context.user_data['edit_playlist_id'] = playlist_id
        
        # Определяем, откуда пришел запрос (callback или message)
        if update.callback_query:
            update.callback_query.answer()
            update.callback_query.message.reply_text(
                "✏️ Изменение названия плейлиста\n\n"
                "Введите новое название (максимум 100 символов):",
                reply_markup=get_cancel_keyboard()
            )
        else:
            update.effective_message.reply_text(
                "✏️ Изменение названия плейлиста\n\n"
                "Введите новое название (максимум 100 символов):",
                reply_markup=get_cancel_keyboard()
            )
        return WAITING_EDIT_NAME
    
    def edit_name_input(self, update: Update, context: CallbackContext) -> int:
        """Обработка ввода нового названия."""
        telegram_id = update.effective_user.id
        new_title = update.effective_message.text.strip()
        
        # Проверка на отмену
        if new_title.lower() in ["отмена", "❌ отмена", "/cancel", "/start"]:
            return self.cancel_operation(update, context)
        
        # Валидация
        if not new_title:
            update.effective_message.reply_text(
                "❌ Название не может быть пустым. Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_EDIT_NAME
        
        if len(new_title) > 100:
            update.effective_message.reply_text(
                "❌ Название слишком длинное (максимум 100 символов).\n\n"
                "Введите более короткое название:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_EDIT_NAME
        
        playlist_id = context.user_data.get('edit_playlist_id')
        if not playlist_id:
            update.effective_message.reply_text(
                "❌ Ошибка: плейлист не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        # Используем PlaylistService для изменения имени в Яндекс.Музыке и БД
        ok, error = self.playlist_service.edit_playlist_name(
            playlist_id, new_title, telegram_id
        )
        
        if ok:
            update.effective_message.reply_text(
                f"✅ Название плейлиста изменено на «{new_title}»",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            update.effective_message.reply_text(
                f"❌ Не удалось изменить название плейлиста.\n\n"
                f"{error or 'Неизвестная ошибка'}",
                reply_markup=get_main_menu_keyboard()
            )
        
        # Очищаем контекст
        context.user_data.pop('edit_playlist_id', None)
        
        return ConversationHandler.END
    
    def delete_playlist_cmd(self, update: Update, context: CallbackContext):
        """Команда /delete_playlist."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        # Получаем активный плейлист
        playlist_id = self.context_manager.get_active_playlist_id(telegram_id)
        
        if not playlist_id:
            update.effective_message.reply_text("У вас нет активного плейлиста.")
            return
        
        # Проверяем, что пользователь - создатель
        if not self.db.is_playlist_creator(playlist_id, telegram_id):
            update.effective_message.reply_text("Только создатель плейлиста может удалять его.")
            return
        
        playlist = self.db.get_playlist(playlist_id)
        title = playlist.get("title") or "плейлист" if playlist else "плейлист"
        
        # Удаляем из БД (плейлист в Яндекс.Музыке остается, но мы теряем связь)
        self.db.delete_playlist(playlist_id)
        
        # Удаляем из контекста
        self.context_manager.clear_active_playlist(telegram_id)
        
        update.effective_message.reply_text(f"✅ Плейлист «{title}» удален из базы данных бота.")
        self.db.log_action(telegram_id, "playlist_deleted", playlist_id, None)
    
    def delete_track_start(self, update: Update, context: CallbackContext) -> int:
        """Начало удаления трека (FSM)."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        # Если это callback query, извлекаем playlist_id из data
        playlist_id = None
        if update.callback_query:
            data = update.callback_query.data
            if data.startswith("delete_track_"):
                try:
                    playlist_id = int(data.split("_")[-1])
                except (ValueError, IndexError):
                    if update.callback_query.message:
                        update.callback_query.message.reply_text(
                            "❌ Ошибка: неверный формат данных.",
                            reply_markup=get_main_menu_keyboard()
                        )
                    return ConversationHandler.END
        
        # FSM диалог
        if not playlist_id:
            playlist_id = self.context_manager.get_active_playlist_id(telegram_id)
        
        if not playlist_id:
            if update.callback_query:
                update.callback_query.message.reply_text(
                    "❌ У вас нет активного плейлиста.\n\n"
                    "💡 Используйте кнопки «📁 Мои плейлисты» или «📂 Общие плейлисты», чтобы выбрать плейлист.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.effective_message.reply_text(
                    "❌ У вас нет активного плейлиста.\n\n"
                    "💡 Используйте кнопки «📁 Мои плейлисты» или «📂 Общие плейлисты», чтобы выбрать плейлист.",
                    reply_markup=get_main_menu_keyboard()
                )
            return ConversationHandler.END
        
        # Проверяем доступ
        if not self.db.check_playlist_access(playlist_id, telegram_id, need_edit=True):
            playlist = self.db.get_playlist(playlist_id)
            title = playlist.get("title") or "плейлист" if playlist else "плейлист"
            if update.callback_query:
                update.callback_query.message.reply_text(
                    f"❌ У вас нет прав на удаление треков из плейлиста «{title}».\n\n"
                    f"💡 Только создатель или пользователи с правами редактирования могут удалять треки.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.effective_message.reply_text(
                    f"❌ У вас нет прав на удаление треков из плейлиста «{title}».\n\n"
                    f"💡 Только создатель или пользователи с правами редактирования могут удалять треки.",
                    reply_markup=get_main_menu_keyboard()
                )
            return ConversationHandler.END
        
        # Получаем информацию о плейлисте для показа количества треков
        tracks = self.playlist_service.get_playlist_tracks(playlist_id, telegram_id)
        if tracks is None:
            if update.callback_query:
                update.callback_query.message.reply_text(
                    "❌ Не удалось загрузить плейлист.\n\n"
                    "💡 Возможно, проблема с доступом к Яндекс.Музыке.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.effective_message.reply_text(
                    "❌ Не удалось загрузить плейлист.\n\n"
                    "💡 Возможно, проблема с доступом к Яндекс.Музыке.",
                    reply_markup=get_main_menu_keyboard()
                )
            return ConversationHandler.END
        
        total = len(tracks)
        
        if total == 0:
            if update.callback_query:
                update.callback_query.message.reply_text(
                    "❌ Плейлист пуст. Нечего удалять.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.effective_message.reply_text(
                    "❌ Плейлист пуст. Нечего удалять.",
                    reply_markup=get_main_menu_keyboard()
                )
            return ConversationHandler.END
        
        # Сохраняем playlist_id в контексте для FSM
        context.user_data['delete_track_playlist_id'] = playlist_id
        context.user_data['delete_track_total'] = total
        
        playlist = self.db.get_playlist(playlist_id)
        playlist_title = playlist.get("title") or "плейлист" if playlist else "плейлист"
        
        # Определяем, откуда пришел запрос (callback или message)
        if update.callback_query:
            update.callback_query.answer()
            update.callback_query.message.reply_text(
                f"🗑️ Удаление трека из плейлиста «{playlist_title}»\n\n"
                f"В плейлисте {total} треков.\n\n"
                f"Введите номер трека для удаления (от 1 до {total}):\n\n"
                f"💡 Используйте /list, чтобы увидеть список треков с номерами.",
                reply_markup=get_cancel_keyboard()
            )
        else:
            update.effective_message.reply_text(
                f"🗑️ Удаление трека из плейлиста «{playlist_title}»\n\n"
                f"В плейлисте {total} треков.\n\n"
                f"Введите номер трека для удаления (от 1 до {total}):\n\n"
                f"💡 Используйте /list, чтобы увидеть список треков с номерами.",
                reply_markup=get_cancel_keyboard()
            )
        return WAITING_TRACK_NUMBER
    
    def delete_track_input(self, update: Update, context: CallbackContext) -> int:
        """Обработка ввода номера трека для удаления."""
        import re
        telegram_id = update.effective_user.id
        raw = update.effective_message.text.strip()
        
        logger.info(f"delete_track_input вызван для пользователя {telegram_id}, текст: {raw}")
        
        # Проверка на отмену (fallback должен обработать, но на всякий случай)
        if raw in ["❌ Отмена", "отмена", "Отмена"] or raw.lower() in ["отмена", "/cancel", "/start"]:
            logger.info(f"Обнаружена отмена в delete_track_input")
            return self.cancel_operation(update, context)
        
        # Валидация
        if not re.match(r"^\d+$", raw):
            update.effective_message.reply_text(
                "❌ Неверный формат. Укажите номер трека (число).\n\n"
                "💡 Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_TRACK_NUMBER
        
        index = int(raw)
        playlist_id = context.user_data.get('delete_track_playlist_id')
        total = context.user_data.get('delete_track_total')
        
        if not playlist_id:
            update.effective_message.reply_text(
                "❌ Ошибка: плейлист не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        if index < 1 or index > total:
            update.effective_message.reply_text(
                f"❌ Номер трека вне диапазона.\n\n"
                f"💡 Доступные номера: 1..{total}\n"
                f"Введите номер еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_TRACK_NUMBER
        
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            update.effective_message.reply_text(
                "❌ Плейлист не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        tracks = self.playlist_service.get_playlist_tracks(playlist_id, telegram_id)
        if tracks is None:
            update.effective_message.reply_text(
                "❌ Не удалось загрузить плейлист.\n\n"
                "💡 Возможно, проблема с доступом к Яндекс.Музыке.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        if index < 1 or index > len(tracks):
            update.effective_message.reply_text(
                f"❌ Номер трека вне диапазона.\n\n"
                f"💡 Доступные номера: 1..{len(tracks)}\n"
                f"Введите номер еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_TRACK_NUMBER
        
        # Получаем информацию о треке перед удалением
        item = tracks[index - 1]
        
        # Получаем клиент для создания YandexService
        client = self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        track_display = yandex_service.format_track(item)
        
        from_idx = index - 1
        to_idx = index - 1
        ok, err = self.playlist_service.delete_track(playlist_id, from_idx, to_idx, telegram_id)
        
        if ok:
            track_info = f"«{track_display}»"
            update.effective_message.reply_text(
                f"✅ Трек №{index} {track_info} удалён из плейлиста.",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            update.effective_message.reply_text(
                f"❌ Не удалось удалить трек: {err}\n\n"
                f"💡 Попробуйте еще раз или проверьте права доступа.",
                reply_markup=get_main_menu_keyboard()
            )
        
        # Очищаем контекст
        context.user_data.pop('delete_track_playlist_id', None)
        context.user_data.pop('delete_track_total', None)
        
        return ConversationHandler.END
    
    def set_cover_start(self, update: Update, context: CallbackContext) -> int:
        """Начало установки обложки (FSM)."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        # Если это callback query, извлекаем playlist_id из data
        playlist_id = None
        if update.callback_query:
            data = update.callback_query.data
            if data.startswith("set_cover_"):
                try:
                    playlist_id = int(data.split("_")[-1])
                except (ValueError, IndexError):
                    if update.callback_query.message:
                        update.callback_query.message.reply_text(
                            "❌ Ошибка: неверный формат данных.",
                            reply_markup=get_main_menu_keyboard()
                        )
                    return ConversationHandler.END
        else:
            # Проверяем, есть ли playlist_id в контексте
            playlist_id = context.user_data.get('set_cover_playlist_id')
        
        # FSM диалог
        if not playlist_id:
            playlist_id = self.context_manager.get_active_playlist_id(telegram_id)
        if not playlist_id:
            if update.callback_query:
                update.callback_query.message.reply_text(
                    "❌ У вас нет активного плейлиста.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.effective_message.reply_text(
                    "❌ У вас нет активного плейлиста.",
                    reply_markup=get_main_menu_keyboard()
                )
            return ConversationHandler.END
        
        # Проверяем, что плейлист существует
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            if update.callback_query:
                update.callback_query.message.reply_text(
                    "❌ Плейлист не найден.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.effective_message.reply_text(
                    "❌ Плейлист не найден.",
                    reply_markup=get_main_menu_keyboard()
                )
            return ConversationHandler.END
        
        if not self.db.is_playlist_creator(playlist_id, telegram_id):
            if update.callback_query:
                update.callback_query.message.reply_text(
                    "❌ Только создатель плейлиста может изменять обложку.",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                update.effective_message.reply_text(
                    "❌ Только создатель плейлиста может изменять обложку.",
                    reply_markup=get_main_menu_keyboard()
                )
            return ConversationHandler.END
        
        context.user_data['set_cover_playlist_id'] = playlist_id
        
        # Определяем, откуда пришел запрос (callback или message)
        if update.callback_query:
            update.callback_query.answer()
            update.callback_query.message.reply_text(
                "🖼️ Установка обложки плейлиста\n\n"
                "Отправьте фото для обложки плейлиста:",
                reply_markup=get_cancel_keyboard()
            )
        else:
            update.effective_message.reply_text(
                "🖼️ Установка обложки плейлиста\n\n"
                "Отправьте фото для обложки плейлиста:",
                reply_markup=get_cancel_keyboard()
            )
        return WAITING_PLAYLIST_COVER
    
    def set_cover_input(self, update: Update, context: CallbackContext) -> int:
        """Обработка ввода обложки."""
        telegram_id = update.effective_user.id
        
        # Проверяем, что это фото
        if not update.effective_message.photo:
            update.effective_message.reply_text(
                "❌ Пожалуйста, отправьте фото для обложки.\n\n"
                "💡 Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return WAITING_PLAYLIST_COVER
        
        playlist_id = context.user_data.get('set_cover_playlist_id')
        if not playlist_id:
            update.effective_message.reply_text(
                "❌ Ошибка: плейлист не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        # Получаем фото (берем самое большое)
        photo = update.effective_message.photo[-1]
        
        update.effective_message.reply_text("⏳ Загружаю обложку...")
        
        # Скачиваем фото
        file = photo.get_file()
        image_file = file.download_as_bytearray()
        
        # Устанавливаем обложку
        ok, err = self.playlist_service.set_playlist_cover(playlist_id, image_file, telegram_id)
        
        if ok:
            update.effective_message.reply_text(
                "✅ Обложка плейлиста успешно установлена!",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            update.effective_message.reply_text(
                f"❌ Не удалось установить обложку: {err}\n\n"
                f"💡 Попробуйте еще раз или проверьте права доступа.",
                reply_markup=get_main_menu_keyboard()
            )
        
        # Очищаем контекст
        context.user_data.pop('set_cover_playlist_id', None)
        
        return ConversationHandler.END
    
    def cancel_operation(self, update: Update, context: CallbackContext) -> int:
        """Отмена текущей операции."""
        # Очищаем контекст FSM
        context.user_data.pop('delete_track_playlist_id', None)
        context.user_data.pop('delete_track_total', None)
        context.user_data.pop('edit_playlist_id', None)
        context.user_data.pop('set_cover_playlist_id', None)
        
        update.effective_message.reply_text(
            "❌ Операция отменена.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    def buy_limit(self, update: Update, context: CallbackContext):
        """Команда для покупки расширенного лимита."""
        telegram_id = update.effective_user.id
        self.db.ensure_user(telegram_id, update.effective_user.username)
        
        # Получаем доступные планы
        payment_service = PaymentService(self.db)
        plans = payment_service.get_available_plans()
        
        # Получаем текущий лимит пользователя
        current_limit = self.db.get_user_playlist_limit(telegram_id)
        current_count = self.db.count_user_playlists(telegram_id)
        limit_text = "безлимитно" if current_limit == -1 else f"{current_limit} плейлистов"
        
        # Формируем клавиатуру с тарифами
        keyboard = []
        for plan_id, plan_data in plans.items():
            button_text = f"⭐ {plan_data['name']} — {plan_data['stars']} Stars"
            keyboard.append([InlineKeyboardButton(
                button_text,
                callback_data=f"buy_{plan_id}"
            )])
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_payment")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.effective_message.reply_text(
            f"💳 Выберите тарифный план:\n\n"
            f"📊 Текущий лимит: {limit_text}\n"
            f"📁 Создано плейлистов: {current_count}\n\n"
            f"⭐ Stars — это внутренняя валюта Telegram\n"
            f"Вы можете купить Stars прямо в приложении Telegram",
            reply_markup=reply_markup
        )
    
    def handle_pre_checkout_query(self, update: Update, context: CallbackContext):
        """Обработка pre_checkout_query."""
        query = update.pre_checkout_query
        telegram_id = query.from_user.id
        
        # Проверяем платеж
        payment_service = PaymentService(self.db)
        payment = self.db.get_payment_by_payload(query.invoice_payload)
        
        if not payment or payment['status'] != 'pending':
            # Отклоняем платеж
            context.bot.answer_pre_checkout_query(
                pre_checkout_query_id=query.id,
                ok=False,
                error_message="Платеж не найден или уже обработан"
            )
            return
        
        # Проверяем сумму
        if payment['stars_amount'] != query.total_amount:
            context.bot.answer_pre_checkout_query(
                pre_checkout_query_id=query.id,
                ok=False,
                error_message="Сумма платежа не совпадает"
            )
            return
        
        # Подтверждаем платеж
        context.bot.answer_pre_checkout_query(
            pre_checkout_query_id=query.id,
            ok=True
        )
    
    def handle_successful_payment(self, update: Update, context: CallbackContext):
        """Обработка успешного платежа."""
        payment = update.message.successful_payment
        telegram_id = update.effective_user.id
        
        payment_service = PaymentService(self.db)
        success = payment_service.process_successful_payment(
            telegram_id=telegram_id,
            invoice_payload=payment.invoice_payload,
            stars_amount=payment.total_amount
        )
        
        if success:
            # Получаем информацию о новой подписке
            subscription = self.db.get_active_subscription(telegram_id)
            if subscription:
                plan = payment_service.get_available_plans()[subscription['subscription_type']]
                limit = plan['limit']
                limit_text = "безлимитно" if limit == -1 else f"{limit} плейлистов"
                
                update.message.reply_text(
                    f"✅ Платеж успешно обработан!\n\n"
                    f"🎉 Ваш лимит увеличен до {limit_text}\n\n"
                    f"Теперь вы можете создавать больше плейлистов!",
                    reply_markup=get_main_menu_keyboard()
                )
                self.db.log_action(telegram_id, "subscription_purchased", None, f"type={subscription['subscription_type']}")
        else:
            update.message.reply_text(
                "❌ Произошла ошибка при обработке платежа.\n"
                "Пожалуйста, свяжитесь с поддержкой.",
                reply_markup=get_main_menu_keyboard()
            )

