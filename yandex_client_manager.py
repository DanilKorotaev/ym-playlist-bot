"""
Модуль для управления клиентами Яндекс.Музыки.
Поддерживает дефолтный клиент и клиенты пользователей.
"""
import logging
from typing import Optional, Dict
from yandex_music import Client
from yandex_music.exceptions import YandexMusicError
from database import Database

logger = logging.getLogger(__name__)


class YandexClientManager:
    """Менеджер клиентов Яндекс.Музыки."""
    
    def __init__(self, default_token: str, db: Database):
        self.db = db
        self.default_token = default_token
        self._default_client: Optional[Client] = None
        self._user_clients: Dict[int, Client] = {}
        
        # Инициализируем дефолтный клиент
        self._init_default_client()
        
        # Сохраняем дефолтный токен в БД
        self.db.set_default_yandex_account(default_token)
    
    def _init_default_client(self):
        """Инициализировать дефолтный клиент."""
        try:
            self._default_client = Client(self.default_token).init()
            logger.info("Дефолтный клиент Яндекс.Музыки инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации дефолтного клиента: {e}")
            raise
    
    def get_client(self, telegram_id: Optional[int] = None) -> Client:
        """
        Получить клиент Яндекс.Музыки для пользователя.
        Если telegram_id не указан или у пользователя нет своего токена, возвращает дефолтный.
        """
        if telegram_id is None:
            return self._default_client
        
        # Проверяем, есть ли у пользователя свой токен
        user_token = self.db.get_user_yandex_token(telegram_id)
        if not user_token:
            return self._default_client
        
        # Если клиент уже создан, возвращаем его
        if telegram_id in self._user_clients:
            return self._user_clients[telegram_id]
        
        # Создаем новый клиент для пользователя
        try:
            client = Client(user_token).init()
            self._user_clients[telegram_id] = client
            logger.info(f"Клиент Яндекс.Музыки для пользователя {telegram_id} инициализирован")
            return client
        except Exception as e:
            logger.error(f"Ошибка инициализации клиента для пользователя {telegram_id}: {e}")
            # В случае ошибки возвращаем дефолтный клиент
            return self._default_client
    
    def set_user_token(self, telegram_id: int, token: str) -> bool:
        """
        Установить токен Яндекс.Музыки для пользователя.
        Возвращает True, если токен валидный и установлен.
        """
        try:
            # Проверяем валидность токена, создавая временный клиент
            test_client = Client(token).init()
            # Если успешно, сохраняем токен
            self.db.set_user_yandex_token(telegram_id, token)
            # Обновляем кэш клиентов
            if telegram_id in self._user_clients:
                del self._user_clients[telegram_id]
            # Создаем новый клиент
            self._user_clients[telegram_id] = test_client
            logger.info(f"Токен для пользователя {telegram_id} установлен и проверен")
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке токена для пользователя {telegram_id}: {e}")
            return False
    
    def get_client_for_playlist(self, playlist_id: int) -> Client:
        """
        Получить клиент для работы с конкретным плейлистом.
        Определяет, какой аккаунт использовался при создании плейлиста.
        """
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return self._default_client
        
        yandex_account_id = playlist.get("yandex_account_id")
        if not yandex_account_id:
            return self._default_client
        
        # Получаем аккаунт из БД
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM yandex_accounts WHERE id = ?", (yandex_account_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row["telegram_id"]:
            return self.get_client(row["telegram_id"])
        
        return self._default_client
    
    def create_playlist(self, telegram_id: Optional[int], title: str) -> Optional[Dict]:
        """
        Создать новый плейлист в Яндекс.Музыке.
        Возвращает информацию о созданном плейлисте или None при ошибке.
        """
        client = self.get_client(telegram_id)
        
        try:
            # Получаем UID аккаунта
            if not hasattr(client, "me") or not client.me:
                client.init()
            
            uid = str(client.me.account.uid)
            
            # Создаем плейлист
            playlist = client.users_playlists_create(title)
            if not playlist:
                logger.error("Не удалось создать плейлист")
                return None
            
            playlist_kind = str(playlist.kind)
            
            # Получаем аккаунт из БД для связи
            yandex_account = self.db.get_yandex_account_for_user(telegram_id) if telegram_id else self.db.get_default_yandex_account()
            yandex_account_id = yandex_account["id"] if yandex_account else None
            
            # Сохраняем в БД
            # Для дефолтного аккаунта используем специальный telegram_id = 0
            creator_id = telegram_id if telegram_id else 0
            playlist_id = self.db.create_playlist(
                playlist_kind=playlist_kind,
                owner_id=uid,
                creator_telegram_id=creator_id,
                yandex_account_id=yandex_account_id,
                title=title
            )
            
            # Генерируем токен для шаринга
            import secrets
            share_token = secrets.token_urlsafe(16)
            
            # Обновляем share_token
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE playlists SET share_token = ?, title = ? WHERE id = ?", 
                         (share_token, title, playlist_id))
            conn.commit()
            conn.close()
            
            # Логируем действие
            if telegram_id:
                self.db.log_action(telegram_id, "playlist_created", playlist_id, 
                                 f"title={title}, kind={playlist_kind}")
            
            return {
                "id": playlist_id,
                "kind": playlist_kind,
                "owner_id": uid,
                "title": title,
                "share_token": share_token
            }
        except Exception as e:
            logger.exception(f"Ошибка при создании плейлиста: {e}")
            return None

