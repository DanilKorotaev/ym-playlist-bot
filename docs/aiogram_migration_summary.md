# Краткое описание миграции на aiogram 3.x

## Статус: ✅ ЗАВЕРШЕНО

Миграция с `python-telegram-bot==13.15` на `aiogram==3.16.0` успешно завершена.

## Основные изменения

### 1. Зависимости

**Было:**
```
python-telegram-bot==13.15
```

**Стало:**
```
aiogram==3.16.0
aiosqlite==0.20.0  # для будущей полной асинхронности БД
```

### 2. Архитектура бота

**Было:**
```python
from telegram.ext import Updater, CommandHandler, MessageHandler

updater = Updater(token=TELEGRAM_TOKEN)
dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler("start", start_handler))
updater.start_polling()
```

**Стало:**
```python
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.message.register(start_handler, CommandStart())
await dp.start_polling(bot)
```

### 3. Handlers

**Было:**
```python
def start_handler(update: Update, context: CallbackContext):
    update.message.reply_text("Hello!")
```

**Стало:**
```python
async def start_handler(message: Message):
    await message.answer("Hello!")
```

### 4. FSM (Finite State Machine)

**Было:**
```python
from telegram.ext import ConversationHandler

WAITING_NAME = 1

def start_create(update, context):
    context.user_data['state'] = WAITING_NAME
    return WAITING_NAME

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("create", start_create)],
    states={WAITING_NAME: [MessageHandler(Filters.text, handle_name)]},
    fallbacks=[CommandHandler("cancel", cancel)]
)
```

**Стало:**
```python
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

class CreatePlaylistStates(StatesGroup):
    waiting_playlist_name = State()

async def start_create(message: Message, state: FSMContext):
    await state.set_state(CreatePlaylistStates.waiting_playlist_name)

dp.message.register(start_create, Command("create"))
dp.message.register(handle_name, CreatePlaylistStates.waiting_playlist_name)
```

### 5. Работа с БД

**Было:**
```python
playlist = self.db.get_playlist(playlist_id)
```

**Стало:**
```python
import asyncio

playlist = await asyncio.to_thread(self.db.get_playlist, playlist_id)
```

### 6. Работа с Yandex Music API

**Было:**
```python
client = self.client_manager.get_client(telegram_id)
playlist = client.users_playlists_create(title)
```

**Стало:**
```python
client = await self.client_manager.get_client(telegram_id)
# Синхронные вызовы обернуты в asyncio.to_thread() внутри метода
playlist = await self.client_manager.create_playlist(telegram_id, title)
```

### 7. Получение экземпляра Bot

**Было:**
```python
from aiogram import Bot
bot = Bot.get_current()  # Устаревший метод
bot_info = await bot.get_me()
```

**Стало:**
```python
# Bot доступен через объекты событий
bot_info = await message.bot.get_me()  # В message handlers
# или
bot_info = await query.bot.get_me()  # В callback handlers
```

### 8. Создание клавиатур

**Было:**
```python
from telegram import ReplyKeyboardMarkup

keyboard = ReplyKeyboardMarkup(
    [["Кнопка 1", "Кнопка 2"]],
    resize_keyboard=True
)
```

**Стало:**
```python
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Кнопка 1"),
            KeyboardButton(text="Кнопка 2")
        ]
    ],
    resize_keyboard=True
)
```

### 9. Обработчик ошибок

**Было:**
```python
async def error_handler(update, exception):
    logger.error(f"Ошибка: {exception}")
```

**Стало:**
```python
async def error_handler(event, data):
    # В aiogram 3.x обработчик вызывается с (event, data)
    exception = data.get('exception') if isinstance(data, dict) else data
    logger.error(f"Ошибка: {exception}", exc_info=exception)
```

## Преимущества миграции

1. **Производительность**: Асинхронная обработка позволяет обрабатывать больше запросов одновременно
2. **Масштабируемость**: Лучшая производительность при росте числа пользователей
3. **Современный подход**: aiogram 3.x - активно развивающаяся библиотека с хорошей документацией
4. **FSM**: Более гибкая и понятная система состояний через `StatesGroup`

## Обратная совместимость

- Все команды бота работают так же, как и раньше
- Пользовательский опыт не изменился
- Изменения касаются только внутренней реализации

## Будущие улучшения

1. **Полная асинхронность БД**: Миграция на `asyncpg` (PostgreSQL) и `aiosqlite` (SQLite) для убирания оберток `asyncio.to_thread()`
2. **Тестирование**: Добавление unit-тестов для проверки работы всех handlers
3. **Мониторинг**: Настройка мониторинга производительности после миграции

## Полезные ссылки

- [Документация aiogram 3.x](https://docs.aiogram.dev/)
- [План миграции](aiogram_migration_plan.md)
- [Архитектура проекта](architecture.md)

