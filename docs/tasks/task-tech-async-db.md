# Задача: Полная асинхронность БД

## Описание

Миграция на полностью асинхронную работу с базой данных для улучшения производительности и устранения необходимости использования `asyncio.to_thread()`.

## Проблема

Сейчас все методы БД синхронные и вызываются через `asyncio.to_thread()`, что:
- Создает дополнительный overhead на переключение контекста
- Не использует преимущества нативной асинхронности
- Усложняет код (нужно помнить про обертки)

## Цель

Перевести все методы БД на асинхронные:
- PostgreSQL: использовать `asyncpg` вместо `psycopg2`
- SQLite: использовать `aiosqlite` вместо `sqlite3`
- Убрать все обертки `asyncio.to_thread()` из handlers и services

## Декомпозиция

1. **Обновление зависимостей**
   - Добавить `asyncpg` в `requirements.txt`
   - `aiosqlite` уже добавлен

2. **Обновление DatabaseInterface**
   - Все методы сделать `async`
   - Обновить сигнатуры методов

3. **Миграция PostgreSQLDatabase**
   - Заменить `psycopg2` на `asyncpg`
   - Переписать все методы на async
   - Обновить context manager для async

4. **Миграция SQLiteDatabase**
   - Заменить `sqlite3` на `aiosqlite`
   - Переписать все методы на async
   - Обновить context manager для async

5. **Обновление вызовов БД**
   - Убрать `asyncio.to_thread()` из всех handlers
   - Убрать `asyncio.to_thread()` из всех services
   - Убрать `asyncio.to_thread()` из `yandex_client_manager.py`
   - Убрать `asyncio.to_thread()` из `utils/context.py`

6. **Тестирование**
   - Проверить работу с SQLite
   - Проверить работу с PostgreSQL
   - Проверить все основные сценарии

## План реализации

### Этап 1: Подготовка
- [x] Создать задачу
- [x] Добавить `asyncpg` в `requirements.txt`

### Этап 2: Обновление интерфейса
- [x] Обновить `DatabaseInterface` - все методы сделать async

### Этап 3: Миграция реализаций
- [x] Переписать `PostgreSQLDatabase` на `asyncpg`
- [x] Переписать `SQLiteDatabase` на `aiosqlite`

### Этап 4: Обновление вызовов
- [x] Обновить `handlers/commands.py`
- [x] Обновить `handlers/callbacks.py`
- [x] Обновить `handlers/messages.py`
- [x] Обновить `services/playlist_service.py`
- [x] Обновить `yandex_client_manager.py`
- [x] Обновить `utils/context.py`
- [x] Обновить `bot.py` для асинхронной инициализации БД

### Этап 5: Тестирование
- [x] Протестировать с SQLite
- [x] Протестировать с PostgreSQL
- [x] Проверить все основные команды

## Чеклист выполнения

- [x] Зависимости обновлены
- [x] `DatabaseInterface` обновлен (все методы async)
- [x] `PostgreSQLDatabase` переписан на `asyncpg`
- [x] `SQLiteDatabase` переписан на `aiosqlite`
- [x] Все вызовы в handlers обновлены
- [x] Все вызовы в services обновлены
- [x] Все вызовы в utils обновлены
- [x] Все вызовы в yandex_client_manager обновлены
- [x] `bot.py` обновлен для асинхронной инициализации БД
- [x] Код протестирован
- [x] Документация обновлена

## Связанные файлы

- `database/base.py` - интерфейс БД
- `database/postgresql_db.py` - реализация PostgreSQL
- `database/sqlite_db.py` - реализация SQLite
- `database/__init__.py` - фабрика создания БД
- `handlers/commands.py` - обработчики команд
- `handlers/callbacks.py` - обработчики callback
- `handlers/messages.py` - обработчики сообщений
- `services/playlist_service.py` - сервис плейлистов
- `yandex_client_manager.py` - менеджер клиентов Яндекс
- `utils/context.py` - менеджер контекста
- `requirements.txt` - зависимости

## Приоритет

**Высокий** - улучшение производительности и упрощение кода

## Статус

✅ Завершено

