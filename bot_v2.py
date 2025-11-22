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
from typing import Any, List, Tuple, Optional, Union, Dict
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext,
    CallbackQueryHandler
)
from yandex_music import Client
from yandex_music.exceptions import YandexMusicError

from database import Database
from yandex_client_manager import YandexClientManager

# Загружаем переменные окружения
load_dotenv()

# === Конфигурация ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")

# Для обратной совместимости (старый плейлист)
PLAYLIST_OWNER_ID = os.getenv("PLAYLIST_OWNER_ID")
PLAYLIST_ID = os.getenv("PLAYLIST_ID")
PLAYLIST_KIND = os.getenv("PLAYLIST_KIND") or os.getenv("PLAYLIST_ID")

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

# === Инициализация БД и менеджера клиентов ===
db = Database()
client_manager = YandexClientManager(YANDEX_TOKEN, db)

# === Контекст пользователей (для хранения выбранного плейлиста) ===
user_contexts: Dict[int, Dict] = {}  # {telegram_id: {"current_playlist_id": ...}}

# === Статистика (для обратной совместимости) ===
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
            update.effective_message.reply_text(
                f"✅ Вы получили доступ к плейлисту «{playlist.get('title', 'Без названия')}»!\n\n"
                f"Теперь вы можете добавлять треки в этот плейлист, отправляя ссылки на треки, альбомы или плейлисты."
            )
            db.log_action(telegram_id, "playlist_shared_access", playlist["id"], f"via_token={share_token}")
            return
    
    help_text = (
        "Привет! Я бот для управления плейлистами Яндекс.Музыки 🎵\n\n"
        "📋 Основные команды:\n"
        "/start — помощь\n"
        "/create_playlist <название> — создать новый плейлист\n"
        "/my_playlists — мои плейлисты (созданные мной)\n"
        "/shared_playlists — плейлисты, куда я добавляю\n"
        "/list [номер] — показать треки (без номера — последний активный)\n"
        "/playlist_info [номер] — информация о плейлисте\n"
        "/set_token <токен> — установить свой токен Яндекс.Музыки\n"
        "/queen_liza <номер> — удалить трек\n\n"
        "💡 Просто отправьте ссылку на трек/альбом/плейлист, чтобы добавить в активный плейлист!"
    )
    
    kb = [
        ["/my_playlists", "/shared_playlists"],
        ["/create_playlist", "/list"]
    ]
    update.effective_message.reply_text(
        help_text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )
    db.log_action(telegram_id, "command_start", None, None)

def create_playlist(update: Update, context: CallbackContext):
    """Команда /create_playlist."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    if not context.args:
        update.effective_message.reply_text(
            "Использование: /create_playlist <название>\n\n"
            "Пример: /create_playlist Моя музыка"
        )
        return
    
    title = " ".join(context.args)
    if len(title) > 100:
        update.effective_message.reply_text("Название плейлиста слишком длинное (максимум 100 символов).")
        return
    
    update.effective_message.reply_text("Создаю плейлист...")
    result = client_manager.create_playlist(telegram_id, title)
    
    if result:
        playlist_id = result["id"]
        share_token = result["share_token"]
        share_link = f"https://t.me/{context.bot.username}?start={share_token}"
        
        # Устанавливаем этот плейлист как активный для пользователя
        if telegram_id not in user_contexts:
            user_contexts[telegram_id] = {}
        user_contexts[telegram_id]["current_playlist_id"] = playlist_id
        
        update.effective_message.reply_text(
            f"✅ Плейлист «{title}» создан!\n\n"
            f"🔗 Ссылка для шаринга:\n{share_link}\n\n"
            f"Отправьте эту ссылку другим пользователям, чтобы они могли добавлять треки в ваш плейлист."
        )
    else:
        update.effective_message.reply_text("❌ Не удалось создать плейлист. Проверьте токен Яндекс.Музыки.")

def my_playlists(update: Update, context: CallbackContext):
    """Команда /my_playlists."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    playlists = db.get_user_playlists(telegram_id, only_created=True)
    
    if not playlists:
        update.effective_message.reply_text(
            "У вас пока нет созданных плейлистов.\n\n"
            "Создайте плейлист командой /create_playlist <название>"
        )
        return
    
    lines = ["📁 Ваши плейлисты:\n"]
    keyboard = []
    
    for i, pl in enumerate(playlists[:10], 1):  # Ограничиваем 10 плейлистами
        title = pl.get("title") or f"Плейлист #{pl['id']}"
        lines.append(f"{i}. {title} (ID: {pl['id']})")
        keyboard.append([InlineKeyboardButton(
            f"{i}. {title}",
            callback_data=f"select_playlist_{pl['id']}"
        )])
    
    if len(playlists) > 10:
        lines.append(f"\n... и еще {len(playlists) - 10} плейлистов")
    
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
            "У вас пока нет общих плейлистов, куда вы добавляете треки.\n\n"
            "Попросите у друзей ссылку на их плейлист!"
        )
        return
    
    lines = ["📂 Плейлисты, куда вы добавляете:\n"]
    keyboard = []
    
    for i, pl in enumerate(playlists[:10], 1):
        title = pl.get("title") or f"Плейлист #{pl['id']}"
        lines.append(f"{i}. {title} (ID: {pl['id']})")
        keyboard.append([InlineKeyboardButton(
            f"{i}. {title}",
            callback_data=f"select_playlist_{pl['id']}"
        )])
    
    if len(playlists) > 10:
        lines.append(f"\n... и еще {len(playlists) - 10} плейлистов")
    
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
            update.effective_message.reply_text("Использование: /playlist_info [номер плейлиста]")
            return
    else:
        # Используем активный плейлист
        if telegram_id in user_contexts and "current_playlist_id" in user_contexts[telegram_id]:
            playlist_id = user_contexts[telegram_id]["current_playlist_id"]
        else:
            # Берем первый доступный плейлист
            playlists = db.get_user_playlists(telegram_id)
            if playlists:
                playlist_id = playlists[0]["id"]
    
    if not playlist_id:
        update.effective_message.reply_text("У вас нет активного плейлиста. Используйте /my_playlists или /shared_playlists")
        return
    
    playlist = db.get_playlist(playlist_id)
    if not playlist:
        update.effective_message.reply_text("Плейлист не найден.")
        return
    
    # Проверяем доступ
    if not db.check_playlist_access(playlist_id, telegram_id):
        update.effective_message.reply_text("У вас нет доступа к этому плейлисту.")
        return
    
    title = playlist.get("title") or "Без названия"
    is_creator = db.is_playlist_creator(playlist_id, telegram_id)
    share_token = playlist.get("share_token")
    share_link = f"https://t.me/{context.bot.username}?start={share_token}" if share_token else None
    
    lines = [
        f"📋 Плейлист: {title}",
        f"ID: {playlist_id}",
        f"Статус: {'Создатель' if is_creator else 'Участник'}",
    ]
    
    if share_link:
        lines.append(f"\n🔗 Ссылка для шаринга:\n{share_link}")
    
    if is_creator:
        lines.append("\n⚙️ Доступные действия:")
        lines.append("/edit_name <новое название> — изменить название")
        lines.append("/delete_playlist — удалить плейлист")
    
    update.effective_message.reply_text("\n".join(lines))

def show_list(update: Update, context: CallbackContext):
    """Команда /list."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    playlist_id = None
    if context.args:
        try:
            playlist_id = int(context.args[0])
        except ValueError:
            update.effective_message.reply_text("Использование: /list [номер плейлиста]")
            return
    else:
        # Используем активный плейлист
        if telegram_id in user_contexts and "current_playlist_id" in user_contexts[telegram_id]:
            playlist_id = user_contexts[telegram_id]["current_playlist_id"]
        else:
            # Берем первый доступный плейлист
            playlists = db.get_user_playlists(telegram_id)
            if playlists:
                playlist_id = playlists[0]["id"]
    
    if not playlist_id:
        update.effective_message.reply_text(
            "У вас нет активного плейлиста.\n\n"
            "Используйте /my_playlists или /shared_playlists, чтобы выбрать плейлист."
        )
        return
    
    playlist = db.get_playlist(playlist_id)
    if not playlist:
        update.effective_message.reply_text("Плейлист не найден.")
        return
    
    # Проверяем доступ
    if not db.check_playlist_access(playlist_id, telegram_id):
        update.effective_message.reply_text("У вас нет доступа к этому плейлисту.")
        return
    
    pl_obj = get_playlist_obj_from_db(playlist_id, telegram_id)
    if pl_obj is None:
        update.effective_message.reply_text("Не удалось загрузить плейлист.")
        return
    
    tracks = getattr(pl_obj, "tracks", []) or []
    if not tracks:
        update.effective_message.reply_text("Плейлист пуст.")
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

def set_token(update: Update, context: CallbackContext):
    """Команда /set_token."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    if not context.args:
        update.effective_message.reply_text(
            "⚠️ ВНИМАНИЕ: Вы передаете боту свой токен Яндекс.Музыки на свой страх и риск!\n\n"
            "Использование: /set_token <токен>\n\n"
            "Токен можно получить здесь: https://yandex-music.readthedocs.io/en/main/token.html\n\n"
            "После установки токена бот будет использовать ваш аккаунт для создания плейлистов."
        )
        return
    
    token = context.args[0].strip()
    
    if client_manager.set_user_token(telegram_id, token):
        update.effective_message.reply_text(
            "✅ Токен успешно установлен!\n\n"
            "Теперь ваши плейлисты будут создаваться в вашем аккаунте Яндекс.Музыки."
        )
        db.log_action(telegram_id, "token_set", None, None)
    else:
        update.effective_message.reply_text(
            "❌ Не удалось установить токен. Проверьте правильность токена."
        )

def edit_name(update: Update, context: CallbackContext):
    """Команда /edit_name."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    if not context.args:
        update.effective_message.reply_text("Использование: /edit_name <новое название>")
        return
    
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
        update.effective_message.reply_text("Только создатель плейлиста может изменять название.")
        return
    
    new_title = " ".join(context.args)
    if len(new_title) > 100:
        update.effective_message.reply_text("Название слишком длинное (максимум 100 символов).")
        return
    
    db.update_playlist(playlist_id, title=new_title)
    update.effective_message.reply_text(f"✅ Название плейлиста изменено на «{new_title}»")
    db.log_action(telegram_id, "playlist_name_edited", playlist_id, f"new_title={new_title}")

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

def queen_liza(update: Update, context: CallbackContext):
    """Команда /queen_liza - удаление трека."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    if not context.args:
        update.effective_message.reply_text("Использование: /queen_liza <номер трека>")
        return
    
    # Получаем активный плейлист
    playlist_id = None
    if telegram_id in user_contexts and "current_playlist_id" in user_contexts[telegram_id]:
        playlist_id = user_contexts[telegram_id]["current_playlist_id"]
    else:
        playlists = db.get_user_playlists(telegram_id)
        if playlists:
            playlist_id = playlists[0]["id"]
    
    if not playlist_id:
        update.effective_message.reply_text("У вас нет активного плейлиста.")
        return
    
    # Проверяем доступ
    if not db.check_playlist_access(playlist_id, telegram_id, need_edit=True):
        update.effective_message.reply_text("У вас нет прав на удаление треков из этого плейлиста.")
        return
    
    raw = context.args[0].strip()
    if not re.match(r"^\d+$", raw):
        update.effective_message.reply_text("Укажите номер трека (число).")
        return
    
    index = int(raw)
    playlist = db.get_playlist(playlist_id)
    if not playlist:
        update.effective_message.reply_text("Плейлист не найден.")
        return
    
    pl_obj = get_playlist_obj_from_db(playlist_id, telegram_id)
    if pl_obj is None:
        update.effective_message.reply_text("Не удалось загрузить плейлист.")
        return
    
    tracks = getattr(pl_obj, "tracks", []) or []
    total = len(tracks)
    if index < 1 or index > total:
        update.effective_message.reply_text(f"Индекс вне диапазона: 1..{total}")
        return
    
    from_idx = index - 1
    to_idx = index - 1
    ok, err = delete_track_api(playlist_id, from_idx, to_idx, telegram_id)
    
    if ok:
        record_message_stats(update, kind="queen_liza", removed_count=1)
        update.effective_message.reply_text(f"✅ Трек №{index} удалён.")
    else:
        update.effective_message.reply_text(f"❌ {err}")

def add_command(update: Update, context: CallbackContext):
    """Обработка ссылок на треки/альбомы/плейлисты."""
    telegram_id = update.effective_user.id
    db.ensure_user(telegram_id, update.effective_user.username)
    
    text = (update.effective_message.text or "").strip()
    
    # Получаем активный плейлист
    playlist_id = None
    if telegram_id in user_contexts and "current_playlist_id" in user_contexts[telegram_id]:
        playlist_id = user_contexts[telegram_id]["current_playlist_id"]
    else:
        # Берем первый доступный плейлист
        playlists = db.get_user_playlists(telegram_id)
        if playlists:
            playlist_id = playlists[0]["id"]
            # Сохраняем как активный
            if telegram_id not in user_contexts:
                user_contexts[telegram_id] = {}
            user_contexts[telegram_id]["current_playlist_id"] = playlist_id
    
    if not playlist_id:
        update.effective_message.reply_text(
            "У вас нет активного плейлиста.\n\n"
            "Создайте плейлист командой /create_playlist <название> или получите доступ к существующему."
        )
        return
    
    # Проверяем доступ
    if not db.check_playlist_access(playlist_id, telegram_id, need_add=True):
        update.effective_message.reply_text("У вас нет прав на добавление треков в этот плейлист.")
        return
    
    client = client_manager.get_client(telegram_id)
    playlist = db.get_playlist(playlist_id)
    
    # Трек
    tr = parse_track_link(text)
    if tr:
        try:
            track_obj = client.tracks(tr)[0]
            album_obj = track_obj.albums[0]
            ok, err = insert_track_api(playlist_id, track_obj.id, album_obj.id, telegram_id)
            if ok:
                record_message_stats(update, kind="track", added_count=1)
                update.effective_message.reply_text(f"✅ Трек добавлен: «{track_obj.title}»")
            else:
                update.effective_message.reply_text(f"❌ Ошибка: {err}")
        except Exception as e:
            logger.exception("Error in add track: %s", e)
            update.effective_message.reply_text(f"❌ Ошибка: {e}")
        return
    
    # Плейлист
    owner, pid = parse_playlist_link(text)
    if pid:
        pl_obj, err = _fetch_playlist_obj(client, owner, pid)
        if pl_obj is None:
            update.effective_message.reply_text(f"❌ Не удалось получить плейлист: {err}")
            return
        added = 0
        for item in getattr(pl_obj, "tracks", []) or []:
            t = item.track if hasattr(item, "track") and item.track else item
            tr_id = getattr(t, "id", None) or getattr(t, "track_id", None)
            alb = getattr(t, "albums", None)
            if tr_id is None or not alb:
                continue
            ok, err = insert_track_api(playlist_id, tr_id, alb[0].id, telegram_id)
            if ok:
                added += 1
        record_message_stats(update, kind="playlist", added_count=added)
        update.effective_message.reply_text(f"✅ Добавлено {added} треков из плейлиста.")
        return
    
    # Альбом
    alb_id = parse_album_link(text)
    if alb_id:
        tracks = _get_album_tracks(client, alb_id)
        if not tracks:
            update.effective_message.reply_text("❌ Не удалось получить альбом или треки.")
            return
        added = 0
        for t in tracks:
            tr_id = getattr(t, "id", None) or getattr(t, "track_id", None)
            alb = getattr(t, "albums", None)
            if tr_id is None or not alb:
                continue
            ok, err = insert_track_api(playlist_id, tr_id, alb[0].id, telegram_id)
            if ok:
                added += 1
        record_message_stats(update, kind="album", added_count=added)
        update.effective_message.reply_text(f"✅ Из альбома добавлено {added} треков.")
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
                f"✅ Вы получили доступ к плейлисту «{playlist.get('title', 'Без названия')}»!"
            )
            db.log_action(telegram_id, "playlist_shared_access", playlist["id"], f"via_token={share_token}")
            return
    
    update.effective_message.reply_text(
        "❌ Не понял ссылку.\n\n"
        "Поддерживается:\n"
        "• Трек (music.yandex.ru/track/...)\n"
        "• Плейлист (music.yandex.ru/users/.../playlists/...)\n"
        "• Альбом (music.yandex.ru/album/...)\n"
        "• Ссылка на шаринг плейлиста"
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
            query.edit_message_text("Плейлист не найден.")
            return
        
        # Проверяем доступ
        if not db.check_playlist_access(playlist_id, telegram_id):
            query.edit_message_text("У вас нет доступа к этому плейлисту.")
            return
        
        # Устанавливаем как активный
        if telegram_id not in user_contexts:
            user_contexts[telegram_id] = {}
        user_contexts[telegram_id]["current_playlist_id"] = playlist_id
        
        title = playlist.get("title") or "Плейлист"
        query.edit_message_text(f"✅ Выбран плейлист: «{title}»\n\nТеперь отправляйте ссылки на треки, чтобы добавить их в этот плейлист.")

def error_handler(update: object, context: CallbackContext):
    """Обработчик ошибок."""
    logger.error(f"Ошибка при обработке обновления: {context.error}")
    if update and hasattr(update, 'effective_message'):
        try:
            update.effective_message.reply_text("Произошла ошибка при обработке запроса.")
        except:
            pass

def main():
    """Главная функция."""
    try:
        logger.info("Запуск бота...")
        logger.info(f"TELEGRAM_TOKEN установлен: {'Да' if TELEGRAM_TOKEN else 'Нет'}")
        
        updater = Updater(TELEGRAM_TOKEN, use_context=True)
        dp = updater.dispatcher
        
        dp.add_error_handler(error_handler)
        
        # Команды
        dp.add_handler(CommandHandler("start", start, pass_args=True))
        dp.add_handler(CommandHandler("create_playlist", create_playlist, pass_args=True))
        dp.add_handler(CommandHandler("my_playlists", my_playlists))
        dp.add_handler(CommandHandler("shared_playlists", shared_playlists))
        dp.add_handler(CommandHandler("playlist_info", playlist_info, pass_args=True))
        dp.add_handler(CommandHandler("list", show_list, pass_args=True))
        dp.add_handler(CommandHandler("set_token", set_token, pass_args=True))
        dp.add_handler(CommandHandler("edit_name", edit_name, pass_args=True))
        dp.add_handler(CommandHandler("delete_playlist", delete_playlist_cmd))
        dp.add_handler(CommandHandler("queen_liza", queen_liza, pass_args=True))
        
        # Inline-кнопки
        dp.add_handler(CallbackQueryHandler(button_callback))
        
        # Обработка текстовых сообщений (ссылки)
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, add_command))
        
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
    except Exception as e:
        logger.exception(f"Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == "__main__":
    main()

