"""
Модуль для управления клиентами Яндекс.Музыки.
Поддерживает дефолтный клиент и клиенты пользователей.
"""
import logging
import asyncio
from typing import Optional, Dict, Tuple
from yandex_music import Client
from yandex_music.exceptions import YandexMusicError, TimedOutError
from database import DatabaseInterface

logger = logging.getLogger(__name__)

# Константы для таймаутов и повторов
DEFAULT_TIMEOUT = 30  # секунды
MAX_RETRIES = 3
RETRY_DELAY = 2  # секунды между попытками


class YandexClientManager:
    """Менеджер клиентов Яндекс.Музыки."""
    
    def __init__(self, default_token: str, db: DatabaseInterface, timeout: int = DEFAULT_TIMEOUT):
        self.db = db
        self.default_token = default_token
        self.timeout = timeout
        self._default_client: Optional[Client] = None
        self._user_clients: Dict[int, Client] = {}
        self._default_client_initialized = False
        
        # Дефолтный клиент будет инициализирован лениво при первом использовании
        # (асинхронно, чтобы не блокировать запуск)
    
    async def init_default_account(self):
        """Инициализировать дефолтный аккаунт в БД (вызывается после инициализации БД)."""
        await self.db.set_default_yandex_account(self.default_token)
    
    def _create_client_with_timeout(self, token: str) -> Client:
        """Создать клиент с настройками таймаута."""
        # yandex-music Client может принимать timeout через различные параметры
        # Пробуем разные варианты, если один не работает, используем дефолтный
        try:
            # Попытка 1: request_timeout (наиболее вероятный вариант)
            client = Client(token, request_timeout=self.timeout)
            return client
        except TypeError:
            # Если request_timeout не поддерживается, пробуем timeout
            try:
                client = Client(token, timeout=self.timeout)
                return client
            except TypeError:
                # Если и timeout не работает, создаем клиент без параметра
                # Таймаут будет обрабатываться на уровне retry логики
                logger.debug(f"Параметр timeout не поддерживается, используем дефолтные настройки")
                return Client(token)
    
    def _init_client_with_retry_sync(self, token: str, max_retries: int = MAX_RETRIES) -> Client:
        """Синхронная версия инициализации клиента с повторными попытками."""
        import time
        last_error = None
        
        for attempt in range(max_retries):
            try:
                client = self._create_client_with_timeout(token)
                client.init()
                return client
            except (TimedOutError, TimeoutError, ConnectionError, OSError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)  # Экспоненциальная задержка
                    logger.warning(
                        f"Попытка {attempt + 1}/{max_retries} инициализации клиента не удалась "
                        f"(таймаут). Повтор через {wait_time}с..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Все {max_retries} попытки инициализации клиента не удались")
            except Exception as e:
                # Для других ошибок не повторяем
                logger.error(f"Ошибка инициализации клиента (не таймаут): {e}")
                raise
        
        # Если все попытки не удались
        raise last_error or Exception("Неизвестная ошибка инициализации клиента")
    
    async def _init_client_with_retry(self, token: str, max_retries: int = MAX_RETRIES) -> Client:
        """Асинхронная версия инициализации клиента с повторными попытками."""
        return await asyncio.to_thread(self._init_client_with_retry_sync, token, max_retries)
    
    async def _init_default_client(self):
        """Инициализировать дефолтный клиент."""
        if self._default_client_initialized and self._default_client is not None:
            return
        
        try:
            self._default_client = await self._init_client_with_retry(self.default_token)
            self._default_client_initialized = True
            logger.info("Дефолтный клиент Яндекс.Музыки инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации дефолтного клиента: {e}")
            self._default_client_initialized = False
            raise
    
    async def _ensure_default_client(self):
        """Убедиться, что дефолтный клиент инициализирован."""
        if not self._default_client_initialized or self._default_client is None:
            try:
                await self._init_default_client()
            except Exception as e:
                logger.error(f"Не удалось инициализировать дефолтный клиент: {e}")
                raise RuntimeError(
                    "Дефолтный клиент Яндекс.Музыки не инициализирован. "
                    "Проверьте токен и сетевое подключение."
                )
    
    async def get_client(self, telegram_id: Optional[int] = None) -> Client:
        """
        Получить клиент Яндекс.Музыки для пользователя.
        Если telegram_id не указан или у пользователя нет своего токена, возвращает дефолтный.
        """
        if telegram_id is None:
            await self._ensure_default_client()
            return self._default_client
        
        # Проверяем, есть ли у пользователя свой токен
        user_token = await self.db.get_user_yandex_token(telegram_id)
        if not user_token:
            await self._ensure_default_client()
            return self._default_client
        
        # Если клиент уже создан, возвращаем его
        if telegram_id in self._user_clients:
            return self._user_clients[telegram_id]
        
        # Создаем новый клиент для пользователя
        try:
            client = await self._init_client_with_retry(user_token)
            self._user_clients[telegram_id] = client
            logger.info(f"Клиент Яндекс.Музыки для пользователя {telegram_id} инициализирован")
            return client
        except Exception as e:
            logger.error(f"Ошибка инициализации клиента для пользователя {telegram_id}: {e}")
            # В случае ошибки возвращаем дефолтный клиент
            await self._ensure_default_client()
            return self._default_client
    
    async def set_user_token(self, telegram_id: int, token: str) -> bool:
        """
        Установить токен Яндекс.Музыки для пользователя.
        Возвращает True, если токен валидный и установлен.
        """
        try:
            # Проверяем валидность токена, создавая временный клиент
            test_client = await self._init_client_with_retry(token)
            # Если успешно, сохраняем токен
            await self.db.set_user_yandex_token(telegram_id, token)
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
    
    async def get_client_for_playlist(self, playlist_id: int) -> Client:
        """
        Получить клиент для работы с конкретным плейлистом.
        Определяет, какой аккаунт использовался при создании плейлиста.
        """
        playlist = await self.db.get_playlist(playlist_id)
        if not playlist:
            await self._ensure_default_client()
            return self._default_client
        
        yandex_account_id = playlist.get("yandex_account_id")
        if not yandex_account_id:
            await self._ensure_default_client()
            return self._default_client
        
        # Получаем аккаунт из БД по ID
        account = await self.db.get_yandex_account_by_id(yandex_account_id)
        if not account:
            await self._ensure_default_client()
            return self._default_client
        
        # Если аккаунт привязан к пользователю, используем его клиент
        telegram_id = account.get("telegram_id")
        if telegram_id:
            return await self.get_client(telegram_id)
        
        # Если это дефолтный аккаунт (telegram_id is None), используем дефолтный клиент
        await self._ensure_default_client()
        return self._default_client
    
    async def create_playlist(self, telegram_id: Optional[int], title: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Создать новый плейлист в Яндекс.Музыке.
        
        Args:
            telegram_id: ID пользователя Telegram (опционально)
            title: Название плейлиста
            
        Returns:
            Tuple[Optional[Dict], Optional[str]]: (результат, сообщение об ошибке)
            Если результат None, то error содержит понятное сообщение для пользователя
        """
        client = await self.get_client(telegram_id)
        
        try:
            # Получаем UID аккаунта (синхронный вызов оборачиваем в thread)
            def _get_uid_and_create_playlist(client, title):
                # Получаем UID аккаунта
                if not hasattr(client, "me") or not client.me:
                    try:
                        client.init()
                    except Exception as e:
                        logger.error(f"Ошибка при повторной инициализации клиента: {e}")
                        raise
                
                uid = str(client.me.account.uid)
                
                # Создаем плейлист
                playlist = client.users_playlists_create(title)
                if not playlist:
                    logger.error("Не удалось создать плейлист")
                    return None, None, None
                
                playlist_kind = str(playlist.kind)
                # Получаем UUID плейлиста (может быть в разных атрибутах)
                playlist_uuid = getattr(playlist, "uuid", None) or getattr(playlist, "playlist_uuid", None)
                if playlist_uuid:
                    playlist_uuid = str(playlist_uuid)
                
                return uid, playlist_kind, playlist_uuid
            
            uid, playlist_kind, playlist_uuid = await asyncio.to_thread(_get_uid_and_create_playlist, client, title)
            if uid is None:
                return None, "Не удалось создать плейлист. Попробуйте еще раз."
            
            # Получаем аккаунт из БД для связи
            if telegram_id:
                yandex_account = await self.db.get_yandex_account_for_user(telegram_id)
            else:
                yandex_account = await self.db.get_default_yandex_account()
            yandex_account_id = yandex_account["id"] if yandex_account else None
            
            # Сохраняем в БД
            # Для дефолтного аккаунта используем специальный telegram_id = 0
            creator_id = telegram_id if telegram_id else 0
            playlist_id = await self.db.create_playlist(
                playlist_kind=playlist_kind,
                owner_id=uid,
                creator_telegram_id=creator_id,
                yandex_account_id=yandex_account_id,
                title=title,
                uuid=playlist_uuid
            )
            
            # Генерируем токен для шаринга
            import secrets
            share_token = secrets.token_urlsafe(16)
            
            # Обновляем share_token и title через интерфейс
            await self.db.update_playlist(playlist_id, title=title, share_token=share_token)
            
            # Логируем действие
            if telegram_id:
                await self.db.log_action(
                    telegram_id, "playlist_created", playlist_id, 
                    f"title={title}, kind={playlist_kind}"
                )
            
            return {
                "id": playlist_id,
                "kind": playlist_kind,
                "owner_id": uid,
                "title": title,
                "share_token": share_token
            }, None
        except TimedOutError as e:
            logger.warning(f"Таймаут при создании плейлиста: {e}")
            return None, "Превышено время ожидания ответа. Попробуйте еще раз."
        except YandexMusicError as e:
            error_message = str(e).lower()
            error_str = str(e)
            
            # Проверяем на ошибки модерации
            if any(keyword in error_message for keyword in ["moderation", "модерац", "name", "title", "invalid", "некорректн"]):
                logger.warning(
                    f"Ошибка модерации названия плейлиста: title='{title}', "
                    f"user_id={telegram_id}, error={error_str}"
                )
                return None, "Название плейлиста не прошло модерацию. Пожалуйста, используйте другое название."
            
            # Проверяем на ошибки авторизации (401)
            if "unauthorized" in error_message or "401" in error_str or "недействителен" in error_message:
                logger.warning(f"Ошибка авторизации при создании плейлиста: user_id={telegram_id}, error={error_str}")
                return None, "Токен Яндекс.Музыки недействителен. Используйте /set_token для обновления."
            
            # Проверяем на ошибки доступа (403)
            if "forbidden" in error_message or "403" in error_str or "недостаточно прав" in error_message:
                logger.warning(f"Ошибка доступа при создании плейлиста: user_id={telegram_id}, error={error_str}")
                return None, "Недостаточно прав для создания плейлиста или название не прошло модерацию."
            
            # Проверяем на ошибки некорректного запроса (400)
            if "bad request" in error_message or "400" in error_str:
                logger.warning(f"Некорректный запрос при создании плейлиста: user_id={telegram_id}, error={error_str}")
                return None, "Некорректный запрос. Проверьте название плейлиста."
            
            # Другие ошибки API
            logger.error(f"Ошибка API при создании плейлиста: user_id={telegram_id}, error={error_str}")
            return None, "Ошибка при создании плейлиста. Попробуйте еще раз."
        except (ConnectionError, OSError) as e:
            logger.warning(f"Сетевая ошибка при создании плейлиста: {e}")
            return None, "Проблема с подключением к Яндекс.Музыке. Попробуйте позже."
        except Exception as e:
            logger.exception(f"Неожиданная ошибка при создании плейлиста: {e}")
            return None, "Ошибка при создании плейлиста. Попробуйте еще раз."

