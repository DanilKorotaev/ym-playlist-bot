# Liza Party Bot

Telegram бот для управления плейлистом Яндекс.Музыки.

## Возможности

- ✅ Множественные плейлисты (каждый пользователь может создать свой)
- ✅ Шаринг плейлистов через ссылки
- ✅ Разделение на "мои плейлисты" и "плейлисты, куда я добавляю"
- ✅ Управление доступом (создатель может редактировать, участники только добавлять)
- ✅ Добавление треков, альбомов и плейлистов
- ✅ Просмотр списка треков в плейлисте
- ✅ Удаление треков из плейлиста
- ✅ Возможность использовать свой токен Яндекс.Музыки
- ✅ Статистика использования бота

## Установка и настройка

### 1. Клонирование репозитория

```bash
git clone <your-repo-url>
cd Liza_patry_bot
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # На Linux/Mac
# или
venv\Scripts\activate  # На Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Скопируйте файл `.env.example` в `.env`:

```bash
cp .env.example .env
```

Откройте `.env` и заполните необходимые значения:

- `TELEGRAM_TOKEN` - токен Telegram бота (получить у [@BotFather](https://t.me/BotFather))
- `YANDEX_TOKEN` - токен Яндекс.Музыки (инструкция: https://yandex-music.readthedocs.io/en/main/token.html)

**Настройка базы данных:**

Выберите тип БД через переменную `DB_TYPE`:
- `sqlite` (по умолчанию) - для локальной разработки
- `postgresql` - для продакшена

**Для SQLite (по умолчанию):**
- `DB_FILE` - путь к файлу БД (по умолчанию: bot.db)

**Для PostgreSQL:**
- `DB_HOST` - хост PostgreSQL (по умолчанию: localhost)
- `DB_PORT` - порт PostgreSQL (по умолчанию: 5432)
- `DB_NAME` или `POSTGRES_DB` - имя базы данных (по умолчанию: yandex_music_bot)
- `DB_USER` или `POSTGRES_USER` - пользователь PostgreSQL (по умолчанию: postgres)
- `DB_PASSWORD` или `POSTGRES_PASSWORD` - пароль PostgreSQL (обязательно)

**Для Docker Compose (опционально):**
- `POSTGRES_USER` - пользователь PostgreSQL (по умолчанию: postgres)
- `POSTGRES_PASSWORD` - пароль PostgreSQL (по умолчанию: postgres) ⚠️ **Измените в продакшене!**
- `POSTGRES_DB` - имя базы данных (по умолчанию: yandex_music_bot)
- `PGADMIN_DEFAULT_EMAIL` - email для входа в pgAdmin (по умолчанию: admin@admin.com)
- `PGADMIN_DEFAULT_PASSWORD` - пароль для входа в pgAdmin (по умолчанию: admin) ⚠️ **Измените в продакшене!**

> **Примечание**: Плейлисты создаются через бота командой `/create_playlist`. Переменные `PLAYLIST_OWNER_ID`, `PLAYLIST_ID`, `PLAYLIST_KIND` больше не требуются.

### 5. Настройка PostgreSQL

#### Вариант 1: Использование Docker Compose (рекомендуется)

**Установка Docker (если не установлен):**

- **macOS:** Скачайте и установите [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop)
- **Linux:** 
  ```bash
  # Ubuntu/Debian
  sudo apt update
  sudo apt install docker.io docker-compose
  sudo systemctl start docker
  sudo systemctl enable docker
  ```

**Важно:** Перед использованием Docker Compose убедитесь, что Docker Desktop запущен.

**На macOS:**
- Откройте Docker Desktop приложение
- Дождитесь полной загрузки (иконка Docker в строке меню должна быть активна)

**Проверка работы Docker:**
```bash
docker ps
# Если команда выполняется без ошибок, Docker работает
# Если видите ошибку "Cannot connect to the Docker daemon", запустите Docker Desktop
```

**Запуск сервисов:**
```bash
# Запустить PostgreSQL и pgAdmin
# На macOS/Linux с Docker Desktop используйте:
docker compose up -d postgres pgadmin

# Или если установлена старая версия docker-compose:
docker-compose up -d postgres pgadmin
```

PostgreSQL будет доступен на `localhost:5432`, pgAdmin на `http://localhost:5050` (логин: `admin@admin.com`, пароль: `admin`).

**Подключение к базе данных через pgAdmin:**

1. Откройте браузер и перейдите по адресу `http://localhost:5050`

2. Войдите в pgAdmin:
   - **Email:** `admin@admin.com` (или значение из `PGADMIN_DEFAULT_EMAIL` в `.env`)
   - **Password:** `admin` (или значение из `PGADMIN_DEFAULT_PASSWORD` в `.env`)

3. После входа добавьте новый сервер PostgreSQL:
   - Правой кнопкой мыши нажмите на **"Servers"** в левой панели
   - Выберите **"Register" → "Server..."**

4. На вкладке **"General"**:
   - **Name:** `Yandex Music Bot DB` (или любое удобное имя)

5. На вкладке **"Connection"**:
   - **Host name/address:** `postgres` (имя сервиса из docker-compose.yml)
   - **Port:** `5432`
   - **Maintenance database:** `yandex_music_bot` (или значение из `POSTGRES_DB` в `.env`)
   - **Username:** `postgres` (или значение из `POSTGRES_USER` в `.env`)
   - **Password:** `postgres` (или значение из `POSTGRES_PASSWORD` в `.env`)
   - ✅ Отметьте **"Save password"** для удобства

6. Нажмите **"Save"**

7. Теперь вы можете:
   - Просматривать все таблицы: разверните **Servers → Yandex Music Bot DB → Databases → yandex_music_bot → Schemas → public → Tables**
   - Просматривать данные: правой кнопкой мыши на таблицу → **"View/Edit Data" → "All Rows"**
   - Выполнять SQL-запросы: правой кнопкой мыши на базу данных → **"Query Tool"**

**Доступные таблицы:**
- `users` - пользователи Telegram
- `yandex_accounts` - аккаунты Яндекс.Музыки
- `playlists` - плейлисты
- `playlist_access` - доступы к плейлистам
- `actions` - история действий пользователей

**Устранение ошибки `'ServerManager' object has no attribute 'user_info'`:**

Если при подключении к серверу PostgreSQL в pgAdmin вы видите эту ошибку, это означает, что используется несовместимая версия pgAdmin. Проблема исправлена в `docker-compose.yml` (используется pgAdmin версии 8, совместимая с PostgreSQL 15).

Если ошибка всё ещё возникает:

1. Остановите и удалите старые контейнеры:
```bash
docker compose down
docker compose rm -f pgadmin
```

2. Пересоздайте контейнеры с обновлённой конфигурацией:
```bash
docker compose up -d postgres pgadmin
```

3. Подождите несколько секунд, пока pgAdmin полностью запустится, затем обновите страницу в браузере.

**Остановка сервисов:**
```bash
docker compose down
# или
docker-compose down
```

**Просмотр логов:**
```bash
docker compose logs -f postgres
# или
docker-compose logs -f postgres
```

#### Вариант 2: Локальная установка PostgreSQL

Установите PostgreSQL на вашей системе и создайте базу данных:

```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib

# Создать базу данных
sudo -u postgres psql
CREATE DATABASE yandex_music_bot;
CREATE USER postgres WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE yandex_music_bot TO postgres;
\q
```

Обновите переменные окружения в `.env` файле.

### 6. Запуск бота

#### Вариант 1: Обычный запуск

```bash
python bot.py
```

#### Вариант 2: Запуск через Docker Compose

```bash
# Запустить все сервисы (bot + PostgreSQL + pgAdmin)
docker compose up -d
# или если установлена старая версия:
docker-compose up -d

# Просмотр логов
docker compose logs -f bot
# или
docker-compose logs -f bot
```

## Развертывание на хостинге (Linux)

### Подготовка сервера

1. Подключитесь к серверу по SSH
2. Установите Python 3 и pip (если еще не установлены):

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

3. Установите Docker и Docker Compose:

```bash
# Установка Docker
sudo apt install docker.io docker-compose-plugin

# Запуск и автозапуск Docker
sudo systemctl start docker
sudo systemctl enable docker

# Добавьте вашего пользователя в группу docker (чтобы не использовать sudo)
sudo usermod -aG docker $USER
# Выйдите и войдите снова, чтобы изменения вступили в силу
```

**Важно:** На сервере используйте `docker compose` (V2) вместо `docker-compose` (V1). Старая версия `docker-compose` может вызывать ошибки совместимости.

Если у вас установлена старая версия `docker-compose`, удалите её:

```bash
# Удаление старой версии docker-compose
sudo apt remove docker-compose
```

Используйте команду `docker compose` (без дефиса) вместо `docker-compose`.

### Клонирование и настройка

1. Клонируйте репозиторий:

```bash
cd ~
git clone <your-repo-url> liza_bot
cd liza_bot
```

2. Создайте виртуальное окружение и установите зависимости:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. Создайте файл `.env` с вашими токенами:

```bash
nano .env
```

Вставьте содержимое с вашими реальными токенами (как в `.env.example`, но с реальными значениями).

4. Протестируйте запуск:

```bash
source venv/bin/activate
python bot.py
```

Если все работает, остановите бота (Ctrl+C).

### Использование Docker Compose на сервере

Если вы хотите использовать Docker Compose для запуска PostgreSQL и pgAdmin на сервере:

1. Создайте файл `.env` с переменными окружения (если еще не создан):

```bash
nano .env
```

Добавьте необходимые переменные (см. раздел "Настройка переменных окружения" выше).

2. Запустите PostgreSQL и pgAdmin:

```bash
# Используйте docker compose (V2) вместо docker-compose
docker compose up -d postgres pgadmin
```

3. Проверьте статус контейнеров:

```bash
docker compose ps
```

4. Просмотр логов:

```bash
docker compose logs -f postgres
```

5. Остановка сервисов:

```bash
docker compose down
```

**Примечание:** Если вы получаете ошибку `Not supported URL scheme http+docker`, это означает, что используется старая версия `docker-compose`. Удалите её и используйте `docker compose` (V2):

```bash
sudo apt remove docker-compose
docker compose up -d postgres pgadmin
```

### Настройка firewall для доступа к портам

На сервере обычно включен firewall (ufw), который блокирует входящие соединения. Чтобы pgAdmin был доступен снаружи, нужно открыть порт 5050.

**⚠️ ВАЖНО: Безопасность**

- **НЕ открывайте порт 5432 (PostgreSQL) наружу** — это небезопасно! База данных должна быть доступна только внутри сервера или через VPN.
- Откройте порт 5050 (pgAdmin) только если вам действительно нужен внешний доступ к веб-интерфейсу.
- Если pgAdmin нужен только для локальной работы, используйте SSH туннель (см. ниже).

#### Вариант 1: Открыть порт pgAdmin (5050) для внешнего доступа

```bash
# Проверьте статус firewall
sudo ufw status

# Откройте порт 5050 для pgAdmin
sudo ufw allow 5050/tcp

# Если firewall не активен, активируйте его
sudo ufw enable
```

После этого pgAdmin будет доступен по адресу `http://ваш_сервер_ip:5050`

**⚠️ Обязательно измените пароль по умолчанию в `.env` файле!**

**Подключение к базе данных через pgAdmin на сервере:**

1. Откройте браузер и перейдите по адресу `http://ваш_сервер_ip:5050` (или `http://localhost:5050` если используете SSH туннель)

2. Войдите в pgAdmin:
   - **Email:** значение из `PGADMIN_DEFAULT_EMAIL` в `.env` (по умолчанию: `admin@admin.com`)
   - **Password:** значение из `PGADMIN_DEFAULT_PASSWORD` в `.env` (по умолчанию: `admin`)

3. После входа добавьте новый сервер PostgreSQL:
   - Правой кнопкой мыши нажмите на **"Servers"** в левой панели
   - Выберите **"Register" → "Server..."**

4. На вкладке **"General"**:
   - **Name:** `Yandex Music Bot DB` (или любое удобное имя)

5. На вкладке **"Connection"**:
   - **Host name/address:** `postgres` (имя сервиса из docker-compose.yml)
   - **Port:** `5432`
   - **Maintenance database:** значение из `POSTGRES_DB` в `.env` (по умолчанию: `yandex_music_bot`)
   - **Username:** значение из `POSTGRES_USER` в `.env` (по умолчанию: `postgres`)
   - **Password:** значение из `POSTGRES_PASSWORD` в `.env` (по умолчанию: `postgres`)
   - ✅ Отметьте **"Save password"** для удобства

6. Нажмите **"Save"**

7. Теперь вы можете просматривать все таблицы и данные базы данных (см. инструкции выше в разделе "Подключение к базе данных через pgAdmin")

#### Вариант 2: Использовать SSH туннель (рекомендуется для безопасности)

Вместо открытия порта наружу, используйте SSH туннель с вашего локального компьютера:

```bash
# На вашем локальном компьютере выполните:
ssh -L 5050:localhost:5050 user@your_server_ip
```

После этого pgAdmin будет доступен на вашем локальном компьютере по адресу `http://localhost:5050`, но соединение будет зашифровано через SSH.

**Примечание о PostgreSQL:** Порт 5432 (PostgreSQL) не нужно открывать в firewall — база данных должна быть доступна только внутри сервера. Если вам нужно подключиться к PostgreSQL с вашего компьютера, используйте SSH туннель:

```bash
# На вашем локальном компьютере:
ssh -L 5432:localhost:5432 user@your_server_ip
```

### Настройка systemd для автозапуска

Создайте файл сервиса:

```bash
sudo nano /etc/systemd/system/liza-bot.service
```

Вставьте следующее содержимое (замените `/home/your_user` на ваш путь):

```ini
[Unit]
Description=Liza Party Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/your_user/liza_bot
Environment="PATH=/home/your_user/liza_bot/venv/bin"
ExecStart=/home/your_user/liza_bot/venv/bin/python /home/your_user/liza_bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Замените `your_user` на ваше имя пользователя.

Активируйте и запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable liza-bot.service
sudo systemctl start liza-bot.service
```

Проверьте статус:

```bash
sudo systemctl status liza-bot.service
```

Просмотр логов:

```bash
sudo journalctl -u liza-bot.service -f
```

### Обновление бота

Для обновления кода на сервере:

```bash
cd ~/liza_bot
git pull
source venv/bin/activate
pip install -r requirements.txt  # если были добавлены новые зависимости
sudo systemctl restart liza-bot.service
```

## Структура проекта

```
ym-playlist-bot/
├── bot.py                    # Основной файл бота
├── database/                  # Модуль работы с БД
│   ├── __init__.py           # Фабрика для создания БД
│   ├── base.py               # Абстрактный интерфейс DatabaseInterface
│   ├── sqlite_db.py          # Реализация для SQLite
│   └── postgresql_db.py      # Реализация для PostgreSQL
├── yandex_client_manager.py   # Управление клиентами Яндекс.Музыки
├── stats.json                 # Файл статистики (создается автоматически)
├── bot.db                     # База данных SQLite (создается автоматически)
├── docker-compose.yml         # Docker Compose конфигурация (PostgreSQL + pgAdmin + Bot)
├── Dockerfile                 # Docker образ для бота
├── requirements.txt           # Зависимости Python
├── .env                       # Переменные окружения (не коммитится)
├── .env.example               # Шаблон переменных окружения
├── .gitignore                 # Игнорируемые файлы для Git
├── docs/                      # Документация
└── README.md                  # Этот файл
```

## Безопасность

⚠️ **ВАЖНО**: Никогда не коммитьте файл `.env` в репозиторий! Он содержит секретные токены.

Файл `.env` уже добавлен в `.gitignore`, но убедитесь, что он не попал в репозиторий случайно.

## Команды бота

### Основные команды
- `/start` - помощь и список команд
- `/create_playlist <название>` - создать новый плейлист
- `/my_playlists` - показать плейлисты, которые вы создали
- `/shared_playlists` - показать плейлисты, куда вы добавляете
- `/list [номер]` - показать список треков в плейлисте
- `/playlist_info [номер]` - информация о плейлисте
- `/queen_liza <номер>` - удалить трек из плейлиста

### Управление плейлистами
- `/set_token <токен>` - установить свой токен Яндекс.Музыки
- `/edit_name <новое название>` - изменить название плейлиста (только для создателя)
- `/delete_playlist` - удалить плейлист из БД (только для создателя)

### Добавление треков
Просто отправьте ссылку на трек, альбом или плейлист, чтобы добавить их в активный плейлист.

### Шаринг плейлистов
После создания плейлиста бот отправит вам ссылку для шаринга. Отправьте её друзьям, чтобы они могли добавлять треки в ваш плейлист.

## Разработка

Для разработки рекомендуется:

1. Использовать отдельный тестовый бот и тестовый плейлист
2. Создать отдельную ветку для разработки
3. Тестировать изменения локально перед деплоем

## Лицензия

Приватный проект.

