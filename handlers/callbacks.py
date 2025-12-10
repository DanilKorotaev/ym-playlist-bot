"""
Обработчики callback query для Telegram бота.
"""
import logging
import asyncio
from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice

from database import DatabaseInterface
from yandex_client_manager import YandexClientManager
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
from services.playlist_service import PlaylistService
from services.yandex_service import YandexService
from .keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)


class CallbackHandlers:
    """Класс с обработчиками callback query."""
    
    def __init__(
        self,
        db: DatabaseInterface,
        context_manager: UserContextManager,
        client_manager: YandexClientManager
    ):
        """
        Инициализация обработчиков.
        
        Args:
            db: Интерфейс базы данных
            context_manager: Менеджер контекста пользователей
            client_manager: Менеджер клиентов Яндекс.Музыки
        """
        self.db = db
        self.context_manager = context_manager
        self.client_manager = client_manager
        self.playlist_service = PlaylistService(db, client_manager)
    
    async def button_callback(self, query: CallbackQuery):
        """
        Роутер для обработки нажатий на inline-кнопки.
        
        Перенаправляет вызовы на соответствующие методы-обработчики
        в зависимости от префикса callback_data.
        """
        await query.answer()
        
        telegram_id = query.from_user.id
        data = query.data
        
        if data.startswith("select_playlist_"):
            playlist_id = int(data.split("_")[-1])
            await self._handle_select_playlist(query, playlist_id, telegram_id)
        elif data.startswith("delete_playlist_"):
            playlist_id = int(data.split("_")[-1])
            await self._handle_delete_playlist(query, playlist_id, telegram_id)
        elif data.startswith("edit_playlist_"):
            playlist_id = int(data.split("_")[-1])
            await self._handle_edit_playlist(query, playlist_id, telegram_id)
        elif data.startswith("toggle_insert_position_"):
            playlist_id = int(data.split("_")[-1])
            await self._handle_toggle_insert_position(query, playlist_id, telegram_id)
        elif data.startswith("buy_"):
            plan_id = data.replace("buy_", "")
            await self._handle_buy_payment(query, telegram_id, plan_id)
        elif data == "cancel_payment":
            await self._handle_cancel_payment(query)
        elif data.startswith("list_page_"):
            # Формат: list_page_<playlist_id>_<page>
            parts = data.split("_")
            if len(parts) >= 4:
                playlist_id = int(parts[2])
                page = int(parts[3])
                await self._handle_list_page(query, playlist_id, page, telegram_id)
        # edit_name_ и delete_track_ обрабатываются через FSM entry points
    
    async def _handle_select_playlist(self, query: CallbackQuery, playlist_id: int, telegram_id: int):
        """Обработка выбора плейлиста."""
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await edit_message(query, PLAYLIST_NOT_FOUND, reply_markup=None)
            return
        
        # Проверяем доступ
        if not await self.db.check_playlist_access(playlist_id, telegram_id):
            await edit_message(query, NO_PLAYLIST_ACCESS, reply_markup=None)
            return
        
        # Устанавливаем как активный
        self.context_manager.set_active_playlist(telegram_id, playlist_id)
        
        title = playlist.get("title") or "Плейлист"
        is_creator = await self.db.is_playlist_creator(playlist_id, telegram_id)
        status = "Создатель" if is_creator else "Участник"
        
        await query.message.edit_text(
            f"✅ Выбран плейлист: «{title}»\n"
            f"👤 Статус: {status}\n\n"
            f"💡 Теперь отправляйте ссылки на треки, альбомы или плейлисты, чтобы добавить их в этот плейлист."
        )
    
    async def _handle_delete_playlist(self, query: CallbackQuery, playlist_id: int, telegram_id: int):
        """Обработка удаления плейлиста."""
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await edit_message(query, PLAYLIST_NOT_FOUND)
            return
        
        if not await self.db.is_playlist_creator(playlist_id, telegram_id):
            await edit_message(query, ONLY_CREATOR_CAN_DELETE)
            return
        
        title = playlist.get("title") or "плейлист"
        await self.db.delete_playlist(playlist_id)
        
        # Удаляем из контекста
        self.context_manager.clear_active_playlist(telegram_id)
        
        await query.message.edit_text(
            f"✅ Плейлист «{title}» удален из базы данных бота.\n\n"
            f"💡 Плейлист остался в Яндекс.Музыке, но бот больше не имеет к нему доступа.",
            reply_markup=None
        )
        await self.db.log_action(telegram_id, "playlist_deleted", playlist_id, None)
    
    async def _handle_edit_playlist(self, query: CallbackQuery, playlist_id: int, telegram_id: int):
        """Обработка открытия меню редактирования плейлиста."""
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await edit_message(query, PLAYLIST_NOT_FOUND)
            return
        
        if not await self.db.is_playlist_creator(playlist_id, telegram_id):
            await edit_message(query, ONLY_CREATOR_CAN_EDIT)
            return
        
        title = playlist.get("title") or "Плейлист"
        reply_markup = self._create_edit_playlist_keyboard(playlist_id, playlist)
        
        await reply_to_message(
            query.message,
            f"✏️ Редактирование плейлиста «{title}»\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup
        )
    
    async def _handle_toggle_insert_position(self, query: CallbackQuery, playlist_id: int, telegram_id: int):
        """Обработка переключения позиции вставки треков."""
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await edit_message(query, PLAYLIST_NOT_FOUND)
            return
        
        if not await self.db.is_playlist_creator(playlist_id, telegram_id):
            await edit_message(query, ONLY_CREATOR_CAN_EDIT)
            return
        
        # Переключаем insert_position
        current_position = playlist.get("insert_position", "end")
        new_position = "start" if current_position == "end" else "end"
        
        # Обновляем в БД
        await self.db.update_playlist(playlist_id, insert_position=new_position)
        await self.db.log_action(telegram_id, "playlist_insert_position_changed", playlist_id, f"position={new_position}")
        
        # Обновляем плейлист для получения актуальных данных
        playlist["insert_position"] = new_position
        position_text = "в начало" if new_position == "start" else "в конец"
        
        # Обновляем сообщение с меню редактирования
        title = playlist.get("title") or "Плейлист"
        reply_markup = self._create_edit_playlist_keyboard(playlist_id, playlist)
        
        await query.message.edit_text(
            f"✏️ Редактирование плейлиста «{title}»\n\n"
            f"✅ Настройка изменена: треки теперь добавляются {position_text}.\n\n"
            f"Выберите действие:",
            reply_markup=reply_markup
        )
    
    async def _handle_buy_payment(self, query: CallbackQuery, telegram_id: int, plan_id: str):
        """Обработка покупки подписки."""
        payment_service = PaymentService(self.db)
        payment_data = await payment_service.create_payment(telegram_id, plan_id)
        
        if not payment_data:
            await query.answer("Ошибка при создании платежа", show_alert=True)
            return
        
        plan = payment_service.get_available_plans()[plan_id]
        
        # Создаем инвойс
        try:
            invoice_link = await query.bot.create_invoice_link(
                title=f"Расширенный лимит: {plan['name']}",
                description=f"Увеличьте лимит плейлистов до {plan['name']}",
                payload=payment_data['payload'],
                provider_token="",  # Не требуется для Stars
                currency="XTR",  # Telegram Stars
                prices=[LabeledPrice(label=plan['name'], amount=plan['stars'])]
            )
            
            # Отправляем сообщение с кнопкой оплаты
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="💳 Оплатить", url=invoice_link)
            ], [
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment")
            ]])
            
            await reply_to_message(
                query.message,
                f"💳 Оплата: {plan['name']}\n\n"
                f"💰 Стоимость: {plan['stars']} Stars\n\n"
                f"Нажмите кнопку ниже для оплаты:",
                reply_markup=keyboard
            )
            
            await query.answer()
        except Exception as e:
            logger.error(f"Ошибка при создании инвойса: {e}")
            await query.answer("Ошибка при создании платежа", show_alert=True)
    
    async def _handle_cancel_payment(self, query: CallbackQuery):
        """Обработка отмены покупки."""
        await query.answer()
        await reply_to_message(
            query.message,
            "❌ Покупка отменена.",
            use_main_menu=True
        )
    
    async def _handle_list_page(self, query: CallbackQuery, playlist_id: int, page: int, telegram_id: int):
        """Обработка навигации по страницам списка треков."""
        # Проверяем доступ
        if not await self.db.check_playlist_access(playlist_id, telegram_id):
            await query.answer("❌ Нет доступа к этому плейлисту", show_alert=True)
            return
        
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await query.answer("❌ Плейлист не найден", show_alert=True)
            return
        
        tracks = await self.playlist_service.get_playlist_tracks(playlist_id, telegram_id)
        if tracks is None:
            await query.answer("❌ Не удалось загрузить треки", show_alert=True)
            return
        
        if not tracks:
            await query.answer("❌ Плейлист пуст", show_alert=True)
            return
        
        # Получаем клиент для создания YandexService
        client = await self.client_manager.get_client_for_playlist(playlist_id)
        yandex_service = YandexService(client)
        
        # Форматируем страницу
        text, reply_markup = self._format_tracks_page(
            tracks, page, playlist.get("title") or "Плейлист", playlist_id, yandex_service
        )
        
        # Обновляем сообщение
        try:
            await query.message.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения со списком треков: {e}")
            await query.answer("❌ Ошибка при обновлении страницы", show_alert=True)
    
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
        # Импортируем константу из commands.py
        from .commands import TRACKS_PER_PAGE
        
        total_tracks = len(tracks)
        total_pages = (total_tracks + TRACKS_PER_PAGE - 1) // TRACKS_PER_PAGE
        
        # Проверяем валидность страницы
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
        
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
        
        keyboard = []
        
        # Кнопка "Открыть в плеере"
        from .keyboards import get_miniapp_inline_keyboard
        miniapp_keyboard = get_miniapp_inline_keyboard(button_text="🎵 Открыть в плеере")
        if miniapp_keyboard and miniapp_keyboard.inline_keyboard:
            keyboard.append(miniapp_keyboard.inline_keyboard[0])
        
        # Кнопки редактирования
        keyboard.extend([
            [InlineKeyboardButton(text="✏️ Изменить имя", callback_data=f"edit_name_{playlist_id}")],
            [InlineKeyboardButton(text="🖼️ Изменить/установить картинку", callback_data=f"set_cover_{playlist_id}")],
            [InlineKeyboardButton(text=f"📍 Добавление треков: {position_text}", callback_data=f"toggle_insert_position_{playlist_id}")],
            [InlineKeyboardButton(text="🗑️ Удалить плейлист", callback_data=f"delete_playlist_{playlist_id}")],
            [InlineKeyboardButton(text="🗑️ Удалить трек", callback_data=f"delete_track_{playlist_id}")]
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

