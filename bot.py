"""
Telegram бот для управления плейлистами Яндекс.Музыки.
Поддерживает множественные плейлисты, шаринг и управление доступом.
"""
import os
import logging
import asyncio
import signal
import sys
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, SuccessfulPayment

from database import create_database
from yandex_client_manager import YandexClientManager
from utils.context import UserContextManager
from utils.maintenance_middleware import MaintenanceMiddleware
from handlers.commands import CommandHandlers
from handlers.callbacks import CallbackHandlers
from handlers.messages import MessageHandlers
from handlers.states import (
    CreatePlaylistStates,
    SetTokenStates,
    EditNameStates,
    DeleteTrackStates,
    SetCoverStates
)

# Загружаем переменные окружения
load_dotenv()

# === Конфигурация ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")

# Список ID администраторов (для режима техработ)
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(",") if admin_id.strip()] if ADMIN_IDS_STR else []

# Проверка обязательных переменных
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен в переменных окружения")
if not YANDEX_TOKEN:
    raise ValueError("YANDEX_TOKEN не установлен в переменных окружения")

# === Логирование ===
# Уровень логирования из переменной окружения (по умолчанию INFO)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, LOG_LEVEL, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Подавляем некритичные предупреждения (только если не DEBUG)
if log_level > logging.DEBUG:
    logging.getLogger('aiogram').setLevel(logging.ERROR)
    logging.getLogger('apscheduler').setLevel(logging.ERROR)

# === Инициализация БД и менеджеров ===
# Создаем БД на основе DB_TYPE из переменных окружения (по умолчанию: sqlite)
# БД будет инициализирована асинхронно в main()
db = create_database()
client_manager = YandexClientManager(YANDEX_TOKEN, db)
context_manager = UserContextManager(db)

# === Инициализация обработчиков ===
command_handlers = CommandHandlers(db, client_manager, context_manager)
callback_handlers = CallbackHandlers(db, context_manager, client_manager)
message_handlers = MessageHandlers(db, client_manager, context_manager)

# Глобальные переменные для корректного завершения
bot_instance: Bot = None
dp_instance: Dispatcher = None


async def error_handler(event, *args, **kwargs):
    """Обработчик ошибок для aiogram 3.x."""
    # В aiogram 3.x обработчик ошибок может вызываться по-разному в зависимости от версии
    exception = None
    
    # Пытаемся получить exception из разных источников
    # 1. Из kwargs (если передается как keyword argument)
    if 'exception' in kwargs:
        exception = kwargs['exception']
    elif 'error' in kwargs:
        exception = kwargs['error']
    # 2. Из первого позиционного аргумента после event
    elif len(args) > 0:
        if isinstance(args[0], Exception):
            exception = args[0]
        elif isinstance(args[0], dict):
            exception = args[0].get('exception') or args[0].get('error')
    # 3. Из атрибута event
    elif hasattr(event, 'exception'):
        exception = event.exception
    
    logger.error(f"Ошибка при обработке обновления: {exception}", exc_info=exception)
    try:
        from utils.message_helpers import send_message, GENERAL_ERROR
        from aiogram.types import Update, Message
        
        # Если это сообщение, пытаемся отправить ошибку
        message = None
        if event:
            # В aiogram 3.x event может быть Update или Message
            if isinstance(event, Update) and event.message:
                message = event.message
            elif isinstance(event, Message):
                message = event
        
        if message:
            await send_message(message, GENERAL_ERROR, use_main_menu=True)
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения об ошибке: {e}")


def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения."""
    logger.info(f"Получен сигнал {signum}, завершаю работу бота...")
    if bot_instance and dp_instance:
        # Останавливаем polling
        asyncio.create_task(dp_instance.stop_polling())
    sys.exit(0)


async def main():
    """Главная функция."""
    global bot_instance, dp_instance
    
    try:
        # Регистрируем обработчики сигналов для корректного завершения в Docker
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        logger.info("Запуск бота...")
        logger.info(f"TELEGRAM_TOKEN установлен: {'Да' if TELEGRAM_TOKEN else 'Нет'}")
        
        # Инициализируем БД асинхронно
        await db.init_db()
        
        # Инициализируем дефолтный аккаунт в менеджере клиентов
        await client_manager.init_default_account()
        
        # Создаем Bot и Dispatcher
        bot_instance = Bot(token=TELEGRAM_TOKEN)
        storage = MemoryStorage()
        dp_instance = Dispatcher(storage=storage)
        
        # Регистрируем middleware для режима техработ
        maintenance_middleware = MaintenanceMiddleware(admin_ids=ADMIN_IDS)
        dp_instance.update.middleware(maintenance_middleware)
        
        # Регистрируем обработчик ошибок
        # В aiogram 3.x обработчик ошибок принимает update и exception
        dp_instance.errors.register(error_handler)
        
        # === Регистрация обработчиков команд ===
        
        # Команда /start (обрабатывает и с аргументами, и без)
        dp_instance.message.register(
            command_handlers.start_handler,
            CommandStart()
        )
        
        # Команда /main_menu
        dp_instance.message.register(
            command_handlers.main_menu,
            Command("main_menu")
        )
        
        # Команда /my_playlists
        dp_instance.message.register(
            command_handlers.my_playlists,
            Command("my_playlists")
        )
        
        # Команда /shared_playlists
        dp_instance.message.register(
            command_handlers.shared_playlists,
            Command("shared_playlists")
        )
        
        # Команда /playlist_info
        dp_instance.message.register(
            command_handlers.playlist_info,
            Command("playlist_info")
        )
        
        # Команда /list
        dp_instance.message.register(
            command_handlers.show_list,
            Command("list")
        )
        
        # Команда /delete_playlist
        dp_instance.message.register(
            command_handlers.delete_playlist_cmd,
            Command("delete_playlist")
        )
        
        # Команда /buy_limit
        dp_instance.message.register(
            command_handlers.buy_limit,
            Command("buy_limit")
        )
        
        # Команда /cancel
        dp_instance.message.register(
            command_handlers.cancel_operation,
            Command("cancel")
        )
        
        # === FSM для создания плейлиста ===
        dp_instance.message.register(
            command_handlers.create_playlist_start,
            Command("create_playlist")
        )
        dp_instance.message.register(
            command_handlers.create_playlist_start,
            F.text == "➕ Создать плейлист"
        )
        dp_instance.message.register(
            command_handlers.create_playlist_name,
            CreatePlaylistStates.waiting_playlist_name
        )
        
        # === FSM для установки токена ===
        dp_instance.message.register(
            command_handlers.set_token_start,
            Command("set_token")
        )
        dp_instance.message.register(
            command_handlers.set_token_input,
            SetTokenStates.waiting_token
        )
        
        # === FSM для редактирования названия ===
        dp_instance.message.register(
            command_handlers.edit_name_start,
            Command("edit_name")
        )
        dp_instance.callback_query.register(
            command_handlers.edit_name_start,
            F.data.startswith("edit_name_")
        )
        dp_instance.message.register(
            command_handlers.edit_name_input,
            EditNameStates.waiting_edit_name
        )
        
        # === FSM для удаления трека ===
        dp_instance.message.register(
            command_handlers.delete_track_start,
            Command("delete_track")
        )
        dp_instance.callback_query.register(
            command_handlers.delete_track_start,
            F.data.startswith("delete_track_")
        )
        dp_instance.message.register(
            command_handlers.delete_track_input,
            DeleteTrackStates.waiting_track_number
        )
        
        # === FSM для установки обложки ===
        dp_instance.callback_query.register(
            command_handlers.set_cover_start,
            F.data.startswith("set_cover_")
        )
        dp_instance.message.register(
            command_handlers.set_cover_input,
            SetCoverStates.waiting_playlist_cover,
            F.photo
        )
        
        # === Обработчики платежей ===
        dp_instance.pre_checkout_query.register(
            command_handlers.handle_pre_checkout_query
        )
        dp_instance.message.register(
            command_handlers.handle_successful_payment,
            F.successful_payment
        )
        
        # === Inline-кнопки ===
        dp_instance.callback_query.register(
            callback_handlers.button_callback
        )
        
        # === Обработка кнопок меню и текстовых сообщений ===
        menu_buttons = [
            "📁 Мои плейлисты", "📂 Общие плейлисты",
            "📋 Список треков", "ℹ️ Информация", "🏠 Главное меню"
        ]
        
        # Обработка кнопок меню (должна быть перед обработкой ссылок)
        dp_instance.message.register(
            message_handlers.handle_menu_buttons,
            F.text.in_(menu_buttons)
        )
        
        # Обработка текстовых сообщений (ссылки) - только если не FSM состояние и не кнопка меню
        # FSM состояния обрабатываются первыми, поэтому этот обработчик сработает только если пользователь НЕ находится в состоянии FSM
        dp_instance.message.register(
            message_handlers.add_command,
            F.text & ~F.text.in_(menu_buttons) & ~F.text.startswith('/')
        )
        
        logger.info("Начинаю polling...")
        await dp_instance.start_polling(
            bot_instance,
            drop_pending_updates=False,
            allowed_updates=dp_instance.resolve_used_update_types()
        )
        logger.info("Бот запущен и готов к работе!")
        bot_info = await bot_instance.get_me()
        logger.info(f"Бот @{bot_info.username} готов принимать команды")
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания, завершаю работу...")
    except Exception as e:
        logger.exception(f"Критическая ошибка при запуске бота: {e}")
        raise
    finally:
        if bot_instance:
            await bot_instance.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
