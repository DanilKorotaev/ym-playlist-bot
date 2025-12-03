# План миграции на aiogram 3.x

## Общая информация

- **Текущее состояние**: ✅ **МИГРАЦИЯ ЗАВЕРШЕНА** - Проект использует `aiogram==3.16.0` (асинхронная версия)
- **Цель**: Мигрировать на `aiogram 3.x` для использования асинхронного подхода и улучшения производительности
- **Приоритет**: Высокий (улучшение производительности и современный подход)
- **Статус**: ✅ **ЗАВЕРШЕНО** - Миграция успешно завершена

## Риски

- Несовместимость библиотеки `yandex-music` с асинхронным кодом (может потребоваться обертка)
- Необходимость миграции БД на асинхронные драйверы (asyncpg/aiosqlite)
- Возможные проблемы с производительностью при обертке синхронных вызовов
- Необходимость переобучения команды на новый API

## Этап 1: Подготовка и исследование

- [x] Изучить документацию aiogram 3.x и основные отличия от python-telegram-bot
- [x] Проанализировать совместимость библиотеки `yandex-music` с асинхронным кодом
- [x] Проверить совместимость БД (PostgreSQL/SQLite) с асинхронными операциями
- [x] Создать отдельную ветку для миграции (`feature/aiogram3-migration`)
- [x] Создать резервную копию текущего рабочего кода

## Этап 2: Обновление зависимостей

- [x] Обновить `requirements.txt`: заменить `python-telegram-bot==13.15` на `aiogram==3.16.0`
- [x] Проверить совместимость других зависимостей (`yandex-music`, `psycopg2-binary`, `python-dotenv`)
- [x] При необходимости добавить `aiosqlite` для асинхронной работы с SQLite
- [x] При необходимости добавить `asyncpg` для асинхронной работы с PostgreSQL (альтернатива `psycopg2-binary`)
- [x] Обновить Dockerfile, если потребуется изменение зависимостей

## Этап 3: Миграция базовых компонентов

- [x] Мигрировать `bot.py`:
  - Заменить `Updater` на `Bot` и `Dispatcher`
  - Изменить `start_polling()` на `dp.start_polling()`
  - Обновить обработку сигналов для корректного завершения
  - Изменить структуру инициализации на асинхронную
- [x] Мигрировать `handlers/keyboards.py`:
  - Заменить `ReplyKeyboardMarkup` из `telegram` на `ReplyKeyboardMarkup` из `aiogram.types`
  - Обновить импорты
- [x] Мигрировать `utils/message_helpers.py`:
  - Заменить `Update`, `Message`, `CallbackQuery` на типы из `aiogram`
  - Изменить функции на `async def`
  - Обновить методы отправки/редактирования сообщений под aiogram API

## Этап 4: Миграция обработчиков команд

- [x] Мигрировать `handlers/commands.py`:
  - Изменить все методы класса `CommandHandlers` на `async def`
  - Заменить `Update` и `CallbackContext` на типы из aiogram (`Message`, `CallbackQuery`, `FSMContext`)
  - Обновить методы работы с сообщениями (`reply_text`, `edit_message_text` и т.д.)
  - Заменить `ConversationHandler` на aiogram FSM (использовать `FSMContext` и состояния)
  - Мигрировать FSM состояния:
    - `WAITING_PLAYLIST_NAME` → `CreatePlaylistStates.waiting_playlist_name`
    - `WAITING_TOKEN` → `SetTokenStates.waiting_token`
    - `WAITING_EDIT_NAME` → `EditNameStates.waiting_edit_name`
    - `WAITING_TRACK_NUMBER` → `DeleteTrackStates.waiting_track_number`
    - `WAITING_PLAYLIST_COVER` → `SetCoverStates.waiting_playlist_cover`
  - Обновить регистрацию обработчиков в `bot.py` (использовать `dp.message.register()` вместо `CommandHandler`)

## Этап 5: Миграция обработчиков callback и сообщений

- [x] Мигрировать `handlers/callbacks.py`:
  - Изменить все методы на `async def`
  - Заменить `CallbackQuery` на тип из aiogram
  - Обновить методы работы с callback query (`answer()`, `edit_message_text()`)
  - Обновить регистрацию в `bot.py` (использовать `dp.callback_query.register()`)
- [x] Мигрировать `handlers/messages.py`:
  - Изменить все методы на `async def`
  - Обновить обработку текстовых сообщений и ссылок
  - Обновить фильтры для обработки сообщений (использовать aiogram фильтры)
  - Обновить регистрацию в `bot.py`

## Этап 6: Миграция работы с БД и сервисами

- [x] Проверить и обновить `database/base.py`:
  - Определить, нужны ли асинхронные методы в интерфейсе БД
  - Решение: оставить синхронные методы, обернуть вызовы в `asyncio.to_thread()` в handlers
- [x] Мигрировать `database/postgresql_db.py`:
  - Решение: оставить синхронные методы, обернуть вызовы в `asyncio.to_thread()` для совместимости
  - Можно мигрировать на `asyncpg` в будущем для полной асинхронности
- [x] Мигрировать `database/sqlite_db.py`:
  - Решение: оставить синхронные методы, обернуть вызовы в `asyncio.to_thread()` для совместимости
  - Можно мигрировать на `aiosqlite` в будущем для полной асинхронности
- [x] Обновить `yandex_client_manager.py`:
  - Проверить, поддерживает ли `yandex-music` асинхронные операции
  - Решение: обернуть синхронные вызовы в `asyncio.to_thread()`
  - Обновить методы на `async def`
- [x] Обновить сервисы (`services/yandex_service.py`, `services/playlist_service.py`, `services/payment_service.py`, `services/link_parser.py`):
  - Изменить методы на `async def`
  - Обновить вызовы БД и клиентов на асинхронные (через `asyncio.to_thread()`)
- [x] Обновить `utils/context.py`:
  - Изменить методы на `async def`
  - Обновить работу с БД на асинхронную (через `asyncio.to_thread()`)

## Этап 7: Обновление FSM (Finite State Machine)

- [x] Создать файл `handlers/states.py` с определениями состояний FSM через aiogram:
  - `CreatePlaylistStates` (waiting_playlist_name)
  - `SetTokenStates` (waiting_token)
  - `EditNameStates` (waiting_edit_name)
  - `DeleteTrackStates` (waiting_track_number)
  - `SetCoverStates` (waiting_playlist_cover)
- [x] Обновить обработчики для использования FSM состояний вместо числовых констант
- [x] Заменить `ConversationHandler` на aiogram FSM роутеры
- [x] Обновить логику переходов между состояниями

## Этап 8: Обновление обработки ошибок и middleware

- [x] Обновить `error_handler` в `bot.py` для работы с aiogram
- [x] При необходимости добавить middleware для обработки ошибок
- [x] Обновить логирование ошибок под новую структуру

## Этап 9: Тестирование

- [ ] Протестировать все команды бота (`/start`, `/create_playlist`, `/my_playlists` и т.д.)
- [ ] Протестировать FSM диалоги (создание плейлиста, установка токена, редактирование названия, удаление трека, установка обложки)
- [ ] Протестировать callback query (выбор плейлиста, удаление, редактирование, покупка лимитов)
- [ ] Протестировать обработку текстовых сообщений (добавление треков, альбомов, плейлистов)
- [ ] Протестировать обработку платежей (Telegram Stars)
- [ ] Проверить работу с БД (создание пользователей, плейлистов, треков)
- [ ] Проверить работу с API Яндекс.Музыки
- [ ] Проверить обработку ошибок и edge cases
- [ ] Провести нагрузочное тестирование (множественные одновременные запросы)

## Этап 10: Документация и финализация

- [x] Обновить `docs/architecture/architecture.md` с описанием новой архитектуры на aiogram 3.x
- [x] Обновить `README.md` с информацией о миграции и новых зависимостях
- [ ] Обновить `docs/instructions/commands.md` при необходимости
- [ ] Создать `docs/migration_guide.md` с описанием процесса миграции и основных изменений
- [ ] Обновить комментарии в коде при необходимости
- [ ] Проверить и обновить CI/CD pipeline при необходимости

## Этап 11: Развертывание

- [ ] Создать pull request с миграцией
- [ ] Провести code review
- [ ] Протестировать на staging окружении
- [ ] Развернуть на production после успешного тестирования
- [ ] Мониторить работу бота после развертывания

## Документация

- [Краткое описание миграции](aiogram_migration_summary.md) - основные изменения и примеры кода
- [Архитектура проекта](architecture.md) - обновленная архитектура с aiogram 3.x
- [План миграции](aiogram_migration_plan.md) - этот файл

## Основные изменения

### Архитектурные изменения

1. **Асинхронность**: Все handlers теперь используют `async def` и `await`
2. **FSM**: Заменен `ConversationHandler` на aiogram FSM с состояниями через `StatesGroup`
3. **Регистрация handlers**: Используется `dp.message.register()` и `dp.callback_query.register()` вместо `CommandHandler`, `MessageHandler`, `CallbackQueryHandler`
4. **Работа с БД**: Синхронные вызовы БД обернуты в `asyncio.to_thread()` для неблокирующей работы
5. **Yandex Music API**: Синхронные вызовы библиотеки `yandex-music` обернуты в `asyncio.to_thread()`

### Технические детали

- **Библиотека**: `aiogram==3.16.0` вместо `python-telegram-bot==13.15`
- **Дополнительные зависимости**: `aiosqlite==0.20.0` (для будущей полной асинхронности БД)
- **Обработка ошибок**: Обновлен `error_handler` для работы с aiogram событиями
- **Сигналы**: Обновлена обработка сигналов для корректного завершения асинхронного бота

