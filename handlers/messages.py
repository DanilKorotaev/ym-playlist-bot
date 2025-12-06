"""
Обработчики текстовых сообщений для Telegram бота.
"""
import logging
import asyncio
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from database import DatabaseInterface
from yandex_client_manager import YandexClientManager
from utils.context import UserContextManager
from utils.message_helpers import (
    send_message,
    NO_ACTIVE_PLAYLIST,
    NO_ADD_PERMISSION,
    LOADING_PLAYLIST,
    LOADING_ALBUM,
    LOADING_TRACK
)
from services.link_parser import parse_track_link, parse_playlist_link, parse_album_link, parse_share_link
from services.yandex_service import YandexService
from services.playlist_service import PlaylistService
from .keyboards import get_main_menu_keyboard

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Класс с обработчиками текстовых сообщений."""
    
    def __init__(
        self,
        db: DatabaseInterface,
        client_manager: YandexClientManager,
        context_manager: UserContextManager,
        command_handlers=None
    ):
        """
        Инициализация обработчиков.
        
        Args:
            db: Интерфейс базы данных
            client_manager: Менеджер клиентов Яндекс.Музыки
            context_manager: Менеджер контекста пользователей
            command_handlers: Обработчики команд (опционально, создается автоматически если не передан)
        """
        self.db = db
        self.client_manager = client_manager
        self.context_manager = context_manager
        self.playlist_service = PlaylistService(db, client_manager)
        self._command_handlers = command_handlers
    
    @property
    def command_handlers(self):
        """Ленивая инициализация command_handlers для избежания циклических импортов."""
        if self._command_handlers is None:
            from .commands import CommandHandlers
            self._command_handlers = CommandHandlers(self.db, self.client_manager, self.context_manager)
        return self._command_handlers
    
    async def handle_menu_buttons(self, message: Message, state: FSMContext):
        """Обработка нажатий на кнопки меню."""
        text = message.text.strip()
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        # Проверяем, не находится ли пользователь в состоянии FSM
        # Если да, то не обрабатываем кнопки меню (кроме "❌ Отмена", которая обрабатывается FSM fallback)
        state_data = await state.get_data()
        if state_data.get('delete_track_playlist_id') is not None:
            # Пользователь в процессе удаления трека - FSM должен обработать
            return
        if state_data.get('edit_playlist_id') is not None:
            # Пользователь в процессе редактирования названия - FSM должен обработать
            return
        if state_data.get('set_cover_playlist_id') is not None:
            # Пользователь в процессе установки обложки - FSM должен обработать
            return
        
        if text == "📁 Мои плейлисты":
            await self.command_handlers.my_playlists(message)
        elif text == "📂 Общие плейлисты":
            await self.command_handlers.shared_playlists(message)
        elif text == "📋 Список треков":
            await self.command_handlers.show_list(message)
        elif text == "ℹ️ Информация":
            await self.command_handlers.playlist_info(message)
        elif text == "🏠 Главное меню":
            await self.command_handlers.main_menu(message)
        # Кнопка "➕ Создать плейлист" обрабатывается FSM
        # Кнопка "❌ Отмена" обрабатывается fallback'ами FSM
        else:
            # Если это не кнопка меню, пытаемся обработать как ссылку
            await self.add_command(message, state)
    
    async def add_command(self, message: Message, state: FSMContext):
        """Обработка ссылок на треки/альбомы/плейлисты."""
        telegram_id = message.from_user.id
        await self.db.ensure_user(telegram_id, message.from_user.username)
        
        # Проверяем, не находится ли пользователь в состоянии FSM
        # Если да, то не обрабатываем сообщение здесь (FSM должен обработать)
        state_data = await state.get_data()
        if state_data.get('delete_track_playlist_id') is not None:
            # Пользователь в процессе удаления трека - не обрабатываем
            return
        if state_data.get('edit_playlist_id') is not None:
            # Пользователь в процессе редактирования названия - не обрабатываем
            return
        if state_data.get('set_cover_playlist_id') is not None:
            # Пользователь в процессе установки обложки - не обрабатываем
            return
        
        text = (message.text or "").strip()
        
        # Получаем активный плейлист
        playlist_id = await self.context_manager.get_active_playlist_id(telegram_id)
        
        if not playlist_id:
            await send_message(message, NO_ACTIVE_PLAYLIST, use_main_menu=True)
            return
        
        # Проверяем доступ
        if not await self.db.check_playlist_access(playlist_id, telegram_id, need_add=True):
            playlist = await self.db.get_playlist(playlist_id)
            title = playlist.get("title") or "плейлист" if playlist else "плейлист"
            await send_message(
                message,
                NO_ADD_PERMISSION.format(title=title),
                use_main_menu=True
            )
            return
        
        # Показываем информацию об активном плейлисте
        playlist = await self.db.get_playlist(playlist_id)
        playlist_title = playlist.get("title") or "плейлист" if playlist else "плейлист"
        
        client = await self.client_manager.get_client(telegram_id)
        yandex_service = YandexService(client)
        
        # Трек
        tr = parse_track_link(text)
        if tr:
            try:
                await send_message(message, LOADING_TRACK)
                track_obj = yandex_service.get_track(tr)
                if not track_obj:
                    await message.answer(
                        f"❌ Не удалось получить трек.\n\n"
                        f"💡 Проверьте правильность ссылки."
                    )
                    return
                
                album_obj = track_obj.albums[0] if track_obj.albums else None
                if not album_obj:
                    await message.answer(
                        f"❌ Не удалось получить альбом для трека.\n\n"
                        f"💡 Проверьте правильность ссылки."
                    )
                    return
                
                ok, err = await self.playlist_service.add_track(playlist_id, track_obj.id, album_obj.id, telegram_id)
                if ok:
                    track_display = yandex_service.format_track(track_obj)
                    # Получаем информацию о том, куда был добавлен трек
                    playlist = await self.db.get_playlist(playlist_id)
                    insert_position = playlist.get("insert_position", "end") if playlist else "end"
                    position_text = "в начало" if insert_position == "start" else "в конец"
                    await message.answer(
                        f"✅ Трек добавлен {position_text} плейлиста «{playlist_title}»:\n"
                        f"🎵 «{track_display}»"
                    )
                else:
                    await message.answer(
                        f"❌ Не удалось добавить трек: {err}\n\n"
                        f"💡 Проверьте права доступа к плейлисту."
                    )
            except Exception as e:
                logger.exception(f"Error in add track: {e}")
                await message.answer(
                    f"❌ Ошибка при добавлении трека: {str(e)}\n\n"
                    f"💡 Проверьте правильность ссылки и попробуйте еще раз."
                )
            return
        
        # Плейлист
        owner, pid = parse_playlist_link(text)
        if pid:
            await send_message(message, LOADING_PLAYLIST)
            pl_obj, err = yandex_service.get_playlist(pid, owner)
            if pl_obj is None:
                await message.answer(
                    f"❌ Не удалось получить плейлист: {err}\n\n"
                    f"💡 Проверьте правильность ссылки."
                )
                return
            added = 0
            tracks_list = getattr(pl_obj, "tracks", []) or []
            total = len(tracks_list)
            
            for item in tracks_list:
                tr_id, album_id = yandex_service.extract_track_info(item)
                if tr_id is None or album_id is None:
                    continue
                ok, err = await self.playlist_service.add_track(playlist_id, tr_id, album_id, telegram_id)
                if ok:
                    added += 1
            
            if added > 0:
                await message.answer(
                    f"✅ Добавлено {added} из {total} треков в «{playlist_title}»."
                )
            else:
                await message.answer(
                    f"⚠️ Не удалось добавить треки из плейлиста.\n\n"
                    f"💡 Возможно, все треки уже есть в плейлисте или возникла ошибка."
                )
            return
        
        # Альбом
        alb_id = parse_album_link(text)
        if alb_id:
            await send_message(message, LOADING_ALBUM)
            tracks = yandex_service.get_album_tracks(alb_id)
            if not tracks:
                await message.answer(
                    "❌ Не удалось получить альбом или треки.\n\n"
                    "💡 Проверьте правильность ссылки."
                )
                return
            added = 0
            total = len(tracks)
            
            for t in tracks:
                tr_id, album_id = yandex_service.extract_track_info(t)
                if tr_id is None or album_id is None:
                    continue
                ok, err = await self.playlist_service.add_track(playlist_id, tr_id, album_id, telegram_id)
                if ok:
                    added += 1
            
            if added > 0:
                await message.answer(
                    f"✅ Добавлено {added} из {total} треков из альбома в «{playlist_title}»."
                )
            else:
                await message.answer(
                    f"⚠️ Не удалось добавить треки из альбома.\n\n"
                    f"💡 Возможно, все треки уже есть в плейлисте или возникла ошибка."
                )
            return
        
        # Ссылка на шаринг плейлиста
        share_token = parse_share_link(text)
        if share_token:
            playlist = await self.db.get_playlist_by_share_token(share_token)
            if playlist:
                await self.db.grant_playlist_access(playlist["id"], telegram_id, can_add=True)
                # Устанавливаем как активный
                self.context_manager.set_active_playlist(telegram_id, playlist["id"])
                await message.answer(
                    f"✅ Вы получили доступ к плейлисту «{playlist.get('title', 'Без названия')}»!\n\n"
                    f"Теперь вы можете добавлять треки в этот плейлист.",
                    reply_markup=get_main_menu_keyboard()
                )
                await self.db.log_action(telegram_id, "playlist_shared_access", playlist["id"], f"via_token={share_token}")
                return
        
        await message.answer(
            "❌ Не удалось распознать ссылку.\n\n"
            "📋 Поддерживаемые форматы:\n"
            "• Трек: music.yandex.ru/track/...\n"
            "• Плейлист: music.yandex.ru/users/.../playlists/...\n"
            "• Альбом: music.yandex.ru/album/...\n"
            "• Ссылка на шаринг плейлиста\n\n"
            f"💡 Активный плейлист: «{playlist_title}»",
            reply_markup=get_main_menu_keyboard()
        )

