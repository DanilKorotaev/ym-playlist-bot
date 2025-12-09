"""
Точка входа для запуска Mini App API в отдельном контейнере.
"""
import os
import logging
import asyncio
import signal
import sys
from dotenv import load_dotenv
import uvicorn

from database import create_database
from yandex_client_manager import YandexClientManager
from miniapp.api.server import app, init_app

load_dotenv()

# Логирование
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, LOG_LEVEL, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Явно устанавливаем уровень для всех логгеров miniapp.api.*
logging.getLogger("miniapp.api").setLevel(log_level)

logger = logging.getLogger(__name__)

# Глобальные переменные
db = None
client_manager = None


async def init():
    """Инициализация БД и зависимостей."""
    global db, client_manager
    
    logger.info("Инициализация Mini App API...")
    
    # Создаем БД
    db = create_database()
    await db.init_db()
    logger.info("База данных инициализирована")
    
    # Создаем client_manager
    yandex_token = os.getenv("YANDEX_TOKEN")
    if not yandex_token:
        raise ValueError("YANDEX_TOKEN не установлен")
    
    client_manager = YandexClientManager(yandex_token, db)
    await client_manager.init_default_account()
    logger.info("YandexClientManager инициализирован")
    
    # Инициализируем FastAPI приложение с зависимостями
    # Зависимости будут инициализированы в lifespan event при запуске сервера
    init_app(db, client_manager)
    logger.info("FastAPI зависимости установлены (инициализация произойдет при запуске сервера)")
    
    logger.info("Mini App API готов к запуску")


def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения."""
    logger.info(f"Получен сигнал {signum}, завершаю работу API...")
    sys.exit(0)


async def main():
    """Главная функция."""
    try:
        # Регистрируем обработчики сигналов
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        logger.info("Запуск Mini App API...")
        
        # Инициализируем зависимости
        await init()
        
        # Получаем порт из переменных окружения
        api_port = int(os.getenv("MINIAPP_API_PORT", "8000"))
        api_host = os.getenv("MINIAPP_API_HOST", "0.0.0.0")
        
        logger.info(f"Запуск FastAPI сервера на {api_host}:{api_port}...")
        
        # Маппим уровни Python logging в уровни uvicorn
        uvicorn_log_level_map = {
            logging.DEBUG: "debug",
            logging.INFO: "info",
            logging.WARNING: "warning",
            logging.ERROR: "error",
            logging.CRITICAL: "critical"
        }
        uvicorn_log_level = uvicorn_log_level_map.get(log_level, "info")
        logger.debug(f"Уровень логирования: Python={LOG_LEVEL} ({log_level}), Uvicorn={uvicorn_log_level}")
        
        # Запускаем uvicorn
        config = uvicorn.Config(
            app,
            host=api_host,
            port=api_port,
            log_level=uvicorn_log_level,
            loop="asyncio"
        )
        server = uvicorn.Server(config)
        await server.serve()
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания, завершаю работу...")
    except Exception as e:
        logger.exception(f"Критическая ошибка при запуске API: {e}")
        raise
    finally:
        if db:
            # Закрываем соединения с БД
            if hasattr(db, 'close'):
                await db.close()
            logger.info("Соединения с БД закрыты")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("API остановлен пользователем")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        sys.exit(1)

