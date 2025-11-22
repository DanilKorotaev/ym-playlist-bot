"""
Скрипт для миграции старого плейлиста в новую систему БД.
Запустите этот скрипт один раз, чтобы добавить ваш старый плейлист в базу данных.
"""
import os
import secrets
from dotenv import load_dotenv
from database import Database

load_dotenv()

db = Database()

# Получаем данные старого плейлиста из .env
PLAYLIST_OWNER_ID = os.getenv("PLAYLIST_OWNER_ID")
PLAYLIST_ID = os.getenv("PLAYLIST_ID")
PLAYLIST_KIND = os.getenv("PLAYLIST_KIND") or os.getenv("PLAYLIST_ID")

if not PLAYLIST_OWNER_ID or not PLAYLIST_KIND:
    print("❌ Ошибка: PLAYLIST_OWNER_ID и PLAYLIST_KIND должны быть установлены в .env")
    exit(1)

# Проверяем, не существует ли уже такой плейлист
existing = db.get_playlist_by_kind_and_owner(PLAYLIST_KIND, PLAYLIST_OWNER_ID)
if existing:
    print(f"⚠️ Плейлист уже существует в БД с ID: {existing['id']}")
    print(f"   Название: {existing.get('title', 'Без названия')}")
    response = input("Хотите обновить его? (y/n): ")
    if response.lower() != 'y':
        print("Отменено.")
        exit(0)
    playlist_id = existing['id']
    # Обновляем share_token, если его нет
    if not existing.get('share_token'):
        share_token = secrets.token_urlsafe(16)
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE playlists SET share_token = ? WHERE id = ?", (share_token, playlist_id))
        conn.commit()
        conn.close()
        print(f"✅ Токен для шаринга обновлен: {share_token}")
else:
    # Создаем новую запись
    share_token = secrets.token_urlsafe(16)
    playlist_id = db.create_playlist(
        playlist_kind=PLAYLIST_KIND,
        owner_id=PLAYLIST_OWNER_ID,
        creator_telegram_id=0,  # 0 для дефолтного аккаунта
        title="Мой плейлист",  # Можно изменить позже через /edit_name
        share_token=share_token
    )
    print(f"✅ Старый плейлист добавлен в БД с ID: {playlist_id}")

print(f"\n📋 Информация о плейлисте:")
print(f"   ID в БД: {playlist_id}")
print(f"   Kind: {PLAYLIST_KIND}")
print(f"   Owner ID: {PLAYLIST_OWNER_ID}")
print(f"   Токен для шаринга: {share_token}")
print(f"\n💡 Теперь вы можете использовать новый бот с этим плейлистом!")

