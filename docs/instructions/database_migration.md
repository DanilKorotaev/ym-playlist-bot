# Миграция базы данных между серверами

## Обзор

Данный документ описывает процесс миграции базы данных PostgreSQL с одного сервера на другой. Процесс применим для случаев, когда бот развернут через Docker на Linux-хостинге.

## Предварительные требования

1. **Доступ к исходному серверу** (старый сервер)
   - SSH доступ
   - Права на выполнение Docker команд
   - Доступ к PostgreSQL контейнеру

2. **Доступ к целевому серверу** (новый сервер)
   - SSH доступ
   - Установленный Docker и Docker Compose
   - Достаточно места на диске для размещения дампа БД

3. **Сетевое соединение** между серверами
   - Возможность передачи файлов (SCP, SFTP, rsync)
   - Или возможность прямого подключения к БД (если серверы в одной сети)

## Методы миграции

### Метод 1: Миграция через дамп (рекомендуется)

Этот метод наиболее безопасен и универсален. Подходит для миграции между любыми серверами, даже если они не находятся в одной сети.

#### Шаг 1: Создание дампа на исходном сервере

```bash
# Подключаемся к исходному серверу
ssh user@old-server.com

# Переходим в директорию проекта
cd /path/to/Liza_patry_bot

# Создаем дамп базы данных
docker exec ym_bot_postgres pg_dump -U postgres yandex_music_bot > backup_$(date +%Y%m%d_%H%M%S).sql

# Или с использованием переменных окружения
docker exec ym_bot_postgres pg_dump -U ${POSTGRES_USER:-postgres} ${POSTGRES_DB:-yandex_music_bot} > backup_$(date +%Y%m%d_%H%M%S).sql
```

**Альтернатива**: Использовать скрипт `scripts/backup_db.sh` (см. документацию по бекапам)

#### Шаг 2: Передача дампа на новый сервер

```bash
# С исходного сервера копируем файл на новый сервер
scp backup_YYYYMMDD_HHMMSS.sql user@new-server.com:/path/to/Liza_patry_bot/

# Или используем rsync для больших файлов
rsync -avz --progress backup_YYYYMMDD_HHMMSS.sql user@new-server.com:/path/to/Liza_patry_bot/
```

#### Шаг 3: Подготовка нового сервера

```bash
# Подключаемся к новому серверу
ssh user@new-server.com

# Клонируем репозиторий (если еще не склонирован)
git clone <repository-url> Liza_patry_bot
cd Liza_patry_bot

# Копируем .env файл (или создаем новый с правильными настройками)
cp .env.example .env
# Редактируем .env файл с настройками для нового сервера
nano .env
```

#### Шаг 4: Запуск PostgreSQL на новом сервере

```bash
# Запускаем только PostgreSQL (без бота)
docker compose up -d postgres

# Ждем, пока PostgreSQL будет готов
docker compose exec postgres pg_isready -U postgres
```

#### Шаг 5: Восстановление дампа

```bash
# Восстанавливаем дамп в новую БД
docker exec -i ym_bot_postgres psql -U postgres yandex_music_bot < backup_YYYYMMDD_HHMMSS.sql

# Или с использованием переменных окружения
docker exec -i ym_bot_postgres psql -U ${POSTGRES_USER:-postgres} ${POSTGRES_DB:-yandex_music_bot} < backup_YYYYMMDD_HHMMSS.sql
```

**Альтернатива**: Использовать скрипт `scripts/restore_db.sh` (см. документацию по бекапам)

#### Шаг 6: Проверка данных

```bash
# Подключаемся к БД и проверяем количество записей
docker exec -it ym_bot_postgres psql -U postgres yandex_music_bot

# В psql выполняем:
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM playlists;
SELECT COUNT(*) FROM yandex_accounts;
SELECT COUNT(*) FROM playlist_access;
SELECT COUNT(*) FROM actions;
SELECT COUNT(*) FROM user_subscriptions;
SELECT COUNT(*) FROM payments;

# Сравниваем с исходным сервером
\q
```

#### Шаг 7: Запуск бота на новом сервере

```bash
# Запускаем все сервисы
docker compose up -d

# Проверяем логи бота
docker compose logs -f bot
```

### Метод 2: Прямая миграция через pg_dump/pg_restore (для серверов в одной сети)

Если серверы находятся в одной сети и есть прямое соединение между ними, можно выполнить миграцию напрямую без промежуточного файла.

#### Шаг 1: Создание дампа на исходном сервере

```bash
# На исходном сервере создаем дамп
docker exec ym_bot_postgres pg_dump -U postgres -F c yandex_music_bot > backup_$(date +%Y%m%d_%H%M%S).dump
```

#### Шаг 2: Прямое восстановление на новом сервере

```bash
# На новом сервере (после запуска PostgreSQL)
# Передаем дамп и восстанавливаем в одной команде
ssh user@old-server.com "docker exec ym_bot_postgres pg_dump -U postgres -F c yandex_music_bot" | \
docker exec -i ym_bot_postgres pg_restore -U postgres -d yandex_music_bot --clean --if-exists
```

**Внимание**: Этот метод требует, чтобы на новом сервере уже была создана пустая БД с правильной структурой.

### Метод 3: Использование Docker volumes (только для локальных миграций)

Если миграция происходит между серверами с общим хранилищем или при переносе на другой хост с доступом к volumes.

#### Шаг 1: Экспорт volume на исходном сервере

```bash
# Останавливаем PostgreSQL
docker compose stop postgres

# Создаем архив volume
docker run --rm -v ym_bot_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_data_backup.tar.gz /data
```

#### Шаг 2: Импорт volume на новом сервере

```bash
# Копируем архив на новый сервер
scp postgres_data_backup.tar.gz user@new-server.com:/path/to/Liza_patry_bot/

# На новом сервере создаем volume и распаковываем
docker volume create ym_bot_postgres_data
docker run --rm -v ym_bot_postgres_data:/data -v $(pwd):/backup alpine tar xzf /backup/postgres_data_backup.tar.gz -C /
```

**Внимание**: Этот метод требует точного совпадения версий PostgreSQL и может быть проблематичен при разных версиях.

## Автоматизация миграции

Для упрощения процесса миграции создан скрипт `scripts/migrate_db.sh`, который автоматизирует основные шаги.

### Использование скрипта миграции

```bash
# На исходном сервере: создание дампа для миграции
./scripts/migrate_db.sh export

# На новом сервере: восстановление из дампа
./scripts/migrate_db.sh import backup_YYYYMMDD_HHMMSS.sql
```

Подробнее см. комментарии в самом скрипте.

## Важные замечания

### Перед миграцией

1. **Создайте резервную копию** на исходном сервере (на всякий случай)
2. **Проверьте версии PostgreSQL** - рекомендуется использовать одинаковые версии на обоих серверах
3. **Проверьте размер БД** - убедитесь, что на новом сервере достаточно места
4. **Остановите бота** на исходном сервере перед созданием дампа (опционально, но рекомендуется для консистентности)

### Во время миграции

1. **Не запускайте бота** на обоих серверах одновременно (может привести к конфликтам данных)
2. **Проверьте переменные окружения** - убедитесь, что настройки БД на новом сервере корректны
3. **Проверьте сетевые настройки** - убедитесь, что бот может подключиться к PostgreSQL

### После миграции

1. **Проверьте целостность данных** - сравните количество записей в таблицах
2. **Протестируйте функциональность** - проверьте основные команды бота
3. **Обновите DNS/настройки** - если используется доменное имя, обновите записи
4. **Мониторинг** - следите за логами бота в первые часы после миграции

## Откат миграции

Если что-то пошло не так, можно откатить миграцию:

1. **Остановите бота** на новом сервере
2. **Восстановите работу** на исходном сервере (если он еще доступен)
3. **Проверьте логи** для выявления проблем
4. **Исправьте проблемы** и повторите миграцию

## Миграция с SQLite на PostgreSQL

Если исходная БД - SQLite, процесс немного отличается:

1. **Экспорт из SQLite**:
   ```bash
   sqlite3 bot.db .dump > sqlite_backup.sql
   ```

2. **Конвертация дампа** (требует ручной правки или специальных инструментов):
   - SQLite и PostgreSQL имеют разные типы данных и синтаксис
   - Рекомендуется использовать инструменты типа `pgloader` или вручную адаптировать дамп

3. **Импорт в PostgreSQL** (после конвертации):
   ```bash
   docker exec -i ym_bot_postgres psql -U postgres yandex_music_bot < converted_backup.sql
   ```

## Часто задаваемые вопросы

### Можно ли мигрировать без остановки бота?

Технически можно, но не рекомендуется. При активной работе бота во время создания дампа возможна потеря данных или несогласованность. Рекомендуется остановить бота на время создания дампа.

### Как долго занимает миграция?

Время зависит от размера БД и скорости сети:
- Маленькая БД (< 100 MB): 5-15 минут
- Средняя БД (100 MB - 1 GB): 15-60 минут
- Большая БД (> 1 GB): 1+ час

### Что делать, если миграция прервалась?

1. Проверьте логи ошибок
2. Убедитесь, что на новом сервере достаточно места
3. Проверьте права доступа к файлам
4. Попробуйте восстановить дамп заново (PostgreSQL автоматически очистит частично восстановленные данные)

### Можно ли мигрировать только часть данных?

Да, можно создать дамп только определенных таблиц:
```bash
docker exec ym_bot_postgres pg_dump -U postgres -t users -t playlists yandex_music_bot > partial_backup.sql
```

Однако это может нарушить целостность данных из-за внешних ключей.

## Дополнительные ресурсы

- [PostgreSQL Documentation: Backup and Restore](https://www.postgresql.org/docs/current/backup.html)
- [Docker Documentation: Volumes](https://docs.docker.com/storage/volumes/)
- Документация по бекапам: `docs/instructions/database_backup.md`

