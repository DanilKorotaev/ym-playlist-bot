"""
Модуль для работы с базой данных.
Поддерживает несколько типов БД через полиморфизм.

Использование:
    from database import create_database
    
    db = create_database()  # Создает БД на основе DB_TYPE из переменных окружения
"""
import os
import logging
from typing import Optional

from .base import DatabaseInterface
from .sqlite_db import SQLiteDatabase
from .postgresql_db import PostgreSQLDatabase

logger = logging.getLogger(__name__)

# Типы поддерживаемых БД
DB_TYPE_SQLITE = "sqlite"
DB_TYPE_POSTGRESQL = "postgresql"


def create_database(
    db_type: Optional[str] = None,
    **kwargs
) -> DatabaseInterface:
    """
    Фабрика для создания экземпляра базы данных.
    
    Args:
        db_type: Тип БД ('sqlite' или 'postgresql'). 
                 Если не указан, берется из переменной окружения DB_TYPE.
                 Если DB_TYPE не установлена, используется 'sqlite' по умолчанию.
        **kwargs: Дополнительные параметры для конкретной реализации БД.
                  Для SQLite: db_file
                  Для PostgreSQL: host, port, database, user, password
    
    Returns:
        Экземпляр DatabaseInterface (SQLiteDatabase или PostgreSQLDatabase)
    
    Raises:
        ValueError: Если указан неподдерживаемый тип БД
    """
    # Определяем тип БД
    if db_type is None:
        db_type = os.getenv("DB_TYPE", DB_TYPE_SQLITE).lower()
    
    # Создаем соответствующую реализацию
    if db_type == DB_TYPE_SQLITE:
        logger.info("Инициализация SQLite базы данных")
        return SQLiteDatabase(**kwargs)
    elif db_type == DB_TYPE_POSTGRESQL:
        logger.info("Инициализация PostgreSQL базы данных")
        return PostgreSQLDatabase(**kwargs)
    else:
        raise ValueError(
            f"Неподдерживаемый тип БД: {db_type}. "
            f"Поддерживаемые типы: {DB_TYPE_SQLITE}, {DB_TYPE_POSTGRESQL}"
        )


# Для обратной совместимости - экспортируем DatabaseInterface как Database
Database = DatabaseInterface

# Экспортируем конкретные реализации для прямого использования при необходимости
__all__ = [
    "DatabaseInterface",
    "Database",
    "SQLiteDatabase",
    "PostgreSQLDatabase",
    "create_database",
    "DB_TYPE_SQLITE",
    "DB_TYPE_POSTGRESQL",
]

