# Architecture

## Текущая реализация (v4.0)

### Telegram Layer
- **Библиотека**: `aiogram==3.16.0` (асинхронная версия) ✅
- **Обработчики**: Используется `dp.message.register()` и `dp.callback_query.register()` для регистрации handlers
- **FSM**: Реализовано через aiogram FSM (`StatesGroup` и `FSMContext`) для интерактивных диалогов
- **Основной файл**: `bot.py` (инициализация `Bot` и `Dispatcher`, регистрация handlers)
- **Модули**:
  - `handlers/commands.py` - обработчики команд бота (все методы `async def`)
  - `handlers/callbacks.py` - обработчики callback query (все методы `async def`)
  - `handlers/messages.py` - обработчики текстовых сообщений (все методы `async def`)
  - `handlers/keyboards.py` - клавиатуры Telegram
  - `handlers/states.py` - определения FSM состояний через `StatesGroup`

### Domain Layer (Services)
- **YandexClientManager** (`yandex_client_manager.py`): 
  - Управление клиентами Яндекс.Музыки
  - Поддержка дефолтного токена и пользовательских токенов
  - Создание плейлистов через API
- **Services** (`services/`):
  - `link_parser.py` - парсинг ссылок Яндекс.Музыки (треки, альбомы, плейлисты, токены)
  - `yandex_service.py` - высокоуровневые методы для работы с API Яндекс.Музыки
    - Получение треков, альбомов, плейлистов
    - Добавление/удаление треков в плейлистах (с автоматической обработкой revision)
    - Автоматический расчет позиции вставки на основе настройки плейлиста (в начало или в конец)
    - Форматирование треков для отображения
    - Извлечение информации о треках (track_id, album_id)
  - `playlist_service.py` - бизнес-логика работы с плейлистами
    - Добавление/удаление треков (с проверкой прав доступа и логированием)
    - Использование настройки `insert_position` из БД для определения места добавления треков
    - Получение треков и их количества (возвращает `Optional` для явного указания отсутствия плейлиста)
    - Формирование ссылок для шаринга и Яндекс.Музыки
    - Получение объекта плейлиста из Яндекс.Музыки
  - `payment_service.py` - бизнес-логика работы с платежами через Telegram Stars
    - Управление тарифными планами (5, 10, unlimited плейлистов)
    - Генерация и парсинг invoice payload для платежей
    - Создание платежей и обработка успешных платежей
    - Активация подписок после успешной оплаты

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
  - `playlists` - плейлисты (включая настройку `insert_position` для выбора места добавления треков)
  - `playlist_access` - права доступа к плейлистам
  - `actions` - история действий пользователей
  - `user_subscriptions` - подписки пользователей на расширенные лимиты
  - `payments` - история платежей через Telegram Stars

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
│   ├── playlist_service.py      # Бизнес-логика плейлистов
│   └── payment_service.py       # Бизнес-логика платежей через Telegram Stars
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
6. **Разделение ответственности**: 
   - `YandexService` - вся работа с API Яндекс.Музыки (получение revision, повторные попытки)
   - `PlaylistService` - бизнес-логика (проверка прав, логирование)
   - `handlers` - только обработка Telegram-событий
7. **Отсутствие дублирования**: Общая логика вынесена в переиспользуемые методы сервисов
8. **Платежи**: Интеграция с Telegram Stars для монетизации через расширенные лимиты

## Примеры использования сервисов

Бизнес-логика в `services/` может использоваться независимо от Telegram бота, например, в консольных скриптах для отладки или автоматизации.

### Пример 1: Парсинг ссылок

```python
from services.link_parser import parse_track_link, parse_album_link, parse_playlist_link

# Парсинг ссылки на трек
track_id = parse_track_link("https://music.yandex.ru/track/123456")
# Результат: 123456

# Парсинг ссылки на альбом
album_id = parse_album_link("https://music.yandex.ru/album/789")
# Результат: 789

# Парсинг ссылки на плейлист
owner, playlist_id = parse_playlist_link("https://music.yandex.ru/users/user123/playlists/456")
# Результат: ('user123', '456')
```

### Пример 2: Работа с API Яндекс.Музыки

```python
from yandex_music import Client
from services.yandex_service import YandexService

# Создаем клиент
client = Client("YOUR_TOKEN")
client.init()

# Создаем сервис
yandex_service = YandexService(client)

# Получаем трек
track = yandex_service.get_track(123456)

# Форматируем трек для отображения
track_display = yandex_service.format_track(track)
# Результат: "Название трека — Исполнитель1 / Исполнитель2"

# Извлекаем информацию о треке
track_id, album_id = yandex_service.extract_track_info(track)
```

### Пример 3: Работа с плейлистами

```python
from database import create_database
from yandex_client_manager import YandexClientManager
from services.playlist_service import PlaylistService

# Инициализация
db = create_database()
client_manager = YandexClientManager("YANDEX_TOKEN", db)
playlist_service = PlaylistService(db, client_manager)

# Добавление трека в плейлист
ok, error = playlist_service.add_track(
    playlist_id=1,
    track_id=123456,
    album_id=789,
    telegram_id=123456789
)

# Получение треков из плейлиста
tracks = playlist_service.get_playlist_tracks(playlist_id=1, telegram_id=123456789)
if tracks is None:
    print("Плейлист не найден")
elif not tracks:
    print("Плейлист пуст")
else:
    print(f"В плейлисте {len(tracks)} треков")

# Получение количества треков
count = playlist_service.get_playlist_tracks_count(playlist_id=1, telegram_id=123456789)
if count is None:
    print("Плейлист не найден")
else:
    print(f"Количество треков: {count}")

# Формирование ссылок
share_link = playlist_service.get_share_link(playlist_id=1, bot_username="my_bot")
yandex_link = playlist_service.get_yandex_link(playlist_id=1)
```

### Пример 4: Работа с платежами

```python
from database import create_database
from services.payment_service import PaymentService

# Инициализация
db = create_database()
payment_service = PaymentService(db)

# Получение доступных тарифов
plans = payment_service.get_available_plans()
for plan_id, plan_data in plans.items():
    print(f"{plan_data['name']}: {plan_data['stars']} Stars")

# Создание платежа
telegram_id = 123456789
subscription_type = "playlist_limit_5"
payment_data = payment_service.create_payment(telegram_id, subscription_type)

if payment_data:
    print(f"Payment ID: {payment_data['payment_id']}")
    print(f"Payload: {payment_data['payload']}")
    print(f"Stars amount: {payment_data['stars_amount']}")

# Обработка успешного платежа
invoice_payload = payment_data['payload']
stars_amount = payment_data['stars_amount']
success = payment_service.process_successful_payment(
    telegram_id=telegram_id,
    invoice_payload=invoice_payload,
    stars_amount=stars_amount
)

if success:
    print("Подписка активирована!")
    
# Получение текущего лимита пользователя (с учетом подписки)
user_limit = db.get_user_playlist_limit(telegram_id)
print(f"Текущий лимит: {user_limit} плейлистов" if user_limit != -1 else "Текущий лимит: безлимит")
```

## Планируемые улучшения

### Исправление багов
- **Удаление треков**: Исправить проблему с удалением треков - API не изменяет количество треков, но не возвращает ошибку. Требуется изучение поведения API и улучшение валидации.

### Рефакторинг
- **Унификация отправки сообщений**: ✅ Создана утилита `utils/message_helpers.py` для унифицированной отправки сообщений, устранено дублирование между `update.callback_query.message.reply_text` и `update.effective_message.reply_text`
- **Общие ответы**: ✅ Вынесены повторяющиеся сообщения (например, "❌ У вас нет активного плейлиста") в константы в `utils/message_helpers.py`
- **Разбиение больших методов**: ✅ Рефакторинг `button_callback` в `handlers/callbacks.py` - вынесены каждый `if` блок в отдельный метод

### Новые функции
- **Управление треками по авторству**: Возможность удалять треки тем, кто их добавил. Требуется хранение информации о том, кто добавил каждый трек.
- **Статистика по плейлистам**: Отображение, кто сколько треков и какие именно добавил в плейлист. Команда для просмотра статистики.
- **Улучшение ссылок на плейлисты**: Отображение ссылки в формате `https://music.yandex.ru/playlists/{uuid}` вместо текущего формата с owner_id и playlist_kind.

### Технические улучшения
- **Telegram Layer**: ✅ Миграция на `aiogram 3.x` с полноценной FSM-логикой завершена
- **Storage Layer**: Синхронные вызовы БД обернуты в `asyncio.to_thread()` для неблокирующей работы. В будущем можно мигрировать на `asyncpg`/`aiosqlite` для полной асинхронности
- **Docker**: docker-compose с сервисами bot + db + pgadmin (уже реализовано)
- **Config**: pydantic-based settings для валидации конфигурации
- **Тесты**: Добавление unit-тестов для services и handlers
