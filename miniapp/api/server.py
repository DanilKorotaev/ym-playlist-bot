"""
FastAPI сервер для Mini App REST API.
"""
import os
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from miniapp.api.routes import router, set_dependencies
from database import DatabaseInterface
from yandex_client_manager import YandexClientManager

logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI(
    title="Mini App API",
    description="REST API для Telegram Mini App",
    version="1.0.0"
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
app.include_router(router, prefix="/api")


def init_app(db: DatabaseInterface, client_manager: YandexClientManager):
    """
    Инициализировать приложение с зависимостями.
    
    Args:
        db: Интерфейс базы данных
        client_manager: Менеджер клиентов Яндекс.Музыки
    """
    if db is None:
        raise ValueError("Database cannot be None")
    if client_manager is None:
        raise ValueError("Client manager cannot be None")
    
    set_dependencies(db, client_manager)
    logger.info("Mini App API initialized")


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

