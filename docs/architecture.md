# Architecture

## Текущая реализация (v3.0)

### Telegram Layer
- **Библиотека**: `python-telegram-bot==13.15` (синхронная версия)
- **Обработчики**: CommandHandler, MessageHandler, CallbackQueryHandler
- **FSM**: Реализовано через ConversationHandler для интерактивных диалогов
- **Основной файл**: `bot.py` (только инициализация и регистрация handlers)
- **Модули**:
  - `handlers/commands.py` - обработчики команд бота
  - `handlers/callbacks.py` - обработчики callback query
  - `handlers/messages.py` - обработчики текстовых сообщений
  - `handlers/keyboards.py` - клавиатуры Telegram

### Domain Layer (Services)
- **YandexClientManager** (`yandex_client_manager.py`): 
  - Управление клиентами Яндекс.Музыки
  - Поддержка дефолтного токена и пользовательских токенов
  - Создание плейлистов через API
- **Services** (`services/`):
  - `link_parser.py` - парсинг ссылок Яндекс.Музыки (треки, альбомы, плейлисты, токены)
  - `yandex_service.py` - высокоуровневые методы для работы с API Яндекс.Музыки
  - `playlist_service.py` - бизнес-логика работы с плейлистами (добавление/удаление треков)

### Utils Layer
- **UserContextManager** (`utils/context.py`):
  - Управление контекстом пользователей (активный плейлист)
  - Независим от Telegram, может использоваться в консольных скриптах

### Storage Layer
- **База данных**: SQLite или PostgreSQL (настраивается через переменную окружения `DB_TYPE`)
- **Модуль**: `database/` (абстракция через DatabaseInterface)
  - `base.py` - интерфейс DatabaseInterface
  - `sqlite_db.py` - реализация для SQLite
  - `postgresql_db.py` - реализация для PostgreSQL
- **Таблицы**:
  - `users` - пользователи Telegram
  - `yandex_accounts` - аккаунты Яндекс.Музыки (дефолтный + пользовательские)
  - `playlists` - плейлисты
  - `playlist_access` - права доступа к плейлистам
  - `actions` - история действий пользователей

### Config
- **Переменные окружения**: `.env` файл через `python-dotenv`
- **Обязательные**: `TELEGRAM_TOKEN`, `YANDEX_TOKEN`
- **Опциональные**: `DB_TYPE` (sqlite/postgresql)

### Структура проекта
```
ym-playlist-bot/
├── bot.py                      # Точка входа, инициализация и регистрация handlers
├── yandex_client_manager.py    # Управление клиентами Яндекс.Музыки
├── database/                    # Модуль работы с БД
│   ├── __init__.py
│   ├── base.py                  # Интерфейс DatabaseInterface
│   ├── sqlite_db.py             # Реализация для SQLite
│   └── postgresql_db.py         # Реализация для PostgreSQL
├── services/                    # Бизнес-логика (независима от Telegram)
│   ├── __init__.py
│   ├── link_parser.py           # Парсинг ссылок
│   ├── yandex_service.py        # Работа с API Яндекс.Музыки
│   └── playlist_service.py      # Бизнес-логика плейлистов
├── handlers/                    # Обработчики Telegram
│   ├── __init__.py
│   ├── commands.py              # Команды бота
│   ├── callbacks.py             # Callback query
│   ├── messages.py              # Текстовые сообщения
│   └── keyboards.py             # Клавиатуры
├── utils/                       # Утилиты
│   ├── __init__.py
│   └── context.py               # Управление контекстом пользователей
└── docs/                        # Документация
```

## Преимущества новой структуры

1. **Модульность**: Код разделен на логические модули, каждый отвечает за свою область
2. **Переиспользование**: Бизнес-логика в `services/` может использоваться как в боте, так и в консольных скриптах
3. **Тестируемость**: Каждый модуль можно тестировать независимо
4. **Масштабируемость**: Легко добавлять новые handlers и services
5. **Читаемость**: `bot.py` стал намного короче и понятнее

## Планируемые улучшения

- **Telegram Layer**: Миграция на `aiogram 3.x` с полноценной FSM-логикой
- **Storage Layer**: Улучшение работы с PostgreSQL через async SQLAlchemy
- **Docker**: docker-compose с сервисами bot + db + pgadmin (уже реализовано)
- **Config**: pydantic-based settings для валидации конфигурации
- **Тесты**: Добавление unit-тестов для services и handlers
