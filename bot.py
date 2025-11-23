"""
Telegram бот для управления плейлистами Яндекс.Музыки.
Поддерживает множественные плейлисты, шаринг и управление доступом.
"""
import re
import os
import json
import logging
import time
import urllib.parse
import secrets
import signal
import sys
from typing import Any, List, Tuple, Optional, Union, Dict
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext,
    CallbackQueryHandler, ConversationHandler
)
from yandex_music import Client
from yandex_music.exceptions import YandexMusicError

from database import create_database, DatabaseInterface
from yandex_client_manager import YandexClientManager

# Загружаем переменные окружения
load_dotenv()

# === Конфигурация ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")

# Проверка обязательных переменных
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен в переменных окружения")
if not YANDEX_TOKEN:
    raise ValueError("YANDEX_TOKEN не установлен в переменных окружения")

STATS_FILE = "stats.json"

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Подавляем некритичные предупреждения
logging.getLogger('telegram.utils.request').setLevel(logging.ERROR)
logging.getLogger('apscheduler').setLevel(logging.ERROR)

# === Инициализация БД и менеджера клиентов ===
# Создаем БД на основе DB_TYPE из переменных окружения (по умолчанию: sqlite)
db: DatabaseInterface = create_database()
client_manager = YandexClientManager(YANDEX_TOKEN, db)

# === Контекст пользователей (для хранения выбранного плейлиста) ===
user_contexts: Dict[int, Dict] = {}  # {telegram_id: {"current_playlist_id": ...}}

# === FSM States ===
WAITING_PLAYLIST_NAME = 1
WAITING_TOKEN = 2
WAITING_EDIT_NAME = 3
WAITING_TRACK_NUMBER = 4

# === Статистика ===
def load_stats() -> dict:
    if not os.path.exists(STATS_FILE):
        base = {
            "users": {},
            "links_count": {"track": 0, "playlist": 0, "album": 0},
            "commands": {},
            "total_messages": 0
        }
        save_stats(base)
        return base
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_stats(obj: dict):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# === Вспомогательные функции для UX ===
def get_main_menu_keyboard():
    """Возвращает клавиатуру главного меню."""
    return ReplyKeyboardMarkup(
        [
            ["📁 Мои плейлисты", "📂 Общие плейлисты"],
            ["➕ Создать плейлист", "📋 Список треков"],
            ["ℹ️ Информация", "🏠 Главное меню"]
        ],
        resize_keyboard=True
    )

def get_cancel_keyboard():
    """Возвращает клавиатуру с кнопкой отмены."""
    return ReplyKeyboardMarkup(
        [["❌ Отмена"]],
        resize_keyboard=True
    )

def get_active_playlist_info(telegram_id: int) -> Optional[str]:
    """Возвращает информацию об активном плейлисте или None."""
    if telegram_id in user_contexts and "current_playlist_id" in user_contexts[telegram_id]:
        playlist_id = user_contexts[telegram_id]["current_playlist_id"]
        playlist = db.get_playlist(playlist_id)
        if playlist:
            title = playlist.get("title") or "Без названия"
            return f"🎵 Активный плейлист: «{title}»"
    return None

def get_active_playlist_id(telegram_id: int) -> Optional[int]:
    """Возвращает ID активного плейлиста или None."""
    if telegram_id in user_contexts and "current_playlist_id" in user_contexts[telegram_id]:
        return user_contexts[telegram_id]["current_playlist_id"]
    # Пытаемся взять первый доступный плейлист
    playlists = db.get_user_playlists(telegram_id)
    if playlists:
        playlist_id = playlists[0]["id"]
        if telegram_id not in user_contexts:
            user_contexts[telegram_id] = {}
        user_contexts[telegram_id]["current_playlist_id"] = playlist_id
        return playlist_id
    return None

def cancel_operation(update: Update, context: CallbackContext) -> int:
    """Отмена текущей операции."""
    # Очищаем контекст FSM
    context.user_data.pop('delete_track_playlist_id', None)
    context.user_data.pop('delete_track_total', None)
    context.user_data.pop('edit_playlist_id', None)
    
    update.effective_message.reply_text(
        "❌ Операция отменена.",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END

def record_message_stats(update: Update, kind: str, added_count: int = 0, removed_count: int = 0):
    stats = load_stats()
    user = update.effective_user
    uid = str(user.id)
    if uid not in stats["users"]:
        stats["users"][uid] = {"username": user.username or "", "added": 0, "removed": 0, "messages": []}
    stats["total_messages"] = stats.get("total_messages", 0) + 1
    stats["users"][uid]["messages"].append({
        "time": int(time.time()),
        "text": update.effective_message.text if update.effective_message else "",
        "kind": kind,
        "added": added_count,
        "removed": removed_count
    })
    if added_count:
        stats["users"][uid]["added"] = stats["users"][uid].get("added", 0) + added_count
    if removed_count:
        stats["users"][uid]["removed"] = stats["users"][uid].get("removed", 0) + removed_count
    if kind in stats.get("links_count", {}):
        stats["links_count"][kind] = stats["links_count"].get(kind, 0) + 1
    save_stats(stats)

# === Парсеры ссылок ===
def parse_track_link(link: str) -> Optional[Any]:
    if not link:
        return None
    m = re.search(r"track/(\d+)", link)
    if m:
        return int(m.group(1))
    m = re.search(r"track/([0-9a-fA-F-]{8,})", link)
    if m:
        return m.group(1)
    m = re.match(r"^\d+$", link.strip())
    if m:
        return int(link.strip())
    return None

def parse_playlist_link(link: str) -> Tuple[Optional[str], Optional[str]]:
    """Возвращает (owner, playlist_id)."""
    if not link:
        return None, None
    m = re.search(r"users/([^/]+)/playlists/([0-9a-fA-F-]+)", link)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"/playlists?/([0-9a-fA-F-]+)", link)
    if m:
        return None, m.group(1)
    return None, None

def parse_album_link(link: str) -> Optional[Any]:
    if not link:
        return None
    m = re.search(r"album/(\d+)", link)
    if m:
        return int(m.group(1))
    m = re.search(r"album/([0-9a-fA-F-]+)", link)
    if m:
        return m.group(1)
    return None

def parse_share_link(link: str) -> Optional[str]:
    """Парсит ссылку вида https://t.me/bot?start=TOKEN или просто TOKEN."""
    if not link:
        return None
    # Если это полная ссылка
    m = re.search(r"[?&]start=([A-Za-z0-9_-]+)", link)
    if m:
        return m.group(1)
    # Если это просто токен (безопасные символы)
    if re.match(r"^[A-Za-z0-9_-]+$", link.strip()):
        return link.strip()
    return None

# === Yandex-helpers ===
def _get_album_tracks(client: Client, album_id) -> List[Any]:
    try:
        if hasattr(client, "albums_with_tracks"):
            alb = client.albums_with_tracks(album_id)
        else:
            if hasattr(client, "albums"):
                maybe = client.albums([album_id])
                alb = maybe[0] if isinstance(maybe, list) and maybe else maybe
            else:
                alb = client.album(album_id)
        if alb is None:
            return []
        if hasattr(alb, "tracks") and alb.tracks:
            return alb.tracks
        vols = getattr(alb, "volumes", None)
        if vols:
            tracks = []
            for vol in vols:
                tracks.extend(vol)
            return tracks
        for attr in ["tracklist", "items", "results"]:
            maybe = getattr(alb, attr, None)
            if maybe and isinstance(maybe, list):
                return maybe
    except YandexMusicError as e:
        logger.exception("Ошибка при получении альбома: %s", e)
    return []

def _fetch_playlist_obj(client: Client, owner: Optional[str], pid: str) -> Tuple[Optional[Any], Optional[str]]:
    """Получить объект плейлиста."""
    if owner:
        try:
            pl = client.users_playlists(pid, owner)
            return pl, None
        except Exception as e:
            logger.debug("users_playlists(pid,owner) failed: %s", e)
    try:
        pl = client.users_playlists(pid)
        return pl, None
    except Exception as e:
        logger.debug("users_playlists(pid) failed: %s", e)
    return None, f"Не удалось получить плейлист {pid}"

def get_playlist_obj_from_db(playlist_id: int, telegram_id: int) -> Optional[Any]:
    """Получить объект плейлиста из БД."""
    playlist = db.get_playlist(playlist_id)
    if not playlist:
        return None
    client = client_manager.get_client_for_playlist(playlist_id)
    try:
        pl = client.users_playlists(playlist["playlist_kind"], playlist["owner_id"])
        return pl
    except Exception as e:
        logger.exception(f"Ошибка получения плейлиста {playlist_id}: {e}")
        return None

# === API вставки / удаления ===
def insert_track_api(playlist_id: int, track_id: Any, album_id: Any, telegram_id: int) -> Tuple[bool, Optional[str]]:
    """Добавить трек в плейлист."""
    playlist = db.get_playlist(playlist_id)
    if not playlist:
        return False, "Плейлист не найден."
    
    # Проверяем права доступа
    if not db.check_playlist_access(playlist_id, telegram_id, need_add=True):
        return False, "У вас нет прав на добавление треков в этот плейлист."
    
    client = client_manager.get_client_for_playlist(playlist_id)
    last_err = None
    
    for attempt in range(2):
        try:
            pl = client.users_playlists(playlist["playlist_kind"], playlist["owner_id"])
            if pl is None:
                return False, "Не удалось получить плейлист."
            revision = getattr(pl, "revision", 1)
            client.users_playlists_insert_track(
                playlist["playlist_kind"], track_id, album_id, 
                at=0, revision=revision, user_id=playlist["owner_id"]
            )
            # Логируем действие
            db.log_action(telegram_id, "track_added", playlist_id, f"track_id={track_id}")
            return True, None
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            logger.debug("insert attempt failed: %s", e)
            if "wrong-revision" in msg or "revision" in msg:
                continue
    return False, f"Ошибка вставки: {last_err}"

def delete_track_api(playlist_id: int, from_idx: int, to_idx: int, telegram_id: int) -> Tuple[bool, Optional[str]]:
    """Удалить трек из плейлиста."""
    playlist = db.get_playlist(playlist_id)
    if not playlist:
        return False, "Плейлист не найден."
    
    # Проверяем права доступа
    if not db.check_playlist_access(playlist_id, telegram_id, need_edit=True):
        return False, "У вас нет прав на удаление треков из этого плейлиста."
    
    client = client_manager.get_client_for_playlist(playlist_id)
    last_err = None
    
    for attempt in range(2):
        try:
            pl = client.users_playlists(playlist["playlist_kind"], playlist["owner_id"])
            if pl is None:
                return False, "Не удалось получить плейлист."
            revision = getattr(pl, "revision", 1)
            diff = [{"op": "delete", "from": from_idx, "to": to_idx}]
            diff_str = json.dumps(diff, ensure_ascii=False).replace(" ", "")
            diff_encoded = urllib.parse.quote(diff_str, safe="")
            url = f"{client.base_url}/users/{playlist['owner_id']}/playlists/{playlist['playlist_kind']}/change-relative?diff={diff_encoded}&revision={revision}"
            result = client._request.post(url)
            # Логируем действие
            db.log_action(telegram_id, "track_deleted", playlist_id, f"from={from_idx}, to={to_idx}")
            return True, "Трек успешно удалён." if result else "Запрос выполнен, но ответ пустой."
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            logger.debug("delete attempt failed: %s", e)
            if "wrong-revision" in msg or "revision" in msg:
                continue
    return False, f"Ошибка удаления: {last_err}"

# === Команды бота ===
def start(update: Update, context: CallbackContext):
    """Команда /start."""
    telegram_id = update.effective_user.id
    username = update.effective_user.username
    db.ensure_user(telegram_id, username)
    
    # Проверяем, есть ли параметр start (для шаринга плейлистов)
    if context.args:
        share_token = context.args[0]
        playlist = db.get_playlist_by_share_token(share_token)
        if playlist:
            # Предоставляем доступ к плейлисту
            db.grant_playlist_access(playlist["id"], telegram_id, can_add=True)
            # Устанавливаем как активный
            if telegram_id not in user_contexts:
                user_contexts[telegram_id] = {}
            user_contexts[telegram_id]["current_playlist_id"] = playlist["id"]
            
            update.effective_message.reply_text(
                f"✅ Вы получили доступ к плейлисту «{playlist.get('title', 'Без названия')}»!\n\n"
                f"Теперь вы можете добавлять треки в этот плейлист, отправляя ссылки на треки, альбомы или плейлисты.",
                reply_markup=get_main_menu_keyboard()
            )
            db.log_action(telegram_id, "playlist_shared_access", playlist["id"], f"via_token={share_token}")
            return
    
    # Показываем информацию об активном плейлисте, если есть
    active_info = get_active_playlist_info(telegram_id)
    
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
    db.log_action(telegram_id, "command_start", None, None)

def main_menu(update: Update, context: CallbackContext):
    """Главное меню."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    active_info = get_active_playlist_info(telegram_id)
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

def create_playlist_start(update: Update, context: CallbackContext) -> int:
    """Начало создания плейлиста (FSM)."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    # Если команда вызвана с аргументами (старый способ)
    if context.args:
        title = " ".join(context.args)
        if len(title) > 100:
            update.effective_message.reply_text(
                "❌ Название плейлиста слишком длинное (максимум 100 символов).",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        update.effective_message.reply_text("⏳ Создаю плейлист...")
        result = client_manager.create_playlist(telegram_id, title)
        
        if result:
            playlist_id = result["id"]
            share_token = result["share_token"]
            share_link = f"https://t.me/{context.bot.username}?start={share_token}"
            
            if telegram_id not in user_contexts:
                user_contexts[telegram_id] = {}
            user_contexts[telegram_id]["current_playlist_id"] = playlist_id
            
            update.effective_message.reply_text(
                f"✅ Плейлист «{title}» создан!\n\n"
                f"🔗 Ссылка для шаринга:\n{share_link}\n\n"
                f"Отправьте эту ссылку другим пользователям, чтобы они могли добавлять треки в ваш плейлист.",
                reply_markup=get_main_menu_keyboard()
            )
            db.log_action(telegram_id, "playlist_created", playlist_id, f"title={title}")
        else:
            update.effective_message.reply_text(
                "❌ Не удалось создать плейлист. Проверьте токен Яндекс.Музыки.\n\n"
                "Используйте /set_token для установки своего токена.",
                reply_markup=get_main_menu_keyboard()
            )
        return ConversationHandler.END
    
    # Новый способ - FSM диалог
    update.effective_message.reply_text(
        "📝 Создание нового плейлиста\n\n"
        "Введите название плейлиста (максимум 100 символов):\n\n"
        "💡 Пример: Моя музыка",
        reply_markup=get_cancel_keyboard()
    )
    return WAITING_PLAYLIST_NAME

def create_playlist_name(update: Update, context: CallbackContext) -> int:
    """Обработка названия плейлиста."""
    telegram_id = update.effective_user.id
    title = update.effective_message.text.strip()
    
    # Проверка на отмену
    if title.lower() in ["отмена", "❌ отмена", "/cancel", "/start"]:
        return cancel_operation(update, context)
    
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
    
    # Создаем плейлист
    update.effective_message.reply_text("⏳ Создаю плейлист...")
    result = client_manager.create_playlist(telegram_id, title)
    
    if result:
        playlist_id = result["id"]
        share_token = result["share_token"]
        share_link = f"https://t.me/{context.bot.username}?start={share_token}"
        
        if telegram_id not in user_contexts:
            user_contexts[telegram_id] = {}
        user_contexts[telegram_id]["current_playlist_id"] = playlist_id
        
        update.effective_message.reply_text(
            f"✅ Плейлист «{title}» успешно создан!\n\n"
            f"🔗 Ссылка для шаринга:\n{share_link}\n\n"
            f"Отправьте эту ссылку другим пользователям, чтобы они могли добавлять треки в ваш плейлист.",
            reply_markup=get_main_menu_keyboard()
        )
        db.log_action(telegram_id, "playlist_created", playlist_id, f"title={title}")
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

def my_playlists(update: Update, context: CallbackContext):
    """Команда /my_playlists."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    playlists = db.get_user_playlists(telegram_id, only_created=True)
    
    if not playlists:
        update.effective_message.reply_text(
            "📁 У вас пока нет созданных плейлистов.\n\n"
            "💡 Создайте новый плейлист, используя кнопку «➕ Создать плейлист» или команду /create_playlist",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Получаем активный плейлист
    active_id = get_active_playlist_id(telegram_id)
    
    lines = ["📁 Ваши плейлисты:\n"]
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
        lines.append(f"\n🎵 Активный плейлист отмечен")
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    update.effective_message.reply_text(
        "\n".join(lines),
        reply_markup=reply_markup
    )

def shared_playlists(update: Update, context: CallbackContext):
    """Команда /shared_playlists."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    playlists = db.get_shared_playlists(telegram_id)
    
    if not playlists:
        update.effective_message.reply_text(
            "📂 У вас пока нет общих плейлистов, куда вы добавляете треки.\n\n"
            "💡 Попросите у друзей ссылку на их плейлист или создайте свой и поделитесь ссылкой!",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Получаем активный плейлист
    active_id = get_active_playlist_id(telegram_id)
    
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

def playlist_info(update: Update, context: CallbackContext):
    """Команда /playlist_info."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    playlist_id = None
    if context.args:
        try:
            playlist_id = int(context.args[0])
        except ValueError:
            update.effective_message.reply_text(
                "❌ Неверный формат. Использование: /playlist_info [номер плейлиста]",
                reply_markup=get_main_menu_keyboard()
            )
            return
    else:
        playlist_id = get_active_playlist_id(telegram_id)
    
    if not playlist_id:
        update.effective_message.reply_text(
            "❌ У вас нет активного плейлиста.\n\n"
            "💡 Используйте кнопки «📁 Мои плейлисты» или «📂 Общие плейлисты», чтобы выбрать плейлист.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    playlist = db.get_playlist(playlist_id)
    if not playlist:
        update.effective_message.reply_text(
            "❌ Плейлист не найден.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Проверяем доступ
    if not db.check_playlist_access(playlist_id, telegram_id):
        update.effective_message.reply_text(
            "❌ У вас нет доступа к этому плейлисту.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    title = playlist.get("title") or "Без названия"
    is_creator = db.is_playlist_creator(playlist_id, telegram_id)
    share_token = playlist.get("share_token")
    share_link = f"https://t.me/{context.bot.username}?start={share_token}" if share_token else None
    
    # Формируем ссылку на плейлист в Яндекс.Музыке
    owner_id = playlist.get("owner_id")
    playlist_kind = playlist.get("playlist_kind")
    yandex_link = None
    if owner_id and playlist_kind:
        yandex_link = f"https://music.yandex.ru/users/{owner_id}/playlists/{playlist_kind}"
    
    # Получаем информацию о количестве треков
    pl_obj = get_playlist_obj_from_db(playlist_id, telegram_id)
    tracks_count = 0
    if pl_obj:
        tracks = getattr(pl_obj, "tracks", []) or []
        tracks_count = len(tracks)
    
    lines = [
        f"📋 Информация о плейлисте\n",
        f"🎵 Название: {title}",
        f"👤 Ваш статус: {'Создатель' if is_creator else 'Участник'}",
        f"🎶 Треков: {tracks_count}",
    ]
    
    if yandex_link:
        lines.append(f"\n🔗 Плейлист в Яндекс.Музыке:\n{yandex_link}")
    
    if share_link:
        lines.append(f"\n🔗 Ссылка для шаринга:\n{share_link}")
        lines.append("\n💡 Отправьте эту ссылку другим пользователям, чтобы они могли добавлять треки.")
    
    # Создаем inline-кнопки для действий
    keyboard = []
    
    # Кнопки для создателя
    if is_creator:
        keyboard.append([InlineKeyboardButton("✏️ Изменить название", callback_data=f"edit_name_{playlist_id}")])
        keyboard.append([InlineKeyboardButton("🗑️ Удалить плейлист", callback_data=f"delete_playlist_{playlist_id}")])
    
    # Кнопка удаления трека (для всех, кто имеет права редактирования, и если есть треки)
    can_edit = db.check_playlist_access(playlist_id, telegram_id, need_edit=True)
    if can_edit and tracks_count > 0:
        keyboard.append([InlineKeyboardButton("🗑️ Удалить трек", callback_data=f"delete_track_{playlist_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    update.effective_message.reply_text(
        "\n".join(lines),
        reply_markup=reply_markup
    )

def show_list(update: Update, context: CallbackContext):
    """Команда /list."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    playlist_id = None
    if context.args:
        try:
            playlist_id = int(context.args[0])
        except ValueError:
            update.effective_message.reply_text(
                "❌ Неверный формат. Использование: /list [номер плейлиста]",
                reply_markup=get_main_menu_keyboard()
            )
            return
    else:
        playlist_id = get_active_playlist_id(telegram_id)
    
    if not playlist_id:
        update.effective_message.reply_text(
            "❌ У вас нет активного плейлиста.\n\n"
            "💡 Используйте кнопки «📁 Мои плейлисты» или «📂 Общие плейлисты», чтобы выбрать плейлист.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    playlist = db.get_playlist(playlist_id)
    if not playlist:
        update.effective_message.reply_text(
            "❌ Плейлист не найден.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Проверяем доступ
    if not db.check_playlist_access(playlist_id, telegram_id):
        update.effective_message.reply_text(
            "❌ У вас нет доступа к этому плейлисту.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    pl_obj = get_playlist_obj_from_db(playlist_id, telegram_id)
    if pl_obj is None:
        update.effective_message.reply_text(
            "❌ Не удалось загрузить плейлист. Возможно, проблема с доступом к Яндекс.Музыке.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    tracks = getattr(pl_obj, "tracks", []) or []
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
    
    for i, item in enumerate(tracks, start=1):
        t = item.track if hasattr(item, "track") and item.track else item
        track_title = getattr(t, "title", None) or "Unknown"
        artists = []
        if getattr(t, "artists", None):
            artists = [a.name for a in getattr(t, "artists", []) if getattr(a, "name", None)]
        artist_line = " / ".join(artists) if artists else ""
        lines.append(f"{i}. {track_title}" + (f" — {artist_line}" if artist_line else ""))
    
    chunk = 50
    for i in range(0, len(lines), chunk):
        part = "\n".join(lines[i:i+chunk])
        update.effective_message.reply_text(part)

def set_token_start(update: Update, context: CallbackContext) -> int:
    """Начало установки токена (FSM)."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    # Если команда вызвана с аргументами (старый способ)
    if context.args:
        token = context.args[0].strip()
        
        if client_manager.set_user_token(telegram_id, token):
            update.effective_message.reply_text(
                "✅ Токен успешно установлен!\n\n"
                "Теперь ваши плейлисты будут создаваться в вашем аккаунте Яндекс.Музыки.",
                reply_markup=get_main_menu_keyboard()
            )
            db.log_action(telegram_id, "token_set", None, None)
        else:
            update.effective_message.reply_text(
                "❌ Не удалось установить токен. Проверьте правильность токена.",
                reply_markup=get_main_menu_keyboard()
            )
        return ConversationHandler.END
    
    # Новый способ - FSM диалог
    update.effective_message.reply_text(
        "🔑 Установка токена Яндекс.Музыки\n\n"
        "⚠️ ВНИМАНИЕ: Вы передаете боту свой токен на свой страх и риск!\n\n"
        "Токен можно получить здесь:\n"
        "https://yandex-music.readthedocs.io/en/main/token.html\n\n"
        "Введите ваш токен:",
        reply_markup=get_cancel_keyboard()
    )
    return WAITING_TOKEN

def set_token_input(update: Update, context: CallbackContext) -> int:
    """Обработка ввода токена."""
    telegram_id = update.effective_user.id
    token = update.effective_message.text.strip()
    
    # Проверка на отмену
    if token.lower() in ["отмена", "❌ отмена", "/cancel", "/start"]:
        return cancel_operation(update, context)
    
    # Валидация
    if not token:
        update.effective_message.reply_text(
            "❌ Токен не может быть пустым. Попробуйте еще раз:",
            reply_markup=get_cancel_keyboard()
        )
        return WAITING_TOKEN
    
    if client_manager.set_user_token(telegram_id, token):
        update.effective_message.reply_text(
            "✅ Токен успешно установлен!\n\n"
            "Теперь ваши плейлисты будут создаваться в вашем аккаунте Яндекс.Музыки.",
            reply_markup=get_main_menu_keyboard()
        )
        db.log_action(telegram_id, "token_set", None, None)
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

def edit_name_start(update: Update, context: CallbackContext) -> int:
    """Начало редактирования названия (FSM)."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
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
    
    # Если команда вызвана с аргументами (старый способ)
    if context.args:
        if not playlist_id:
            playlist_id = get_active_playlist_id(telegram_id)
        if not playlist_id:
            update.effective_message.reply_text(
                "❌ У вас нет активного плейлиста.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        if not db.is_playlist_creator(playlist_id, telegram_id):
            update.effective_message.reply_text(
                "❌ Только создатель плейлиста может изменять название.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        new_title = " ".join(context.args)
        if len(new_title) > 100:
            update.effective_message.reply_text(
                "❌ Название слишком длинное (максимум 100 символов).",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        db.update_playlist(playlist_id, title=new_title)
        update.effective_message.reply_text(
            f"✅ Название плейлиста изменено на «{new_title}»",
            reply_markup=get_main_menu_keyboard()
        )
        db.log_action(telegram_id, "playlist_name_edited", playlist_id, f"new_title={new_title}")
        context.user_data.pop('edit_playlist_id', None)
        return ConversationHandler.END
    
    # Новый способ - FSM диалог
    if not playlist_id:
        playlist_id = get_active_playlist_id(telegram_id)
    if not playlist_id:
        update.effective_message.reply_text(
            "❌ У вас нет активного плейлиста.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    # Проверяем, что плейлист существует
    playlist = db.get_playlist(playlist_id)
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
    
    if not db.is_playlist_creator(playlist_id, telegram_id):
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

def edit_name_input(update: Update, context: CallbackContext) -> int:
    """Обработка ввода нового названия."""
    telegram_id = update.effective_user.id
    new_title = update.effective_message.text.strip()
    
    # Проверка на отмену
    if new_title.lower() in ["отмена", "❌ отмена", "/cancel", "/start"]:
        return cancel_operation(update, context)
    
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
    
    db.update_playlist(playlist_id, title=new_title)
    update.effective_message.reply_text(
        f"✅ Название плейлиста изменено на «{new_title}»",
        reply_markup=get_main_menu_keyboard()
    )
    db.log_action(telegram_id, "playlist_name_edited", playlist_id, f"new_title={new_title}")
    
    # Очищаем контекст
    context.user_data.pop('edit_playlist_id', None)
    
    return ConversationHandler.END

def delete_playlist_cmd(update: Update, context: CallbackContext):
    """Команда /delete_playlist."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    # Получаем активный плейлист
    playlist_id = None
    if telegram_id in user_contexts and "current_playlist_id" in user_contexts[telegram_id]:
        playlist_id = user_contexts[telegram_id]["current_playlist_id"]
    else:
        playlists = db.get_user_playlists(telegram_id, only_created=True)
        if playlists:
            playlist_id = playlists[0]["id"]
    
    if not playlist_id:
        update.effective_message.reply_text("У вас нет активного плейлиста.")
        return
    
    # Проверяем, что пользователь - создатель
    if not db.is_playlist_creator(playlist_id, telegram_id):
        update.effective_message.reply_text("Только создатель плейлиста может удалять его.")
        return
    
    playlist = db.get_playlist(playlist_id)
    title = playlist.get("title") or "плейлист" if playlist else "плейлист"
    
    # Удаляем из БД (плейлист в Яндекс.Музыке остается, но мы теряем связь)
    db.delete_playlist(playlist_id)
    
    # Удаляем из контекста
    if telegram_id in user_contexts:
        user_contexts[telegram_id].pop("current_playlist_id", None)
    
    update.effective_message.reply_text(f"✅ Плейлист «{title}» удален из базы данных бота.")
    db.log_action(telegram_id, "playlist_deleted", playlist_id, None)

def delete_track_start(update: Update, context: CallbackContext) -> int:
    """Начало удаления трека (FSM)."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
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
    
    # Если команда вызвана с аргументами (старый способ - для обратной совместимости)
    if context.args:
        raw = context.args[0].strip()
        if not re.match(r"^\d+$", raw):
            update.effective_message.reply_text(
                "❌ Неверный формат. Укажите номер трека (число).\n\n"
                "💡 Используйте /list, чтобы увидеть номера треков.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        index = int(raw)
        playlist_id = get_active_playlist_id(telegram_id)
        
        if not playlist_id:
            update.effective_message.reply_text(
                "❌ У вас нет активного плейлиста.\n\n"
                "💡 Используйте кнопки «📁 Мои плейлисты» или «📂 Общие плейлисты», чтобы выбрать плейлист.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        if not db.check_playlist_access(playlist_id, telegram_id, need_edit=True):
            playlist = db.get_playlist(playlist_id)
            title = playlist.get("title") or "плейлист" if playlist else "плейлист"
            update.effective_message.reply_text(
                f"❌ У вас нет прав на удаление треков из плейлиста «{title}».\n\n"
                f"💡 Только создатель или пользователи с правами редактирования могут удалять треки.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        # Выполняем удаление
        playlist = db.get_playlist(playlist_id)
        if not playlist:
            update.effective_message.reply_text(
                "❌ Плейлист не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        pl_obj = get_playlist_obj_from_db(playlist_id, telegram_id)
        if pl_obj is None:
            update.effective_message.reply_text(
                "❌ Не удалось загрузить плейлист.\n\n"
                "💡 Возможно, проблема с доступом к Яндекс.Музыке.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        tracks = getattr(pl_obj, "tracks", []) or []
        total = len(tracks)
        if index < 1 or index > total:
            update.effective_message.reply_text(
                f"❌ Номер трека вне диапазона.\n\n"
                f"💡 Доступные номера: 1..{total}\n"
                f"Используйте /list, чтобы увидеть список треков.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        # Получаем информацию о треке перед удалением
        item = tracks[index - 1]
        t = item.track if hasattr(item, "track") and item.track else item
        track_title = getattr(t, "title", None) or "Unknown"
        
        from_idx = index - 1
        to_idx = index - 1
        ok, err = delete_track_api(playlist_id, from_idx, to_idx, telegram_id)
        
        if ok:
            record_message_stats(update, kind="delete_track", removed_count=1)
            update.effective_message.reply_text(
                f"✅ Трек №{index} «{track_title}» удалён из плейлиста.",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            update.effective_message.reply_text(
                f"❌ Не удалось удалить трек: {err}\n\n"
                f"💡 Попробуйте еще раз или проверьте права доступа.",
                reply_markup=get_main_menu_keyboard()
            )
        return ConversationHandler.END
    
    # Новый способ - FSM диалог
    if not playlist_id:
        playlist_id = get_active_playlist_id(telegram_id)
    
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
    if not db.check_playlist_access(playlist_id, telegram_id, need_edit=True):
        playlist = db.get_playlist(playlist_id)
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
    pl_obj = get_playlist_obj_from_db(playlist_id, telegram_id)
    if pl_obj is None:
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
    
    tracks = getattr(pl_obj, "tracks", []) or []
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
    
    playlist = db.get_playlist(playlist_id)
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

def delete_track_input(update: Update, context: CallbackContext) -> int:
    """Обработка ввода номера трека для удаления."""
    telegram_id = update.effective_user.id
    raw = update.effective_message.text.strip()
    
    logger.info(f"delete_track_input вызван для пользователя {telegram_id}, текст: {raw}")
    
    # Проверка на отмену (fallback должен обработать, но на всякий случай)
    if raw in ["❌ Отмена", "отмена", "Отмена"] or raw.lower() in ["отмена", "/cancel", "/start"]:
        logger.info(f"Обнаружена отмена в delete_track_input")
        return cancel_operation(update, context)
    
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
    
    playlist = db.get_playlist(playlist_id)
    if not playlist:
        update.effective_message.reply_text(
            "❌ Плейлист не найден.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    pl_obj = get_playlist_obj_from_db(playlist_id, telegram_id)
    if pl_obj is None:
        update.effective_message.reply_text(
            "❌ Не удалось загрузить плейлист.\n\n"
            "💡 Возможно, проблема с доступом к Яндекс.Музыке.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    tracks = getattr(pl_obj, "tracks", []) or []
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
    t = item.track if hasattr(item, "track") and item.track else item
    track_title = getattr(t, "title", None) or "Unknown"
    artists = []
    if getattr(t, "artists", None):
        artists = [a.name for a in getattr(t, "artists", []) if getattr(a, "name", None)]
    artist_line = " / ".join(artists) if artists else ""
    
    from_idx = index - 1
    to_idx = index - 1
    ok, err = delete_track_api(playlist_id, from_idx, to_idx, telegram_id)
    
    if ok:
        record_message_stats(update, kind="delete_track", removed_count=1)
        track_info = f"«{track_title}»"
        if artist_line:
            track_info += f" — {artist_line}"
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

def add_command(update: Update, context: CallbackContext):
    """Обработка ссылок на треки/альбомы/плейлисты."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    # Проверяем, не находится ли пользователь в состоянии FSM
    # Если да, то не обрабатываем сообщение здесь (ConversationHandler должен обработать)
    if context.user_data.get('delete_track_playlist_id') is not None:
        # Пользователь в процессе удаления трека - не обрабатываем
        return
    if context.user_data.get('edit_playlist_id') is not None:
        # Пользователь в процессе редактирования названия - не обрабатываем
        return
    
    text = (update.effective_message.text or "").strip()
    
    # Получаем активный плейлист
    playlist_id = get_active_playlist_id(telegram_id)
    
    if not playlist_id:
        update.effective_message.reply_text(
            "❌ У вас нет активного плейлиста.\n\n"
            "💡 Создайте плейлист, используя кнопку «➕ Создать плейлист», или получите доступ к существующему.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Проверяем доступ
    if not db.check_playlist_access(playlist_id, telegram_id, need_add=True):
        playlist = db.get_playlist(playlist_id)
        title = playlist.get("title") or "плейлист" if playlist else "плейлист"
        update.effective_message.reply_text(
            f"❌ У вас нет прав на добавление треков в плейлист «{title}».\n\n"
            f"💡 Обратитесь к создателю плейлиста для получения доступа.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Показываем информацию об активном плейлисте
    playlist = db.get_playlist(playlist_id)
    playlist_title = playlist.get("title") or "плейлист" if playlist else "плейлист"
    
    client = client_manager.get_client(telegram_id)
    
    # Трек
    tr = parse_track_link(text)
    if tr:
        try:
            update.effective_message.reply_text("⏳ Добавляю трек...")
            track_obj = client.tracks(tr)[0]
            album_obj = track_obj.albums[0]
            ok, err = insert_track_api(playlist_id, track_obj.id, album_obj.id, telegram_id)
            if ok:
                record_message_stats(update, kind="track", added_count=1)
                artists = ", ".join([a.name for a in track_obj.artists]) if track_obj.artists else ""
                artist_text = f" — {artists}" if artists else ""
                update.effective_message.reply_text(
                    f"✅ Трек добавлен в «{playlist_title}»:\n"
                    f"🎵 «{track_obj.title}»{artist_text}"
                )
            else:
                update.effective_message.reply_text(
                    f"❌ Не удалось добавить трек: {err}\n\n"
                    f"💡 Проверьте права доступа к плейлисту."
                )
        except Exception as e:
            logger.exception("Error in add track: %s", e)
            update.effective_message.reply_text(
                f"❌ Ошибка при добавлении трека: {str(e)}\n\n"
                f"💡 Проверьте правильность ссылки и попробуйте еще раз."
            )
        return
    
    # Плейлист
    owner, pid = parse_playlist_link(text)
    if pid:
        update.effective_message.reply_text("⏳ Загружаю треки из плейлиста...")
        pl_obj, err = _fetch_playlist_obj(client, owner, pid)
        if pl_obj is None:
            update.effective_message.reply_text(
                f"❌ Не удалось получить плейлист: {err}\n\n"
                f"💡 Проверьте правильность ссылки."
            )
            return
        added = 0
        tracks_list = getattr(pl_obj, "tracks", []) or []
        total = len(tracks_list)
        
        for item in tracks_list:
            t = item.track if hasattr(item, "track") and item.track else item
            tr_id = getattr(t, "id", None) or getattr(t, "track_id", None)
            alb = getattr(t, "albums", None)
            if tr_id is None or not alb:
                continue
            ok, err = insert_track_api(playlist_id, tr_id, alb[0].id, telegram_id)
            if ok:
                added += 1
        
        record_message_stats(update, kind="playlist", added_count=added)
        if added > 0:
            update.effective_message.reply_text(
                f"✅ Добавлено {added} из {total} треков в «{playlist_title}»."
            )
        else:
            update.effective_message.reply_text(
                f"⚠️ Не удалось добавить треки из плейлиста.\n\n"
                f"💡 Возможно, все треки уже есть в плейлисте или возникла ошибка."
            )
        return
    
    # Альбом
    alb_id = parse_album_link(text)
    if alb_id:
        update.effective_message.reply_text("⏳ Загружаю треки из альбома...")
        tracks = _get_album_tracks(client, alb_id)
        if not tracks:
            update.effective_message.reply_text(
                "❌ Не удалось получить альбом или треки.\n\n"
                "💡 Проверьте правильность ссылки."
            )
            return
        added = 0
        total = len(tracks)
        
        for t in tracks:
            tr_id = getattr(t, "id", None) or getattr(t, "track_id", None)
            alb = getattr(t, "albums", None)
            if tr_id is None or not alb:
                continue
            ok, err = insert_track_api(playlist_id, tr_id, alb[0].id, telegram_id)
            if ok:
                added += 1
        
        record_message_stats(update, kind="album", added_count=added)
        if added > 0:
            update.effective_message.reply_text(
                f"✅ Добавлено {added} из {total} треков из альбома в «{playlist_title}»."
            )
        else:
            update.effective_message.reply_text(
                f"⚠️ Не удалось добавить треки из альбома.\n\n"
                f"💡 Возможно, все треки уже есть в плейлисте или возникла ошибка."
            )
        return
    
    # Ссылка на шаринг плейлиста
    share_token = parse_share_link(text)
    if share_token:
        playlist = db.get_playlist_by_share_token(share_token)
        if playlist:
            db.grant_playlist_access(playlist["id"], telegram_id, can_add=True)
            # Устанавливаем как активный
            if telegram_id not in user_contexts:
                user_contexts[telegram_id] = {}
            user_contexts[telegram_id]["current_playlist_id"] = playlist["id"]
            update.effective_message.reply_text(
                f"✅ Вы получили доступ к плейлисту «{playlist.get('title', 'Без названия')}»!\n\n"
                f"Теперь вы можете добавлять треки в этот плейлист.",
                reply_markup=get_main_menu_keyboard()
            )
            db.log_action(telegram_id, "playlist_shared_access", playlist["id"], f"via_token={share_token}")
            return
    
    update.effective_message.reply_text(
        "❌ Не удалось распознать ссылку.\n\n"
        "📋 Поддерживаемые форматы:\n"
        "• Трек: music.yandex.ru/track/...\n"
        "• Плейлист: music.yandex.ru/users/.../playlists/...\n"
        "• Альбом: music.yandex.ru/album/...\n"
        "• Ссылка на шаринг плейлиста\n\n"
        f"💡 Активный плейлист: «{playlist_title}»",
        reply_markup=get_main_menu_keyboard()
    )

def button_callback(update: Update, context: CallbackContext):
    """Обработка нажатий на inline-кнопки."""
    query = update.callback_query
    query.answer()
    
    telegram_id = query.from_user.id
    data = query.data
    
    if data.startswith("select_playlist_"):
        playlist_id = int(data.split("_")[-1])
        playlist = db.get_playlist(playlist_id)
        if not playlist:
            query.edit_message_text(
                "❌ Плейлист не найден.",
                reply_markup=None
            )
            return
        
        # Проверяем доступ
        if not db.check_playlist_access(playlist_id, telegram_id):
            query.edit_message_text(
                "❌ У вас нет доступа к этому плейлисту.",
                reply_markup=None
            )
            return
        
        # Устанавливаем как активный
        if telegram_id not in user_contexts:
            user_contexts[telegram_id] = {}
        user_contexts[telegram_id]["current_playlist_id"] = playlist_id
        
        title = playlist.get("title") or "Плейлист"
        is_creator = db.is_playlist_creator(playlist_id, telegram_id)
        status = "Создатель" if is_creator else "Участник"
        
        query.edit_message_text(
            f"✅ Выбран плейлист: «{title}»\n"
            f"👤 Статус: {status}\n\n"
            f"💡 Теперь отправляйте ссылки на треки, альбомы или плейлисты, чтобы добавить их в этот плейлист."
        )
    # edit_name_ и delete_track_ обрабатываются через ConversationHandler entry points
    elif data.startswith("delete_playlist_"):
        playlist_id = int(data.split("_")[-1])
        playlist = db.get_playlist(playlist_id)
        if not playlist:
            query.edit_message_text("❌ Плейлист не найден.")
            return
        
        if not db.is_playlist_creator(playlist_id, telegram_id):
            query.edit_message_text("❌ Только создатель плейлиста может удалять его.")
            return
        
        title = playlist.get("title") or "плейлист"
        db.delete_playlist(playlist_id)
        
        # Удаляем из контекста
        if telegram_id in user_contexts:
            user_contexts[telegram_id].pop("current_playlist_id", None)
        
        query.edit_message_text(
            f"✅ Плейлист «{title}» удален из базы данных бота.\n\n"
            f"💡 Плейлист остался в Яндекс.Музыке, но бот больше не имеет к нему доступа.",
            reply_markup=None
        )
        db.log_action(telegram_id, "playlist_deleted", playlist_id, None)

def handle_menu_buttons(update: Update, context: CallbackContext):
    """Обработка нажатий на кнопки меню."""
    text = update.effective_message.text.strip()
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    # Проверяем, не находится ли пользователь в состоянии FSM
    # Если да, то не обрабатываем кнопки меню (кроме "❌ Отмена", которая обрабатывается ConversationHandler)
    if context.user_data.get('delete_track_playlist_id') is not None:
        # Пользователь в процессе удаления трека - ConversationHandler должен обработать
        return
    if context.user_data.get('edit_playlist_id') is not None:
        # Пользователь в процессе редактирования названия - ConversationHandler должен обработать
        return
    
    if text == "📁 Мои плейлисты":
        my_playlists(update, context)
    elif text == "📂 Общие плейлисты":
        shared_playlists(update, context)
    elif text == "📋 Список треков":
        show_list(update, context)
    elif text == "ℹ️ Информация":
        playlist_info(update, context)
    elif text == "🏠 Главное меню":
        main_menu(update, context)
    # Кнопка "➕ Создать плейлист" обрабатывается ConversationHandler
    # Кнопка "❌ Отмена" обрабатывается fallback'ами ConversationHandler
    else:
        # Если это не кнопка меню, пытаемся обработать как ссылку
        add_command(update, context)

def error_handler(update: object, context: CallbackContext):
    """Обработчик ошибок."""
    logger.error(f"Ошибка при обработке обновления: {context.error}")
    if update and hasattr(update, 'effective_message'):
        try:
            update.effective_message.reply_text(
                "❌ Произошла ошибка при обработке запроса.\n\n"
                "💡 Попробуйте еще раз или используйте /start для возврата в главное меню.",
                reply_markup=get_main_menu_keyboard()
            )
        except:
            pass

# Глобальная переменная для хранения updater (нужна для обработки сигналов)
_updater_instance = None

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения."""
    logger.info(f"Получен сигнал {signum}, завершаю работу бота...")
    if _updater_instance:
        _updater_instance.stop()
        _updater_instance.is_idle = False
    sys.exit(0)

def main():
    """Главная функция."""
    global _updater_instance
    
    try:
        # Регистрируем обработчики сигналов для корректного завершения в Docker
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        logger.info("Запуск бота...")
        logger.info(f"TELEGRAM_TOKEN установлен: {'Да' if TELEGRAM_TOKEN else 'Нет'}")
        
        _updater_instance = Updater(TELEGRAM_TOKEN, use_context=True)
        updater = _updater_instance
        dp = updater.dispatcher
        
        dp.add_error_handler(error_handler)
        
        # FSM для создания плейлиста
        create_playlist_conv = ConversationHandler(
            entry_points=[
                CommandHandler("create_playlist", create_playlist_start, pass_args=True),
                MessageHandler(Filters.regex("^➕ Создать плейлист$"), create_playlist_start)
            ],
            states={
                WAITING_PLAYLIST_NAME: [
                    MessageHandler(Filters.text & ~Filters.command & ~Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), create_playlist_name)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel_operation),
                CommandHandler("start", cancel_operation),
                MessageHandler(Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), cancel_operation)
            ],
            name="create_playlist",
            persistent=False
        )
        
        # FSM для установки токена
        set_token_conv = ConversationHandler(
            entry_points=[
                CommandHandler("set_token", set_token_start, pass_args=True)
            ],
            states={
                WAITING_TOKEN: [
                    MessageHandler(Filters.text & ~Filters.command & ~Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), set_token_input)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel_operation),
                CommandHandler("start", cancel_operation),
                MessageHandler(Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), cancel_operation)
            ],
            name="set_token",
            persistent=False
        )
        
        # Команды
        dp.add_handler(CommandHandler("start", start, pass_args=True))
        dp.add_handler(create_playlist_conv)
        dp.add_handler(set_token_conv)
        dp.add_handler(CommandHandler("my_playlists", my_playlists))
        dp.add_handler(CommandHandler("shared_playlists", shared_playlists))
        dp.add_handler(CommandHandler("playlist_info", playlist_info, pass_args=True))
        dp.add_handler(CommandHandler("list", show_list, pass_args=True))
        # FSM для редактирования названия
        edit_name_conv = ConversationHandler(
            entry_points=[
                CommandHandler("edit_name", edit_name_start, pass_args=True),
                CallbackQueryHandler(edit_name_start, pattern="^edit_name_")
            ],
            states={
                WAITING_EDIT_NAME: [
                    MessageHandler(Filters.text & ~Filters.command & ~Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), edit_name_input)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel_operation),
                CommandHandler("start", cancel_operation),
                MessageHandler(Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), cancel_operation)
            ],
            name="edit_name",
            persistent=False
        )
        
        dp.add_handler(edit_name_conv)
        dp.add_handler(CommandHandler("delete_playlist", delete_playlist_cmd))
        
        # FSM для удаления трека
        delete_track_conv = ConversationHandler(
            entry_points=[
                CommandHandler("delete_track", delete_track_start, pass_args=True),
                CallbackQueryHandler(delete_track_start, pattern="^delete_track_")
            ],
            states={
                WAITING_TRACK_NUMBER: [
                    # Перехватываем ВСЕ текстовые сообщения (включая просто цифры)
                    # Но исключаем кнопку "Отмена", которая обрабатывается fallback
                    MessageHandler(Filters.text & ~Filters.command & ~Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), delete_track_input)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel_operation),
                CommandHandler("start", cancel_operation),
                MessageHandler(Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), cancel_operation)
            ],
            name="delete_track",
            persistent=False
        )
        
        dp.add_handler(delete_track_conv)
        
        # Inline-кнопки
        dp.add_handler(CallbackQueryHandler(button_callback))
        
        # Обработка кнопок меню и текстовых сообщений
        # Кнопки меню (кроме тех, что обрабатываются ConversationHandler)
        # ВАЖНО: "❌ Отмена" НЕ должна быть в этом списке, она обрабатывается ConversationHandler
        menu_buttons = [
            "📁 Мои плейлисты", "📂 Общие плейлисты",
            "📋 Список треков", "ℹ️ Информация", "🏠 Главное меню"
        ]
        # Обработка кнопок меню (должна быть перед обработкой ссылок, но после ConversationHandler)
        # Исключаем "❌ Отмена" из обработки, так как она обрабатывается ConversationHandler
        dp.add_handler(MessageHandler(
            Filters.text(menu_buttons) & ~Filters.command & ~Filters.regex("^(❌ Отмена|отмена)$"),
            handle_menu_buttons
        ))
        
        # Обработка текстовых сообщений (ссылки) - только если не кнопка меню и не команда
        # ConversationHandler обрабатывает свои состояния первым, поэтому этот обработчик
        # сработает только если пользователь НЕ находится в состоянии FSM
        dp.add_handler(MessageHandler(
            Filters.text & ~Filters.command,
            add_command
        ))
        
        logger.info("Начинаю polling...")
        updater.start_polling(
            drop_pending_updates=False,
            timeout=10,
            bootstrap_retries=3,
            read_latency=2
        )
        logger.info("Бот запущен и готов к работе!")
        logger.info(f"Бот @{updater.bot.get_me().username} готов принимать команды")
        updater.idle()
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания, завершаю работу...")
        if _updater_instance:
            _updater_instance.stop()
    except Exception as e:
        logger.exception(f"Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    main()

