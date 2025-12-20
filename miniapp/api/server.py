"""
FastAPI сервер для Mini App REST API.
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from miniapp.api.routes import router
from database import DatabaseInterface
from yandex_client_manager import YandexClientManager

logger = logging.getLogger(__name__)

# Глобальные переменные для хранения зависимостей до инициализации
_initial_db: DatabaseInterface = None
_initial_client_manager: YandexClientManager = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Управление жизненным циклом приложения FastAPI.
    
    Инициализирует зависимости при запуске и очищает ресурсы при завершении.
    """
    # Startup
    logger.info("Initializing Mini App API dependencies...")
    
    if _initial_db is None or _initial_client_manager is None:
        raise RuntimeError(
            "Dependencies not set! Call init_app() before starting the server."
        )
    
    # Определяем тип БД
    db_type = os.getenv("DB_TYPE", "sqlite").lower()
    
    if db_type == "postgresql":
        # Для PostgreSQL создаем новый экземпляр с новым connection pool
        # для FastAPI event loop
        from database.postgresql_db import PostgreSQLDatabase
        
        if hasattr(_initial_db, 'host'):
            fastapi_db = PostgreSQLDatabase(
                host=_initial_db.host,
                port=_initial_db.port,
                database=_initial_db.database,
                user=_initial_db.user,
                password=_initial_db.password
            )
        else:
            fastapi_db = PostgreSQLDatabase()
        
        # Инициализируем pool
        await fastapi_db._get_pool()
        
        # Создаем отдельный client_manager для FastAPI с правильной БД
        fastapi_client_manager = YandexClientManager(
            _initial_client_manager.default_token,
            fastapi_db,
            _initial_client_manager.timeout
        )
        await fastapi_client_manager.init_default_account()
        
        # Сохраняем в app.state
        app.state.db = fastapi_db
        app.state.client_manager = fastapi_client_manager
        
        logger.info("PostgreSQL database and client manager initialized for FastAPI event loop")
    else:
        # Для SQLite используем тот же экземпляр (с блокировкой)
        app.state.db = _initial_db
        app.state.client_manager = _initial_client_manager
        logger.info("SQLite database and client manager initialized (shared instance)")
    
    logger.info("Mini App API dependencies initialized successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Mini App API...")
    
    # Закрываем соединения с БД, если нужно
    if hasattr(app.state, 'db'):
        db = app.state.db
        if hasattr(db, 'close'):
            await db.close()
            logger.info("Database connections closed")
    
    logger.info("Mini App API shutdown complete")


# Создаем FastAPI приложение с lifespan
# root_path нужен для работы за прокси (nginx добавляет префикс /api)
app = FastAPI(
    title="Mini App API",
    description="REST API для Telegram Mini App",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/api"  # Префикс, который добавляет nginx при проксировании
)

# Глобальный обработчик исключений
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Глобальный обработчик исключений для детального логирования."""
    logger.exception(f"Unhandled exception: {exc}", exc_info=exc)
    import os
    if os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG":
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Internal server error: {str(exc)}",
                "type": type(exc).__name__
            }
        )
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# CORS для Telegram
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роуты API
# Префикс /api не нужен, т.к. nginx уже добавляет его при проксировании
app.include_router(router)


def init_app(db: DatabaseInterface, client_manager: YandexClientManager):
    """
    Инициализировать приложение с зависимостями.
    
    Зависимости сохраняются в глобальные переменные и будут использованы
    в lifespan event при запуске FastAPI сервера.
    
    Args:
        db: Интерфейс базы данных
        client_manager: Менеджер клиентов Яндекс.Музыки
    """
    global _initial_db, _initial_client_manager
    
    if db is None:
        raise ValueError("Database cannot be None")
    if client_manager is None:
        raise ValueError("Client manager cannot be None")
    
    _initial_db = db
    _initial_client_manager = client_manager
    logger.info("Mini App API dependencies set (will be initialized on startup)")


# Раздача статики (для разработки, в проде через nginx)
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    @app.get("/")
    async def serve_index():
        """Отдать index.html."""
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Mini App static files not found"}
    
    # Раздача статических файлов
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    # Раздача CSS и JS напрямую (для удобства)
    css_dir = os.path.join(static_dir, "css")
    js_dir = os.path.join(static_dir, "js")
    
    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.exists(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")

