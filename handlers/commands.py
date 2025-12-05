"""
Обработчики команд Telegram бота.
"""
import logging
import os
import asyncio
from typing import Optional
from aiogram import Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, PreCheckoutQuery, SuccessfulPayment, BufferedInputFile, LinkPreviewOptions
from aiogram.fsm.context import FSMContext

from database import DatabaseInterface
from yandex_client_manager import YandexClientManager
from utils.context import UserContextManager
from utils.validation import validate_playlist_name
from utils.message_helpers import (
    send_message,
    NO_ACTIVE_PLAYLIST,
    NO_ACTIVE_PLAYLIST_SELECT,
    NO_ACTIVE_PLAYLIST_SHORT,
    PLAYLIST_NOT_FOUND,
    PLAYLIST_NOT_FOUND_ERROR,
    NO_PLAYLIST_ACCESS,
    ONLY_CREATOR_CAN_CHANGE_NAME,
    ONLY_CREATOR_CAN_CHANGE_COVER,
    CREATING_PLAYLIST
)
from services.playlist_service import PlaylistService
from services.yandex_service import YandexService
from services.payment_service import PaymentService
from .keyboards import get_main_menu_keyboard, get_cancel_keyboard
from .states import (
    CreatePlaylistStates,
    SetTokenStates,
    EditNameStates,
    DeleteTrackStates,
    SetCoverStates
)

logger = logging.getLogger(__name__)

# Лимит плейлистов на пользователя (можно задать через переменную окружения)
DEFAULT_PLAYLIST_LIMIT = 2
PLAYLIST_LIMIT = int(os.getenv("PLAYLIST_LIMIT", DEFAULT_PLAYLIST_LIMIT))

# Размер страницы для пагинации списка треков
TRACKS_PER_PAGE = 12


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
    
    async def start_handler(self, message: Message):
        """Команда /start (обрабатывает и с аргументами, и без)."""
        telegram_id = message.from_user.id
        username = message.from_user.username
        await self.db.ensure_user(telegram_id, username)
        
        # Извлекаем аргументы из команды (для шаринга плейлистов)
        command_args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
        if command_args:
            share_token = command_args.split()[0] if command_args else None
            if share_token:
                playlist = await self.db.get_playlist_by_share_token(share_token)
                if playlist:
                    # Предоставляем доступ к плейлисту
                    await self.db.grant_playlist_access(playlist["id"], telegram_id, can_add=True)
                    # Устанавливаем как активный
                    self.context_manager.set_active_playlist(telegram_id, playlist["id"])
                    
                    await message.answer(
                        f"✅ Вы получили доступ к плейлисту «{playlist.get('title', 'Без названия')}»!\n\n"
                        f"Теперь вы можете добавлять треки в этот плейлист, отправляя ссылки на треки, альбомы или плейлисты.",
                        reply_markup=get_main_menu_keyboard()
                    )
                    await self.db.log_action(telegram_id, "playlist_shared_access", playlist["id"], f"via_token={share_token}")
                    return
        
        # Показываем информацию об активном плейлисте, если есть
        active_info = await self.context_manager.get_active_playlist_info(telegram_id)
        
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
        
        await message.answer(
            help_text,
            reply_markup=get_main_menu_keyboard()
        )
        await self.db.log_action(telegram_id, "command_start", None, None)
    
    async def main_menu(self, message: Message):
        """Главное меню."""
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        active_info = await self.context_manager.get_active_playlist_info(telegram_id)
        text = "🏠 Главное меню\n\n"
        
        if active_info:
            text += f"{active_info}\n\n"
        else:
            text += "⚠️ У вас нет активного плейлиста.\n"
            text += "Создайте новый или получите доступ к существующему.\n\n"
        
        text += "Выберите действие из меню ниже:"
        
        await message.answer(
            text,
            reply_markup=get_main_menu_keyboard()
        )
    
    async def create_playlist_start(self, message: Message, state: FSMContext):
        """Начало создания плейлиста (FSM)."""
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        # FSM диалог
        await message.answer(
            "📝 Создание нового плейлиста\n\n"
            "Введите название плейлиста (максимум 100 символов):\n\n"
            "💡 Пример: Моя музыка",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(CreatePlaylistStates.waiting_playlist_name)
    
    async def create_playlist_name(self, message: Message, state: FSMContext):
        """Обработка названия плейлиста."""
        telegram_id = message.from_user.id
        title = message.text.strip()
        
        # Проверка на отмену
        if title.lower() in ["отмена", "❌ отмена", "/cancel", "/start"]:
            await self.cancel_operation(message, state)
            return
        
        # Предварительная валидация названия
        is_valid, validation_error = validate_playlist_name(title)
        if not is_valid:
            await message.answer(
                f"❌ {validation_error}\n\n"
                f"💡 Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        # Проверяем лимит плейлистов (с учетом подписки)
        user_limit = await self.db.get_user_playlist_limit(telegram_id)
        current_count = await self.db.count_user_playlists(telegram_id)
        
        # Проверка лимита
        if user_limit == -1:
            # Unlimited - пропускаем проверку
            pass
        elif current_count >= user_limit:
            # Показываем предложение купить расширенный лимит
            limit_text = "безлимитно" if user_limit == -1 else f"{user_limit} плейлистов"
            await message.answer(
                f"❌ Достигнут лимит плейлистов!\n\n"
                f"📊 У вас уже создано {current_count} из {user_limit} плейлистов.\n\n"
                f"💡 Хотите увеличить лимит? Используйте /buy_limit",
                reply_markup=get_main_menu_keyboard()
            )
            await state.clear()
            return
        
        # Создаем плейлист
        await send_message(message, CREATING_PLAYLIST)
        result, error = await self.client_manager.create_playlist(telegram_id, title)
        
        if result:
            playlist_id = result["id"]
            bot_info = await message.bot.get_me()
            share_link = await self.playlist_service.get_share_link(playlist_id, bot_info.username)
            
            self.context_manager.set_active_playlist(telegram_id, playlist_id)
            
            await message.answer(
                f"✅ Плейлист «{title}» успешно создан!\n\n"
                f"🔗 Ссылка для шаринга:\n{share_link}\n\n"
                f"Отправьте эту ссылку другим пользователям, чтобы они могли добавлять треки в ваш плейлист.",
                reply_markup=get_main_menu_keyboard()
            )
            await self.db.log_action(telegram_id, "playlist_created", playlist_id, f"title={title}")
            await state.clear()
        else:
            error_message = error or "Не удалось создать плейлист."
            
            # Проверяем на ошибку модерации - не очищаем state, предлагаем ввести другое название
            if "модерац" in error_message.lower() or "moderation" in error_message.lower():
                await message.answer(
                    f"❌ {error_message}\n\n"
                    f"💡 Попробуйте ввести другое название:",
                    reply_markup=get_cancel_keyboard()
                )
                # Не очищаем state - остаемся в состоянии ожидания названия
                return
            
            # Для других ошибок - показываем сообщение и очищаем state
            await message.answer(
                f"❌ {error_message}\n\n"
                f"💡 Если проблема с токеном, используйте /set_token для установки своего токена.",
                reply_markup=get_main_menu_keyboard()
            )
            await state.clear()
    
    async def my_playlists(self, message: Message):
        """Команда /my_playlists."""
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        playlists = await self.db.get_user_playlists(telegram_id, only_created=True)
        
        # Получаем информацию о лимите (с учетом подписки)
        current_count = len(playlists)
        user_limit = await self.db.get_user_playlist_limit(telegram_id)
        limit_text = "∞" if user_limit == -1 else str(user_limit)
        limit_info = f"📊 {current_count}/{limit_text} плейлистов"
        
        if not playlists:
            await message.answer(
                f"📁 У вас пока нет созданных плейлистов.\n\n"
                f"{limit_info}\n\n"
                f"💡 Создайте новый плейлист, используя кнопку «➕ Создать плейлист» или команду /create_playlist",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Получаем активный плейлист
        active_id = await self.context_manager.get_active_playlist_id(telegram_id)
        
        lines = [f"📁 Ваши плейлисты:\n{limit_info}\n"]
        keyboard = []
        
        for i, pl in enumerate(playlists[:10], 1):  # Ограничиваем 10 плейлистами
            title = pl.get("title") or f"Плейлист #{pl['id']}"
            is_active = "🎵 " if pl['id'] == active_id else ""
            lines.append(f"{i}. {is_active}{title}")
            keyboard.append([InlineKeyboardButton(
                text=f"{'✓ ' if pl['id'] == active_id else ''}{i}. {title}",
                callback_data=f"select_playlist_{pl['id']}"
            )])
        
        if len(playlists) > 10:
            lines.append(f"\n... и еще {len(playlists) - 10} плейлистов")
        
        if active_id:
            lines.append(f"\nАктивный плейлист отмечен 🎵 ")
        
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
        await message.answer(
            "\n".join(lines),
            reply_markup=reply_markup
        )
    
    async def shared_playlists(self, message: Message):
        """Команда /shared_playlists."""
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        playlists = await self.db.get_shared_playlists(telegram_id)
        
        if not playlists:
            await message.answer(
                "📂 У вас пока нет общих плейлистов, куда вы добавляете треки.\n\n"
                "💡 Попросите у друзей ссылку на их плейлист или создайте свой и поделитесь ссылкой!",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Получаем активный плейлист
        active_id = await self.context_manager.get_active_playlist_id(telegram_id)
        
        lines = ["📂 Плейлисты, куда вы добавляете:\n"]
        keyboard = []
        
        for i, pl in enumerate(playlists[:10], 1):
            title = pl.get("title") or f"Плейлист #{pl['id']}"
            is_active = "🎵 " if pl['id'] == active_id else ""
            lines.append(f"{i}. {is_active}{title}")
            keyboard.append([InlineKeyboardButton(
                text=f"{'✓ ' if pl['id'] == active_id else ''}{i}. {title}",
                callback_data=f"select_playlist_{pl['id']}"
            )])
        
        if len(playlists) > 10:
            lines.append(f"\n... и еще {len(playlists) - 10} плейлистов")
        
        if active_id:
            lines.append(f"\n🎵 Активный плейлист отмечен")
        
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
        await message.answer(
            "\n".join(lines),
            reply_markup=reply_markup
        )
    
    async def playlist_info(self, message: Message):
        """Команда /playlist_info."""
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        playlist_id = await self.context_manager.get_active_playlist_id(telegram_id)
        
        if not playlist_id:
            await send_message(message, NO_ACTIVE_PLAYLIST_SELECT, use_main_menu=True)
            return
        
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await send_message(message, PLAYLIST_NOT_FOUND, use_main_menu=True)
            return
        
        # Проверяем доступ
        if not await self.db.check_playlist_access(playlist_id, telegram_id):
            await send_message(message, NO_PLAYLIST_ACCESS, use_main_menu=True)
            return
        
        # Синхронизируем данные плейлиста из API (обновляем название и обложку)
        sync_ok, sync_error = await self.playlist_service.sync_playlist_from_api(playlist_id, telegram_id)
        if sync_ok:
            # Обновляем объект плейлиста из БД после синхронизации
            playlist = await self.db.get_playlist(playlist_id)
        
        title = playlist.get("title") or "Без названия"
        is_creator = await self.db.is_playlist_creator(playlist_id, telegram_id)
        bot_info = await message.bot.get_me()
        share_link = await self.playlist_service.get_share_link(playlist_id, bot_info.username)
        yandex_link = await self.playlist_service.get_yandex_link(playlist_id)
        
        # Получаем информацию о количестве треков
        tracks_count = await self.playlist_service.get_playlist_tracks_count(playlist_id, telegram_id)
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
            keyboard.append([InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_playlist_{playlist_id}")])
        
        # Кнопка удаления трека (для всех, кто имеет права редактирования, и если есть треки)
        can_edit = await self.db.check_playlist_access(playlist_id, telegram_id, need_edit=True)
        if can_edit and tracks_count is not None and tracks_count > 0:
            keyboard.append([InlineKeyboardButton(text="🗑️ Удалить трек", callback_data=f"delete_track_{playlist_id}")])
        
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
        
        # Пытаемся получить URL обложки плейлиста для превью
        cover_url = await self.playlist_service.get_playlist_cover_url(playlist_id, telegram_id, only_custom=False)
        
        # Формируем текст сообщения
        text_content = "\n".join(lines)
        
        # Если есть URL обложки, добавляем невидимую ссылку для превью
        if cover_url:
            # Добавляем невидимую ссылку в конец текста (zero-width space)
            text_content += f'\n<a href="{cover_url}">&#8203;</a>'
            # Используем HTML-разметку и включаем превью для этой ссылки
            await message.answer(
                text_content,
                reply_markup=reply_markup,
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(url=cover_url, prefer_large_media=True)
            )
        else:
            # Если обложки нет, отправляем текст с отключенным превью ссылок
            await message.answer(
                text_content,
                reply_markup=reply_markup,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
    
    def _format_tracks_page(
        self,
        tracks: list,
        page: int,
        playlist_title: str,
        playlist_id: int,
        yandex_service: YandexService
    ) -> tuple[str, InlineKeyboardMarkup]:
        """
        Форматирует страницу треков с пагинацией.
        
        Args:
            tracks: Список треков
            page: Номер страницы (начиная с 1)
            playlist_title: Название плейлиста
            playlist_id: ID плейлиста для callback_data
            yandex_service: Сервис для форматирования треков
            
        Returns:
            Кортеж (текст сообщения, клавиатура пагинации)
        """
        total_tracks = len(tracks)
        total_pages = (total_tracks + TRACKS_PER_PAGE - 1) // TRACKS_PER_PAGE
        
        # Вычисляем индексы для текущей страницы
        start_idx = (page - 1) * TRACKS_PER_PAGE
        end_idx = min(start_idx + TRACKS_PER_PAGE, total_tracks)
        
        # Формируем заголовок
        lines = [f"🎵 {playlist_title} ({total_tracks} треков)\n"]
        lines.append(f"📄 Страница {page} из {total_pages}\n")
        
        # Добавляем треки текущей страницы
        page_tracks = tracks[start_idx:end_idx]
        for i, item in enumerate(page_tracks, start=start_idx + 1):
            track_display = yandex_service.format_track(item)
            lines.append(f"{i}. {track_display}")
        
        text = "\n".join(lines)
        
        # Создаем клавиатуру пагинации
        keyboard = []
        if total_pages > 1:
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data=f"list_page_{playlist_id}_{page - 1}"
                ))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton(
                    text="Вперед ▶️",
                    callback_data=f"list_page_{playlist_id}_{page + 1}"
                ))
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
        
        return text, reply_markup
    
    async def show_list(self, message: Message, page: int = 1):
        """Команда /list с поддержкой пагинации."""
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        playlist_id = await self.context_manager.get_active_playlist_id(telegram_id)
        
        if not playlist_id:
            await send_message(message, NO_ACTIVE_PLAYLIST_SELECT, use_main_menu=True)
            return
        
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await send_message(message, PLAYLIST_NOT_FOUND, use_main_menu=True)
            return
        
        # Проверяем доступ
        if not await self.db.check_playlist_access(playlist_id, telegram_id):
            await send_message(message, NO_PLAYLIST_ACCESS, use_main_menu=True)
            return
        
        tracks = await self.playlist_service.get_playlist_tracks(playlist_id, telegram_id)
        if tracks is None:
            await message.answer(
                "❌ Не удалось загрузить плейлист. Возможно, проблема с доступом к Яндекс.Музыке.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        if not tracks:
            title = playlist.get("title") or "Плейлист"
            await message.answer(
                f"📋 Плейлист «{title}» пуст.\n\n"
                f"💡 Отправьте ссылку на трек, альбом или плейлист, чтобы добавить треки.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Получаем клиент для создания YandexService
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        title = playlist.get("title") or "Плейлист"
        text, reply_markup = self._format_tracks_page(tracks, page, title, playlist_id, yandex_service)
        
        await message.answer(text, reply_markup=reply_markup)
    
    async def set_token_start(self, message: Message, state: FSMContext):
        """Начало установки токена (FSM)."""
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        # FSM диалог
        await message.answer(
            "🔑 Установка токена Яндекс.Музыки\n\n"
            "⚠️ ВНИМАНИЕ: Вы передаете боту свой токен на свой страх и риск!\n\n"
            "Токен можно получить здесь:\n"
            "https://yandex-music.readthedocs.io/en/main/token.html\n\n"
            "Введите ваш токен:",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(SetTokenStates.waiting_token)
    
    async def set_token_input(self, message: Message, state: FSMContext):
        """Обработка ввода токена."""
        telegram_id = message.from_user.id
        token = message.text.strip()
        
        # Проверка на отмену
        if token.lower() in ["отмена", "❌ отмена", "/cancel", "/start"]:
            await self.cancel_operation(message, state)
            return
        
        # Валидация
        if not token:
            await message.answer(
                "❌ Токен не может быть пустым. Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        if await self.client_manager.set_user_token(telegram_id, token):
            await message.answer(
                "✅ Токен успешно установлен!\n\n"
                "Теперь ваши плейлисты будут создаваться в вашем аккаунте Яндекс.Музыки.",
                reply_markup=get_main_menu_keyboard()
            )
            await self.db.log_action(telegram_id, "token_set", None, None)
        else:
            await message.answer(
                "❌ Не удалось установить токен.\n\n"
                "Возможные причины:\n"
                "• Токен недействителен\n"
                "• Токен истек\n"
                "• Проблема с подключением к Яндекс.Музыке\n\n"
                "Проверьте правильность токена и попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        await state.clear()
    
    async def edit_name_start(self, message_or_query, state: FSMContext):
        """Начало редактирования названия (FSM)."""
        # Определяем, откуда пришел запрос
        if isinstance(message_or_query, CallbackQuery):
            query = message_or_query
            message = query.message
            telegram_id = query.from_user.id
            # Извлекаем playlist_id из callback_data
            data = query.data
            try:
                playlist_id = int(data.split("_")[-1])
            except (ValueError, IndexError):
                await message.answer(
                    "❌ Ошибка: неверный формат данных.",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            await query.answer()
        else:
            message = message_or_query
            telegram_id = message.from_user.id
            # Проверяем, есть ли playlist_id в состоянии FSM
            state_data = await state.get_data()
            playlist_id = state_data.get('edit_playlist_id')
        
        await self.db.ensure_user(telegram_id, message.from_user.username if hasattr(message.from_user, 'username') else None)
        
        # FSM диалог
        if not playlist_id:
            playlist_id = await self.context_manager.get_active_playlist_id(telegram_id)
        if not playlist_id:
            await send_message(message, NO_ACTIVE_PLAYLIST_SHORT, use_main_menu=True)
            return
        
        # Проверяем, что плейлист существует
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await send_message(message, PLAYLIST_NOT_FOUND, use_main_menu=True)
            return
        
        if not await self.db.is_playlist_creator(playlist_id, telegram_id):
            await send_message(message, ONLY_CREATOR_CAN_CHANGE_NAME, use_main_menu=True)
            return
        
        await state.update_data(edit_playlist_id=playlist_id)
        
        await message.answer(
            "✏️ Изменение названия плейлиста\n\n"
            "Введите новое название (максимум 100 символов):",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(EditNameStates.waiting_edit_name)
    
    async def edit_name_input(self, message: Message, state: FSMContext):
        """Обработка ввода нового названия."""
        telegram_id = message.from_user.id
        new_title = message.text.strip()
        
        # Проверка на отмену
        if new_title.lower() in ["отмена", "❌ отмена", "/cancel", "/start"]:
            await self.cancel_operation(message, state)
            return
        
        # Предварительная валидация названия
        is_valid, validation_error = validate_playlist_name(new_title)
        if not is_valid:
            await message.answer(
                f"❌ {validation_error}\n\n"
                f"💡 Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        state_data = await state.get_data()
        playlist_id = state_data.get('edit_playlist_id')
        if not playlist_id:
            await send_message(message, PLAYLIST_NOT_FOUND_ERROR, use_main_menu=True)
            await state.clear()
            return
        
        # Используем PlaylistService для изменения имени в Яндекс.Музыке и БД
        ok, error = await self.playlist_service.edit_playlist_name(
            playlist_id, new_title, telegram_id
        )
        
        if ok:
            await message.answer(
                f"✅ Название плейлиста изменено на «{new_title}»",
                reply_markup=get_main_menu_keyboard()
            )
            await state.clear()
        else:
            error_message = error or "Не удалось изменить название плейлиста."
            
            # Проверяем на ошибку модерации - возвращаем в состояние редактирования
            if "модерац" in error_message.lower() or "moderation" in error_message.lower():
                await message.answer(
                    f"❌ {error_message}\n\n"
                    f"💡 Попробуйте ввести другое название:",
                    reply_markup=get_cancel_keyboard()
                )
                # Не очищаем state - остаемся в состоянии ожидания нового названия
                return
            
            # Для других ошибок - показываем сообщение и очищаем state
            await message.answer(
                f"❌ {error_message}",
                reply_markup=get_main_menu_keyboard()
            )
            await state.clear()
    
    async def delete_playlist_cmd(self, message: Message):
        """Команда /delete_playlist."""
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        # Получаем активный плейлист
        playlist_id = await self.context_manager.get_active_playlist_id(telegram_id)
        
        if not playlist_id:
            await message.answer("У вас нет активного плейлиста.")
            return
        
        # Проверяем, что пользователь - создатель
        if not await self.db.is_playlist_creator(playlist_id, telegram_id):
            await message.answer("Только создатель плейлиста может удалять его.")
            return
        
        playlist = await self.db.get_playlist(playlist_id)
        title = playlist.get("title") or "плейлист" if playlist else "плейлист"
        
        # Удаляем из БД (плейлист в Яндекс.Музыке остается, но мы теряем связь)
        await self.db.delete_playlist(playlist_id)
        
        # Удаляем из контекста
        self.context_manager.clear_active_playlist(telegram_id)
        
        await message.answer(f"✅ Плейлист «{title}» удален из базы данных бота.")
        await self.db.log_action(telegram_id, "playlist_deleted", playlist_id, None)
    
    async def delete_track_start(self, message_or_query, state: FSMContext):
        """Начало удаления трека (FSM)."""
        """Начало удаления трека (FSM)."""
        # Определяем, откуда пришел запрос
        if isinstance(message_or_query, CallbackQuery):
            query = message_or_query
            message = query.message
            telegram_id = query.from_user.id
            # Извлекаем playlist_id из callback_data
            data = query.data
            try:
                playlist_id = int(data.split("_")[-1])
            except (ValueError, IndexError):
                await message.answer(
                    "❌ Ошибка: неверный формат данных.",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            await query.answer()
        else:
            message = message_or_query
            telegram_id = message.from_user.id
            playlist_id = None
        
        await self.db.ensure_user(telegram_id, message.from_user.username if hasattr(message.from_user, 'username') else None)
        
        # FSM диалог
        if not playlist_id:
            playlist_id = await self.context_manager.get_active_playlist_id(telegram_id)
        
        if not playlist_id:
            await message.answer(
                "❌ У вас нет активного плейлиста.\n\n"
                "💡 Используйте кнопки «📁 Мои плейлисты» или «📂 Общие плейлисты», чтобы выбрать плейлист.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Проверяем доступ
        if not await self.db.check_playlist_access(playlist_id, telegram_id, need_edit=True):
            playlist = await self.db.get_playlist(playlist_id)
            title = playlist.get("title") or "плейлист" if playlist else "плейлист"
            await message.answer(
                f"❌ У вас нет прав на удаление треков из плейлиста «{title}».\n\n"
                f"💡 Только создатель или пользователи с правами редактирования могут удалять треки.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Получаем информацию о плейлисте для показа количества треков
        tracks = await self.playlist_service.get_playlist_tracks(playlist_id, telegram_id)
        if tracks is None:
            await message.answer(
                "❌ Не удалось загрузить плейлист.\n\n"
                "💡 Возможно, проблема с доступом к Яндекс.Музыке.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        total = len(tracks)
        
        if total == 0:
            await message.answer(
                "❌ Плейлист пуст. Нечего удалять.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Сохраняем playlist_id в состоянии FSM
        await state.update_data(delete_track_playlist_id=playlist_id, delete_track_total=total)
        
        playlist = await self.db.get_playlist(playlist_id)
        playlist_title = playlist.get("title") or "плейлист" if playlist else "плейлист"
        
        await message.answer(
            f"🗑️ Удаление трека из плейлиста «{playlist_title}»\n\n"
            f"В плейлисте {total} треков.\n\n"
            f"Введите номер трека для удаления (от 1 до {total}):\n\n"
            f"💡 Используйте /list, чтобы увидеть список треков с номерами.",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(DeleteTrackStates.waiting_track_number)
    
    async def delete_track_input(self, message: Message, state: FSMContext):
        """Обработка ввода номера трека для удаления."""
        import re
        telegram_id = message.from_user.id
        raw = message.text.strip()
        
        logger.info(f"delete_track_input вызван для пользователя {telegram_id}, текст: {raw}")
        
        # Проверка на отмену (fallback должен обработать, но на всякий случай)
        if raw in ["❌ Отмена", "отмена", "Отмена"] or raw.lower() in ["отмена", "/cancel", "/start"]:
            logger.info(f"Обнаружена отмена в delete_track_input")
            await self.cancel_operation(message, state)
            return
        
        # Валидация
        if not re.match(r"^\d+$", raw):
            await message.answer(
                "❌ Неверный формат. Укажите номер трека (число).\n\n"
                "💡 Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        index = int(raw)
        state_data = await state.get_data()
        playlist_id = state_data.get('delete_track_playlist_id')
        total = state_data.get('delete_track_total')
        
        if not playlist_id:
            await send_message(message, PLAYLIST_NOT_FOUND_ERROR, use_main_menu=True)
            await state.clear()
            return
        
        if index < 1 or index > total:
            await message.answer(
                f"❌ Номер трека вне диапазона.\n\n"
                f"💡 Доступные номера: 1..{total}\n"
                f"Введите номер еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await message.answer(
                "❌ Плейлист не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            await state.clear()
            return
        
        tracks = await self.playlist_service.get_playlist_tracks(playlist_id, telegram_id)
        if tracks is None:
            await message.answer(
                "❌ Не удалось загрузить плейлист.\n\n"
                "💡 Возможно, проблема с доступом к Яндекс.Музыке.",
                reply_markup=get_main_menu_keyboard()
            )
            await state.clear()
            return
        
        if index < 1 or index > len(tracks):
            await message.answer(
                f"❌ Номер трека вне диапазона.\n\n"
                f"💡 Доступные номера: 1..{len(tracks)}\n"
                f"Введите номер еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        # Получаем информацию о треке перед удалением
        item = tracks[index - 1]
        
        # Получаем клиент для создания YandexService
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        track_display = yandex_service.format_track(item)
        
        from_idx = index - 1
        to_idx = index - 1
        ok, err = await self.playlist_service.delete_track(playlist_id, from_idx, to_idx, telegram_id)
        
        if ok:
            track_info = f"«{track_display}»"
            await message.answer(
                f"✅ Трек №{index} {track_info} удалён из плейлиста.",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await message.answer(
                f"❌ Не удалось удалить трек: {err}\n\n"
                f"💡 Попробуйте еще раз или проверьте права доступа.",
                reply_markup=get_main_menu_keyboard()
            )
        
        # Очищаем состояние
        await state.clear()
    
    async def set_cover_start(self, query: CallbackQuery, state: FSMContext):
        """Начало установки обложки (FSM)."""
        telegram_id = query.from_user.id
        message = query.message
        await self.db.ensure_user(telegram_id, query.from_user.username)
        
        # Извлекаем playlist_id из callback_data
        data = query.data
        try:
            playlist_id = int(data.split("_")[-1])
        except (ValueError, IndexError):
            await message.answer(
                "❌ Ошибка: неверный формат данных.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # FSM диалог
        if not playlist_id:
            playlist_id = await self.context_manager.get_active_playlist_id(telegram_id)
        if not playlist_id:
            await message.answer(
                "❌ У вас нет активного плейлиста.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Проверяем, что плейлист существует
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await send_message(message, PLAYLIST_NOT_FOUND, use_main_menu=True)
            return
        
        if not await self.db.is_playlist_creator(playlist_id, telegram_id):
            await send_message(message, ONLY_CREATOR_CAN_CHANGE_COVER, use_main_menu=True)
            return
        
        await state.update_data(set_cover_playlist_id=playlist_id)
        await query.answer()
        
        await message.answer(
            "🖼️ Установка обложки плейлиста\n\n"
            "Отправьте фото для обложки плейлиста:",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(SetCoverStates.waiting_playlist_cover)
    
    async def set_cover_input(self, message: Message, state: FSMContext):
        """Обработка ввода обложки."""
        telegram_id = message.from_user.id
        
        # Проверяем, что это фото
        if not message.photo:
            await message.answer(
                "❌ Пожалуйста, отправьте фото для обложки.\n\n"
                "💡 Попробуйте еще раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        state_data = await state.get_data()
        playlist_id = state_data.get('set_cover_playlist_id')
        if not playlist_id:
            await send_message(message, PLAYLIST_NOT_FOUND_ERROR, use_main_menu=True)
            await state.clear()
            return
        
        # Получаем фото (берем самое большое)
        photo = message.photo[-1]
        
        await message.answer("⏳ Загружаю обложку...")
        
        # Скачиваем фото
        file = await message.bot.get_file(photo.file_id)
        image_bytes = await message.bot.download_file(file.file_path)
        # Читаем байты из BytesIO
        image_file = image_bytes.read() if hasattr(image_bytes, 'read') else image_bytes
        
        # Устанавливаем обложку
        ok, err = await self.playlist_service.set_playlist_cover(playlist_id, image_file, telegram_id)
        
        if ok:
            await message.answer(
                "✅ Обложка плейлиста успешно установлена!",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await message.answer(
                f"❌ Не удалось установить обложку: {err}\n\n"
                f"💡 Попробуйте еще раз или проверьте права доступа.",
                reply_markup=get_main_menu_keyboard()
            )
        
        # Очищаем состояние
        await state.clear()
    
    async def cancel_operation(self, message: Message, state: FSMContext):
        """Отмена текущей операции."""
        # Очищаем состояние FSM
        await state.clear()
        
        await message.answer(
            "❌ Операция отменена.",
            reply_markup=get_main_menu_keyboard()
        )
    
    async def buy_limit(self, message: Message):
        """Команда для покупки расширенного лимита."""
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        # Получаем доступные планы
        payment_service = PaymentService(self.db)
        plans = payment_service.get_available_plans()
        
        # Получаем текущий лимит пользователя
        current_limit = await self.db.get_user_playlist_limit(telegram_id)
        current_count = await self.db.count_user_playlists(telegram_id)
        limit_text = "безлимитно" if current_limit == -1 else f"{current_limit} плейлистов"
        
        # Формируем клавиатуру с тарифами
        keyboard = []
        for plan_id, plan_data in plans.items():
            button_text = f"⭐ {plan_data['name']} — {plan_data['stars']} Stars"
            keyboard.append([InlineKeyboardButton(
                text=button_text,
                callback_data=f"buy_{plan_id}"
            )])
        keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment")])
        
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await message.answer(
            f"💳 Выберите тарифный план:\n\n"
            f"📊 Текущий лимит: {limit_text}\n"
            f"📁 Создано плейлистов: {current_count}\n\n"
            f"⭐ Stars — это внутренняя валюта Telegram\n"
            f"Вы можете купить Stars прямо в приложении Telegram",
            reply_markup=reply_markup
        )
    
    async def handle_pre_checkout_query(self, pre_checkout_query: PreCheckoutQuery):
        """Обработка pre_checkout_query."""
        telegram_id = pre_checkout_query.from_user.id
        
        # Проверяем платеж
        payment_service = PaymentService(self.db)
        payment = await self.db.get_payment_by_payload(pre_checkout_query.invoice_payload)
        
        if not payment or payment['status'] != 'pending':
            # Отклоняем платеж
            await pre_checkout_query.bot.answer_pre_checkout_query(
                pre_checkout_query_id=pre_checkout_query.id,
                ok=False,
                error_message="Платеж не найден или уже обработан"
            )
            return
        
        # Проверяем сумму
        if payment['stars_amount'] != pre_checkout_query.total_amount:
            await pre_checkout_query.bot.answer_pre_checkout_query(
                pre_checkout_query_id=pre_checkout_query.id,
                ok=False,
                error_message="Сумма платежа не совпадает"
            )
            return
        
        # Подтверждаем платеж
        await pre_checkout_query.bot.answer_pre_checkout_query(
            pre_checkout_query_id=pre_checkout_query.id,
            ok=True
        )
    
    async def handle_successful_payment(self, message: Message, successful_payment: SuccessfulPayment):
        """Обработка успешного платежа."""
        telegram_id = message.from_user.id
        
        payment_service = PaymentService(self.db)
        success = payment_service.process_successful_payment(
            telegram_id=telegram_id,
            invoice_payload=successful_payment.invoice_payload,
            stars_amount=successful_payment.total_amount
        )
        
        if success:
            # Получаем информацию о новой подписке
            subscription = await self.db.get_active_subscription(telegram_id)
            if subscription:
                plan = payment_service.get_available_plans()[subscription['subscription_type']]
                limit = plan['limit']
                limit_text = "безлимитно" if limit == -1 else f"{limit} плейлистов"
                
                await message.answer(
                    f"✅ Платеж успешно обработан!\n\n"
                    f"🎉 Ваш лимит увеличен до {limit_text}\n\n"
                    f"Теперь вы можете создавать больше плейлистов!",
                    reply_markup=get_main_menu_keyboard()
                )
                await self.db.log_action(telegram_id, "subscription_purchased", None, f"type={subscription['subscription_type']}")
        else:
            await message.answer(
                "❌ Произошла ошибка при обработке платежа.\n"
                "Пожалуйста, свяжитесь с поддержкой.",
                reply_markup=get_main_menu_keyboard()
            )

