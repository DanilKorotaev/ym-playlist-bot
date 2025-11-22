# Architecture

## Текущая реализация (v2.0)

### Telegram Layer
- **Библиотека**: `python-telegram-bot==13.15` (синхронная версия)
- **Обработчики**: CommandHandler, MessageHandler, CallbackQueryHandler
- **FSM**: Не реализовано (команды принимают аргументы в строке или через интерактивные кнопки)
- **Основной файл**: `bot.py`

### Domain Layer
- **YandexClientManager** (`yandex_client_manager.py`): 
  - Управление клиентами Яндекс.Музыки
  - Поддержка дефолтного токена и пользовательских токенов
  - Создание плейлистов через API
- **Парсинг ссылок**: Встроен в `bot.py`
  - Треки, альбомы, плейлисты
  - Токены для шаринга плейлистов

### Storage Layer
- **База данных**: SQLite (`bot.db`)
- **Модуль**: `database.py` (синхронный SQLite)
- **Таблицы**:
  - `users` - пользователи Telegram
  - `yandex_accounts` - аккаунты Яндекс.Музыки (дефолтный + пользовательские)
  - `playlists` - плейлисты
  - `playlist_access` - права доступа к плейлистам
  - `actions` - история действий пользователей

### Config
- **Переменные окружения**: `.env` файл через `python-dotenv`
- **Обязательные**: `TELEGRAM_TOKEN`, `YANDEX_TOKEN`

### Структура проекта
```
ym-playlist-bot/
├── bot.py                 # Основной файл бота
├── database.py            # Работа с SQLite БД
├── yandex_client_manager.py  # Управление клиентами Яндекс.Музыки
└── docs/                  # Документация
```

## Планируемые улучшения

- **Telegram Layer**: Миграция на `aiogram 3.x` с полноценной FSM-логикой
- **Storage Layer**: Миграция на PostgreSQL через async SQLAlchemy
- **Docker**: docker-compose с сервисами bot + db + pgadmin
- **Config**: pydantic-based settings для валидации конфигурации
- **Модульная структура**: Разделение на handlers/, services/, storage/, config/
