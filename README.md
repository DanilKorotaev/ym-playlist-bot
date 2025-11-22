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

> **Примечание**: Плейлисты создаются через бота командой `/create_playlist`. Переменные `PLAYLIST_OWNER_ID`, `PLAYLIST_ID`, `PLAYLIST_KIND` больше не требуются.

### 5. Запуск бота

```bash
python bot.py
```

## Развертывание на хостинге (Linux)

### Подготовка сервера

1. Подключитесь к серверу по SSH
2. Установите Python 3 и pip (если еще не установлены):

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

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
├── database.py               # Работа с SQLite БД
├── yandex_client_manager.py  # Управление клиентами Яндекс.Музыки
├── stats.json                # Файл статистики (создается автоматически)
├── bot.db                    # База данных SQLite (создается автоматически)
├── requirements.txt          # Зависимости Python
├── .env                      # Переменные окружения (не коммитится)
├── .env.example              # Шаблон переменных окружения
├── .gitignore                # Игнорируемые файлы для Git
├── docs/                     # Документация
└── README.md                 # Этот файл
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

