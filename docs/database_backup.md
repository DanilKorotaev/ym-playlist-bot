# Резервное копирование базы данных

## Обзор

Данный документ описывает стратегию и процесс создания резервных копий базы данных PostgreSQL для бота. Регулярные бекапы критически важны для защиты данных от потери.

## Стратегия бекапов

### Рекомендуемая частота

- **Ежедневные бекапы**: Полные дампы БД каждый день
- **Еженедельные бекапы**: Архивные копии на отдельном хранилище
- **Перед важными операциями**: Ручные бекапы перед обновлениями, миграциями, изменениями структуры БД

### Хранение бекапов

1. **Локальное хранилище** (на сервере)
   - Последние 7 дней ежедневных бекапов
   - Последние 4 недельных бекапа

2. **Внешнее хранилище** (рекомендуется)
   - Облачное хранилище (S3, Google Cloud Storage, Yandex Object Storage)
   - Другой сервер
   - Локальный компьютер администратора

3. **Ротация бекапов**
   - Автоматическое удаление старых бекапов
   - Сохранение только необходимого количества копий

## Методы создания бекапов

### Метод 1: pg_dump (рекомендуется)

Создает SQL-дамп базы данных, который можно восстановить на любой версии PostgreSQL.

#### Базовый бекап

```bash
# Создание простого SQL-дампа
docker exec ym_bot_postgres pg_dump -U postgres yandex_music_bot > backup_$(date +%Y%m%d_%H%M%S).sql
```

#### Сжатый бекап

```bash
# Создание сжатого дампа (экономит место)
docker exec ym_bot_postgres pg_dump -U postgres -F c yandex_music_bot > backup_$(date +%Y%m%d_%H%M%S).dump
```

#### Бекап с переменными окружения

```bash
# Использование переменных из .env
source .env
docker exec ym_bot_postgres pg_dump -U ${POSTGRES_USER:-postgres} ${POSTGRES_DB:-yandex_music_bot} > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Метод 2: pg_dumpall (для всех БД)

Если на сервере несколько баз данных PostgreSQL:

```bash
# Бекап всех БД на сервере
docker exec ym_bot_postgres pg_dumpall -U postgres > all_databases_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Метод 3: Физический бекап (для больших БД)

Для очень больших баз данных можно использовать физический бекап через копирование файлов данных:

```bash
# Остановка PostgreSQL
docker-compose stop postgres

# Создание архива volume
docker run --rm -v ym_bot_postgres_data:/data -v $(pwd)/backups:/backup alpine tar czf /backup/physical_backup_$(date +%Y%m%d_%H%M%S).tar.gz /data

# Запуск PostgreSQL
docker-compose start postgres
```

**Внимание**: Физический бекап требует остановки PostgreSQL и может быть несовместим между разными версиями.

## Автоматизация бекапов

### Скрипт для автоматического бекапа

Создан скрипт `scripts/backup_db.sh` для автоматизации процесса создания бекапов.

#### Использование скрипта

```bash
# Базовый бекап
./scripts/backup_db.sh

# Бекап с указанием директории
./scripts/backup_db.sh /path/to/backups

# Бекап с автоматической загрузкой в облако (если настроено)
./scripts/backup_db.sh --upload
```

#### Настройка скрипта

Отредактируйте `scripts/backup_db.sh` для настройки:
- Путь к директории бекапов
- Настройки сжатия
- Интеграция с облачными хранилищами
- Ротация старых бекапов

### Настройка cron для автоматических бекапов

#### Ежедневный бекап в 3:00 ночи

```bash
# Редактируем crontab
crontab -e

# Добавляем строку:
0 3 * * * cd /path/to/Liza_patry_bot && ./scripts/backup_db.sh >> /var/log/db_backup.log 2>&1
```

#### Еженедельный бекап (каждое воскресенье в 2:00)

```bash
0 2 * * 0 cd /path/to/Liza_patry_bot && ./scripts/backup_db.sh --weekly >> /var/log/db_backup.log 2>&1
```

#### Ежедневный бекап с отправкой в облако

```bash
0 3 * * * cd /path/to/Liza_patry_bot && ./scripts/backup_db.sh --upload >> /var/log/db_backup.log 2>&1
```

## Восстановление из бекапа

### Восстановление SQL-дампа

```bash
# Восстановление из SQL-дампа
docker exec -i ym_bot_postgres psql -U postgres yandex_music_bot < backup_YYYYMMDD_HHMMSS.sql

# Или с использованием переменных окружения
source .env
docker exec -i ym_bot_postgres psql -U ${POSTGRES_USER:-postgres} ${POSTGRES_DB:-yandex_music_bot} < backup_YYYYMMDD_HHMMSS.sql
```

### Восстановление сжатого дампа

```bash
# Восстановление из .dump файла
docker exec -i ym_bot_postgres pg_restore -U postgres -d yandex_music_bot --clean --if-exists < backup_YYYYMMDD_HHMMSS.dump
```

### Использование скрипта восстановления

```bash
# Восстановление через скрипт
./scripts/restore_db.sh backup_YYYYMMDD_HHMMSS.sql
```

## Интеграция с облачными хранилищами

### AWS S3

```bash
# Установка AWS CLI (если еще не установлен)
# apt-get install awscli  # для Debian/Ubuntu
# yum install awscli      # для CentOS/RHEL

# Настройка credentials
aws configure

# Загрузка бекапа в S3
aws s3 cp backup_YYYYMMDD_HHMMSS.sql s3://your-bucket/backups/

# Автоматическая загрузка в скрипте бекапа
./scripts/backup_db.sh --upload-s3
```

### Google Cloud Storage

```bash
# Установка gsutil
# pip install gsutil

# Настройка аутентификации
gcloud auth login

# Загрузка бекапа
gsutil cp backup_YYYYMMDD_HHMMSS.sql gs://your-bucket/backups/
```

### Yandex Object Storage

```bash
# Установка yandex-cloud-cli
# curl https://storage.yandexcloud.net/yandexcloud-yc/install.sh | bash

# Настройка
yc config set token YOUR_TOKEN

# Загрузка бекапа
yc storage cp backup_YYYYMMDD_HHMMSS.sql s3://your-bucket/backups/
```

## Мониторинг бекапов

### Проверка успешности бекапов

Рекомендуется добавить проверку успешности создания бекапа:

```bash
#!/bin/bash
# Проверка бекапа
if [ $? -eq 0 ]; then
    echo "Бекап успешно создан: backup_$(date +%Y%m%d_%H%M%S).sql"
    # Отправка уведомления (email, Telegram, и т.д.)
else
    echo "ОШИБКА: Не удалось создать бекап!"
    # Отправка уведомления об ошибке
fi
```

### Уведомления о бекапах

Можно настроить отправку уведомлений:
- Email (через mail или sendmail)
- Telegram (через бота)
- Slack/Discord webhooks
- Системные логи

Пример отправки в Telegram:

```bash
# В скрипте бекапа после успешного создания
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/sendMessage" \
  -d "chat_id=<ADMIN_CHAT_ID>" \
  -d "text=✅ Бекап БД успешно создан: backup_$(date +%Y%m%d_%H%M%S).sql"
```

## Ротация бекапов

### Автоматическое удаление старых бекапов

Добавьте в скрипт бекапа логику ротации:

```bash
# Удаление бекапов старше 7 дней
find /path/to/backups -name "backup_*.sql" -mtime +7 -delete

# Удаление бекапов старше 30 дней (кроме недельных)
find /path/to/backups -name "backup_*.sql" ! -name "backup_*_weekly.sql" -mtime +30 -delete
```

## Проверка целостности бекапов

### Проверка SQL-дампа

```bash
# Проверка синтаксиса SQL-дампа
head -n 100 backup_YYYYMMDD_HHMMSS.sql | grep -i "CREATE TABLE"

# Проверка размера файла (не должен быть пустым)
ls -lh backup_YYYYMMDD_HHMMSS.sql
```

### Тестовое восстановление

Периодически (например, раз в месяц) рекомендуется тестировать восстановление бекапов на тестовой БД:

```bash
# Создание тестовой БД
docker exec ym_bot_postgres createdb -U postgres test_restore

# Восстановление в тестовую БД
docker exec -i ym_bot_postgres psql -U postgres test_restore < backup_YYYYMMDD_HHMMSS.sql

# Проверка данных
docker exec -it ym_bot_postgres psql -U postgres test_restore -c "SELECT COUNT(*) FROM users;"

# Удаление тестовой БД
docker exec ym_bot_postgres dropdb -U postgres test_restore
```

## Рекомендации по безопасности

1. **Шифрование бекапов**
   ```bash
   # Создание зашифрованного бекапа
   docker exec ym_bot_postgres pg_dump -U postgres yandex_music_bot | gpg --encrypt --recipient admin@example.com > backup_$(date +%Y%m%d_%H%M%S).sql.gpg
   ```

2. **Ограничение доступа к бекапам**
   ```bash
   # Установка прав доступа только для владельца
   chmod 600 backup_*.sql
   ```

3. **Не храните пароли в бекапах**
   - Если в БД хранятся чувствительные данные, рассмотрите возможность их исключения из бекапов
   - Используйте отдельные бекапы для чувствительных таблиц

4. **Проверка целостности после восстановления**
   - Всегда проверяйте данные после восстановления
   - Сравнивайте количество записей в таблицах

## Чеклист регулярных задач

### Ежедневно
- [ ] Проверить, что автоматический бекап выполнился успешно
- [ ] Проверить размер последнего бекапа (не должен быть необычно маленьким)

### Еженедельно
- [ ] Проверить наличие недельного бекапа в облачном хранилище
- [ ] Проверить логи бекапов на ошибки

### Ежемесячно
- [ ] Выполнить тестовое восстановление из бекапа
- [ ] Проверить ротацию старых бекапов
- [ ] Обновить документацию при изменении процесса

### Перед важными операциями
- [ ] Создать ручной бекап
- [ ] Сохранить бекап в безопасное место
- [ ] Задокументировать текущее состояние БД

## Дополнительные ресурсы

- [PostgreSQL Documentation: Backup and Restore](https://www.postgresql.org/docs/current/backup.html)
- Документация по миграции: `docs/database_migration.md`
- Скрипты автоматизации: `scripts/backup_db.sh`, `scripts/restore_db.sh`

