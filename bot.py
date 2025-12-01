"""
Telegram бот для управления плейлистами Яндекс.Музыки.
Поддерживает множественные плейлисты, шаринг и управление доступом.
"""
import os
import logging
import signal
import sys
from dotenv import load_dotenv

from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext,
    CallbackQueryHandler, ConversationHandler, PreCheckoutQueryHandler
)

from database import create_database
from yandex_client_manager import YandexClientManager
from utils.context import UserContextManager
from handlers.commands import CommandHandlers, WAITING_PLAYLIST_NAME, WAITING_TOKEN, WAITING_EDIT_NAME, WAITING_TRACK_NUMBER, WAITING_PLAYLIST_COVER
from handlers.callbacks import CallbackHandlers
from handlers.messages import MessageHandlers
from handlers.keyboards import get_main_menu_keyboard, get_cancel_keyboard

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
    logging.getLogger('telegram.utils.request').setLevel(logging.ERROR)
    logging.getLogger('apscheduler').setLevel(logging.ERROR)

# === Инициализация БД и менеджера клиентов ===
# Создаем БД на основе DB_TYPE из переменных окружения (по умолчанию: sqlite)
db = create_database()
client_manager = YandexClientManager(YANDEX_TOKEN, db)
context_manager = UserContextManager(db)

# === Инициализация обработчиков ===
command_handlers = CommandHandlers(db, client_manager, context_manager)
callback_handlers = CallbackHandlers(db, context_manager)
message_handlers = MessageHandlers(db, client_manager, context_manager)

# Глобальная переменная для хранения updater (нужна для обработки сигналов)
_updater_instance = None


def error_handler(update: object, context: CallbackContext):
    """Обработчик ошибок."""
    logger.error(f"Ошибка при обработке обновления: {context.error}")
    if update and hasattr(update, 'effective_message'):
        try:
            from utils.message_helpers import send_message, GENERAL_ERROR
            send_message(update, GENERAL_ERROR, use_main_menu=True)
        except:
            pass


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
                CommandHandler("create_playlist", command_handlers.create_playlist_start),
                MessageHandler(Filters.regex("^➕ Создать плейлист$"), command_handlers.create_playlist_start)
            ],
            states={
                WAITING_PLAYLIST_NAME: [
                    MessageHandler(Filters.text & ~Filters.command & ~Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), command_handlers.create_playlist_name)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", command_handlers.cancel_operation),
                CommandHandler("start", command_handlers.cancel_operation),
                MessageHandler(Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), command_handlers.cancel_operation)
            ],
            name="create_playlist",
            persistent=False
        )
        
        # FSM для установки токена
        set_token_conv = ConversationHandler(
            entry_points=[
                CommandHandler("set_token", command_handlers.set_token_start)
            ],
            states={
                WAITING_TOKEN: [
                    MessageHandler(Filters.text & ~Filters.command & ~Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), command_handlers.set_token_input)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", command_handlers.cancel_operation),
                CommandHandler("start", command_handlers.cancel_operation),
                MessageHandler(Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), command_handlers.cancel_operation)
            ],
            name="set_token",
            persistent=False
        )
        
        # Команды
        dp.add_handler(CommandHandler("start", command_handlers.start, pass_args=True))
        dp.add_handler(create_playlist_conv)
        dp.add_handler(set_token_conv)
        dp.add_handler(CommandHandler("my_playlists", command_handlers.my_playlists))
        dp.add_handler(CommandHandler("shared_playlists", command_handlers.shared_playlists))
        dp.add_handler(CommandHandler("playlist_info", command_handlers.playlist_info))
        dp.add_handler(CommandHandler("list", command_handlers.show_list))
        
        # FSM для редактирования названия
        edit_name_conv = ConversationHandler(
            entry_points=[
                CommandHandler("edit_name", command_handlers.edit_name_start),
                CallbackQueryHandler(command_handlers.edit_name_start, pattern="^edit_name_")
            ],
            states={
                WAITING_EDIT_NAME: [
                    MessageHandler(Filters.text & ~Filters.command & ~Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), command_handlers.edit_name_input)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", command_handlers.cancel_operation),
                CommandHandler("start", command_handlers.cancel_operation),
                MessageHandler(Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), command_handlers.cancel_operation)
            ],
            name="edit_name",
            persistent=False
        )
        
        dp.add_handler(edit_name_conv)
        dp.add_handler(CommandHandler("delete_playlist", command_handlers.delete_playlist_cmd))
        
        # FSM для удаления трека
        delete_track_conv = ConversationHandler(
            entry_points=[
                CommandHandler("delete_track", command_handlers.delete_track_start),
                CallbackQueryHandler(command_handlers.delete_track_start, pattern="^delete_track_")
            ],
            states={
                WAITING_TRACK_NUMBER: [
                    # Перехватываем ВСЕ текстовые сообщения (включая просто цифры)
                    # Но исключаем кнопку "Отмена", которая обрабатывается fallback
                    MessageHandler(Filters.text & ~Filters.command & ~Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), command_handlers.delete_track_input)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", command_handlers.cancel_operation),
                CommandHandler("start", command_handlers.cancel_operation),
                MessageHandler(Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), command_handlers.cancel_operation)
            ],
            name="delete_track",
            persistent=False
        )
        
        dp.add_handler(delete_track_conv)
        
        # FSM для установки обложки
        set_cover_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(command_handlers.set_cover_start, pattern="^set_cover_")
            ],
            states={
                WAITING_PLAYLIST_COVER: [
                    MessageHandler(Filters.photo, command_handlers.set_cover_input)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", command_handlers.cancel_operation),
                CommandHandler("start", command_handlers.cancel_operation),
                MessageHandler(Filters.regex("^(❌ Отмена|отмена|🏠 Главное меню)$"), command_handlers.cancel_operation)
            ],
            name="set_cover",
            persistent=False
        )
        
        dp.add_handler(set_cover_conv)
        
        # Обработчики платежей
        dp.add_handler(PreCheckoutQueryHandler(command_handlers.handle_pre_checkout_query))
        dp.add_handler(MessageHandler(Filters.successful_payment, command_handlers.handle_successful_payment))
        
        # Команда покупки лимита
        dp.add_handler(CommandHandler("buy_limit", command_handlers.buy_limit))
        
        # Inline-кнопки
        dp.add_handler(CallbackQueryHandler(callback_handlers.button_callback))
        
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
            message_handlers.handle_menu_buttons
        ))
        
        # Обработка текстовых сообщений (ссылки) - только если не кнопка меню и не команда
        # ConversationHandler обрабатывает свои состояния первым, поэтому этот обработчик
        # сработает только если пользователь НЕ находится в состоянии FSM
        dp.add_handler(MessageHandler(
            Filters.text & ~Filters.command,
            message_handlers.add_command
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
