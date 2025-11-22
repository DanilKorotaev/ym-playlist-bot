import re
import os
import json
import logging
import time
import json
import urllib.parse
from typing import Any, List, Tuple, Optional, Union
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from yandex_music import Client
from yandex_music.exceptions import YandexMusicError

# Загружаем переменные окружения из .env файла
load_dotenv()

# === Конфигурация ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")

# uid = client.me.account.uid
# для плейлистов: client.users_playlists_list(uid) -> p.kind
PLAYLIST_OWNER_ID = os.getenv("PLAYLIST_OWNER_ID")
PLAYLIST_ID = os.getenv("PLAYLIST_ID")
PLAYLIST_KIND = os.getenv("PLAYLIST_KIND") or os.getenv("PLAYLIST_ID")  # обычно совпадает с PLAYLIST_ID

# Проверка обязательных переменных
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен в переменных окружения")
if not YANDEX_TOKEN:
    raise ValueError("YANDEX_TOKEN не установлен в переменных окружения")
if not PLAYLIST_OWNER_ID:
    raise ValueError("PLAYLIST_OWNER_ID не установлен в переменных окружения")
if not PLAYLIST_ID:
    raise ValueError("PLAYLIST_ID не установлен в переменных окружения")
if not PLAYLIST_KIND:
    raise ValueError("PLAYLIST_KIND не установлен в переменных окружения (или установите PLAYLIST_ID)")

STATS_FILE = "stats.json"

# === Логирование ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Инициализация клиента ===
client = Client(YANDEX_TOKEN).init()

# === Статистика в памяти / файле ===
def load_stats() -> dict:
    if not os.path.exists(STATS_FILE):
        base = {
            "users": {},
            "links_count": {"track": 0, "playlist": 0, "album": 0},
            "commands": {"list": 0, "link": 0, "statistics": 0, "queen_liza": 0},
            "total_messages": 0
        }
        save_stats(base)
        return base
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_stats(obj: dict):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def ensure_user(stats: dict, user_id: str, username: Optional[str]):
    if user_id not in stats["users"]:
        stats["users"][user_id] = {"username": username or "", "added": 0, "removed": 0, "messages": []}

def record_message_stats(update: Update, kind: str, added_count: int =0, removed_count: int =0):
    stats = load_stats()
    user = update.effective_user
    uid = str(user.id)
    ensure_user(stats, uid, user.username)
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
    if kind in stats["links_count"]:
        stats["links_count"][kind] += 1
    save_stats(stats)

def record_command_usage(cmd: str):
    stats = load_stats()
    stats["commands"][cmd] = stats["commands"].get(cmd, 0) + 1
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
    """
    Возвращает (owner, playlist_id), где могут быть GUID или числа как str.
    """
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

# === Yandex-helpers: альбомы и плейлисты ===

def _get_album_tracks(album_id) -> List[Any]:
    try:
        # используем метод albums_with_tracks, если есть
        if hasattr(client, "albums_with_tracks"):
            alb = client.albums_with_tracks(album_id)
        else:
            # fallback к albums / album
            if hasattr(client, "albums"):
                maybe = client.albums([album_id])
                alb = maybe[0] if isinstance(maybe, list) and maybe else maybe
            else:
                alb = client.album(album_id)

        if alb is None:
            return []

        # есть атрибут tracks
        if hasattr(alb, "tracks") and alb.tracks:
            return alb.tracks

        # иногда у альбома может быть volumes
        vols = getattr(alb, "volumes", None)
        if vols:
            tracks = []
            for vol in vols:
                tracks.extend(vol)
            return tracks

        # другие возможные атрибуты
        for attr in ["tracklist", "items", "results"]:
            maybe = getattr(alb, attr, None)
            if maybe and isinstance(maybe, list):
                return maybe

    except YandexMusicError as e:
        logger.exception("Ошибка при получении альбома с треками: %s", e)
    return []

def playlists_list_resolve_owner(pid: Union[int, str]) -> Optional[Tuple[str, str]]:
    """
    Разрешить GUID плейлиста в (owner_id, kind).
    """
    try:
        url = f"{client.base_url}/playlist/{pid}"
        result = client._request.get(url)
        if result and "owner" in result and "uid" in result["owner"]:
            return result["owner"]["uid"], result["kind"]
    except Exception as e:
        logger.debug("playlists_list_resolve_owner failed: %s", e)
    return None


def _fetch_playlist_obj(owner: Optional[str], pid: str) -> Tuple[Optional[Any], Optional[str]]:
    """
    Получить объект плейлиста с заполненными tracks.
    Поддержка: /users/<owner>/playlists/<id>, /playlists/<guid>, просто GUID/id.
    """
    # 1) если owner задан в ссылке
    if owner:
        try:
            pl = client.users_playlists(pid, owner)
            return pl, None
        except Exception as e:
            logger.debug("users_playlists(pid,owner) failed: %s", e)

    # 2) если owner не задан — резолвим через hidden API
    resolved = playlists_list_resolve_owner(pid)
    if resolved:
        own, kind = resolved
        try:
            pl = client.users_playlists(kind, own)
            return pl, None
        except Exception as e:
            logger.debug("Resolved owner but users_playlists failed: %s", e)

    # 3) fallback — пробуем стандартные методы (для старых версий API)
    try:
        if hasattr(client, "playlist"):
            pl = client.playlist(pid)
            return pl, None
        if hasattr(client, "playlists"):
            pl = client.playlists(pid)
            return pl, None
        if hasattr(client, "playlists_list"):
            pl = client.playlists_list([pid])
            return pl, None
    except Exception as e:
        logger.debug("client.playlist/playlists failed: %s", e)

    return None, f"Не удалось получить плейлист {pid}"

def get_playlist_obj() -> Optional[Any]:
    """
    Получить объект твоего (локального) целевого плейлиста с tracks.
    """
    try:
        pl = client.users_playlists(PLAYLIST_ID, PLAYLIST_OWNER_ID)
        return pl
    except Exception as e:
        logger.debug("users_playlists(local) failed: %s", e)
    # fallback: if PLAYLIST_KIND variant
    try:
        pl = client.users_playlists(PLAYLIST_KIND)
        return pl
    except Exception as e:
        logger.debug("users_playlists(kind) fallback failed: %s", e)
    return None

# === API вставки / удаления ===

def insert_track_api(track_id: Any, album_id: Any) -> Tuple[bool, Optional[str]]:
    last_err = None
    for attempt in range(2):
        pl = get_playlist_obj()
        if pl is None:
            return False, "Не удалось получить целевой плейлист."
        revision = getattr(pl, "revision", 1)

        try:
            # Метод из последней версии
            # users_playlists_insert_track(kind, track_id, album_id, at=0, revision=..., user_id=...)
            client.users_playlists_insert_track(PLAYLIST_KIND, track_id, album_id, at=0, revision=revision, user_id=PLAYLIST_OWNER_ID)
            return True, None
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            logger.debug("insert attempt failed: %s", e)
            if "wrong-revision" in msg or "revision" in msg:
                continue
    return False, f"Ошибка вставки: {last_err}"

def delete_track_by_index(index: int) -> Tuple[bool, str]:
    pl = get_playlist_obj()
    if pl is None:
        return False, "Не удалось получить плейлист."
    total = len(getattr(pl, "tracks", []) or [])
    if index < 1 or index > total:
        return False, f"Индекс вне диапазона: 1..{total}"
    from_idx = index - 1
    to_idx = index - 1
    tracks = getattr(pl, "tracks", []) or []

    ok, err = delete_track_api(tracks[index], from_idx, to_idx)
    if ok:
        return True, f"Трек №{index} удалён."
    else:
        return False, err

def delete_track_api(track, from_idx: int, to_idx: int) -> Tuple[bool, Optional[str]]:
    """
    Удаление трека из плейлиста через change-relative API.
    track — объект трека (нужно id и albumId).
    """
    owner = PLAYLIST_OWNER_ID
    kind = PLAYLIST_KIND

    last_err = None
    
    for attempt in range(2):
        try:
            pl = get_playlist_obj()
            
            if pl is None:
                return False, "Не удалось получить целевой плейлист."
            revision = getattr(pl, "revision", 1)
            diff = [{
                "op": "delete",
                "from": from_idx,
                "to": to_idx
            }]
            diff_str = json.dumps(diff, ensure_ascii=False).replace(" ", "")
            diff_encoded = urllib.parse.quote(diff_str, safe="")
            url = f"{client.base_url}/users/{owner}/playlists/{kind}/change-relative?diff={diff_encoded}&revision={revision}"
            result = client._request.post(url)
            return True, "Трек успешно удалён." if result else "Запрос выполнен, но ответ пустой."
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            logger.debug("delete attempt failed: %s", e)
            if "wrong-revision" in msg or "revision" in msg:
                continue
    return False, f"Ошибка удаления: {last_err}"

def delete_track_by_track_ref(track_ref: Any) -> Tuple[bool, str]:
    """
    Ищет индекс трека по track_ref (id или guid) и удаляет его.
    Возвращает (ok, message).
    """
    idx = find_track_index_in_playlist(track_ref)
    if idx is None:
        return False, "Не удалось найти трек в целевом плейлисте."
    return delete_track_by_index(idx)

def find_track_index_in_playlist(track_ref) -> Optional[int]:
    """
    По track id (или guid) найти индекс (1-based) в целевом плейлисте.
    """
    try:
        pl = client.users_playlists(PLAYLIST_ID, PLAYLIST_OWNER_ID)
    except Exception as e:
        logger.exception("Не удалось получить плейлист: %s", e)
        return None
    tracks = getattr(pl, "tracks", []) or []
    for idx, item in enumerate(tracks, start=1):
        t = item.track if hasattr(item, "track") and item.track else item
        tid = getattr(t, "id", None) or getattr(t, "track_id", None)
        try:
            if str(tid) == str(track_ref) or (str(tid).isdigit() and int(tid) == int(track_ref)):
                return idx
        except Exception:
            if str(tid) == str(track_ref):
                return idx
    return None

# === Команды бота (добавление / удаление / статистика / list / link / start) ===

def start(update: Update, context: CallbackContext):
    kb = [["/start", "/link"], ["/list"]]
    update.effective_message.reply_text(
        "Привет! Я бот для управления плейлистом Яндекс.Музыки 🎵\n\n"
        "Доступные команды:\n"
        "/start — помощь\n"
        "/link — ссылка на плейлист\n"
        "/list — показать треки\n\n"
        "А также просто кидай ссылку на трек / плейлист / альбом, чтобы добавить.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

def add_command(update: Update, context: CallbackContext):
    text = (update.effective_message.text or "").strip()
    user = update.effective_user.username or str(update.effective_user.id)

    # track
    tr = parse_track_link(text)
    if tr:
        try:
            track_obj = client.tracks(tr)[0]
            album_obj = track_obj.albums[0]
            ok, err = insert_track_api(track_obj.id, album_obj.id)
            if ok:
                record_message_stats(update, kind="track", added_count=1)
                update.effective_message.reply_text(f"✅ Трек добавлен: «{track_obj.title}»")
            else:
                update.effective_message.reply_text(f"Ошибка добавления: {err}")
        except Exception as e:
            logger.exception("Error in add track link: %s", e)
            update.effective_message.reply_text(f"Ошибка: {e}")
        return

    # playlist
    owner, pid = parse_playlist_link(text)
    if pid:
        pl_obj, err = _fetch_playlist_obj(owner, pid)
        if pl_obj is None:
            update.effective_message.reply_text(f"Не удалось получить плейлист: {err}")
            return
        added = 0
        for item in getattr(pl_obj, "tracks", []) or []:
            t = item.track if hasattr(item, "track") and item.track else item
            tr_id = getattr(t, "id", None) or getattr(t, "track_id", None)
            alb = getattr(t, "albums", None)
            if tr_id is None or not alb:
                continue
            ok, err = insert_track_api(tr_id, alb[0].id)
            if ok:
                added += 1
        record_message_stats(update, kind="playlist", added_count=added)
        update.effective_message.reply_text(f"✅ Добавлено {added} треков из плейлиста.")
        return

    # album
    alb_id = parse_album_link(text)
    if alb_id:
        tracks = _get_album_tracks(alb_id)
        if not tracks:
            update.effective_message.reply_text("Не удалось получить альбом или треки.")
            return
        added = 0
        for t in tracks:
            tr_id = getattr(t, "id", None) or getattr(t, "track_id", None)
            alb = getattr(t, "albums", None)
            if tr_id is None or not alb:
                continue
            ok, err = insert_track_api(tr_id, alb[0].id)
            if ok:
                added += 1
        record_message_stats(update, kind="album", added_count=added)
        update.effective_message.reply_text(f"✅ Из альбома добавлено {added} треков.")
        return

    update.effective_message.reply_text("Не понял ссылку. Поддерживается: трек, плейлист, альбом.")

def show_list(update: Update, context: CallbackContext):
    record_command_usage("list")
    pl = get_playlist_obj()
    if pl is None:
        update.effective_message.reply_text("Не удалось загрузить плейлист.")
        return
    tracks = getattr(pl, "tracks", []) or []
    if not tracks:
        update.effective_message.reply_text("Плейлист пуст.")
        return
    lines = []
    for i, item in enumerate(tracks, start=1):
        t = item.track if hasattr(item, "track") and item.track else item
        title = getattr(t, "title", None) or "Unknown"
        artists = []
        if getattr(t, "artists", None):
            artists = [a.name for a in getattr(t, "artists", []) if getattr(a, "name", None)]
        artist_line = " / ".join(artists) if artists else ""
        lines.append(f"{i}. {title}" + (f" — {artist_line}" if artist_line else ""))
    chunk = 50
    for i in range(0, len(lines), chunk):
        part = "\n".join(lines[i:i+chunk])
        update.effective_message.reply_text(part)

def link_command(update: Update, context: CallbackContext):
    record_command_usage("link")
    url = f"https://music.yandex.ru/users/{PLAYLIST_OWNER_ID}/playlists/{PLAYLIST_ID}"
    update.effective_message.reply_text(f"Ссылка на плейлист: {url}")

def statistics_command(update: Update, context: CallbackContext):
    record_command_usage("statistics")
    stats = load_stats()
    users = stats.get("users", {})
    lines = ["📊 Статистика:\n"]
    for uid, data in users.items():
        name = data.get("username") or f"id:{uid}"
        lines.append(f"{name}: {data.get('added',0)} добавлений, {data.get('removed',0)} удалений")
    lc = stats.get("links_count", {})
    lines.append(f"\nТипы ссылок: трек {lc.get('track',0)}, плейлист {lc.get('playlist',0)}, альбом {lc.get('album',0)}")
    cmdc = stats.get("commands", {})
    lines.append("\nИспользование команд:")
    for cmd, c in cmdc.items():
        lines.append(f"/{cmd}: {c}")
    update.effective_message.reply_text("\n".join(lines))

def queen_lisa(update: Update, context: CallbackContext):
    record_command_usage("queen_liza")
    msg = update.effective_message
    args = context.args if hasattr(context, "args") else []
    if not args:
        msg.reply_text("Укажи номер или ссылку на трек: /queen_liza 5 или /queen_liza <ссылка>")
        return
    raw = args[0].strip()
    if re.match(r"^\d+$", raw):
        idx = int(raw)
        ok, text = delete_track_by_index(idx)
        if ok:
            record_message_stats(update, kind="queen_liza", removed_count=1)
        msg.reply_text(text)
        return
    tr = parse_track_link(raw)
    if tr:
        ok, text = delete_track_by_track_ref(tr)
        if ok:
            record_message_stats(update, kind="queen_liza", removed_count=1)
        msg.reply_text(text)
        return
    msg.reply_text("Не понял аргумент.")

def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("list", show_list))
    dp.add_handler(CommandHandler("link", link_command))
    dp.add_handler(CommandHandler("statistics", statistics_command))
    dp.add_handler(CommandHandler("queen_liza", queen_lisa, pass_args=True))

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, add_command))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()