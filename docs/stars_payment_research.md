# Исследование: Интеграция оплаты расширенных лимитов через Telegram Stars

## Дата исследования
2024

## Цель
Исследовать возможности интеграции оплаты расширенных лимитов плейлистов через Telegram Stars в боте для Яндекс.Музыки.

---

## 1. Что такое Telegram Stars?

**Telegram Stars** — это внутренняя валюта Telegram, которая позволяет пользователям:
- Покупать подписки и услуги в ботах
- Поддерживать разработчиков
- Оплачивать премиум-функции

### Ключевые особенности:
- ⭐ Stars можно купить в Telegram (через приложение)
- 💰 Разработчики могут выводить Stars в реальные деньги
- 🔄 Stars работают как единая валюта для всех ботов в Telegram
- 📱 Интеграция на уровне Bot API (не требует внешних платежных систем)

---

## 2. Telegram Bot API для работы с Stars

### Основные методы Bot API:

#### 2.1. `createInvoiceLink`
Создает ссылку на инвойс для оплаты через Stars.

**Параметры:**
- `title` — название товара/услуги
- `description` — описание
- `payload` — уникальный идентификатор платежа (до 128 байт)
- `provider_token` — не требуется для Stars (можно передать пустую строку)
- `currency` — валюта: `"XTR"` (Telegram Stars)
- `prices` — массив цен в Stars
- `max_tip_amount` — максимальная сумма чаевых (опционально)
- `suggested_tip_amounts` — предложенные суммы чаевых (опционально)
- `provider_data` — дополнительные данные (JSON строка, опционально)
- `photo_url` — URL изображения товара (опционально)
- `photo_size` — размер изображения (опционально)
- `photo_width` — ширина изображения (опционально)
- `photo_height` — высота изображения (опционально)
- `need_name` — требуется ли имя (опционально)
- `need_phone_number` — требуется ли телефон (опционально)
- `need_email` — требуется ли email (опционально)
- `need_shipping_address` — требуется ли адрес доставки (опционально)
- `send_phone_number_to_provider` — отправлять ли телефон провайдеру (опционально)
- `send_email_to_provider` — отправлять ли email провайдеру (опционально)
- `is_flexible` — гибкая цена (опционально)

**Возвращает:**
- `invoice_link` — ссылка на инвойс

#### 2.2. `sendInvoice`
Отправляет инвойс пользователю напрямую в чате.

**Параметры:** (аналогичны `createInvoiceLink`)

**Возвращает:**
- `Message` — сообщение с инвойсом

#### 2.3. `answerPreCheckoutQuery`
Подтверждает или отклоняет предварительный запрос на оплату.

**Параметры:**
- `pre_checkout_query_id` — ID запроса
- `ok` — успешно ли прошла проверка
- `error_message` — сообщение об ошибке (если `ok=False`)

#### 2.4. `answerShippingQuery`
Обрабатывает запрос на доставку (для физических товаров, обычно не требуется для Stars).

---

## 3. Обработка платежей в боте

### 3.1. Типы обновлений (Updates)

Telegram Bot API отправляет следующие типы обновлений для платежей:

1. **`pre_checkout_query`** — пользователь подтвердил оплату, нужно проверить и подтвердить
2. **`successful_payment`** — платеж успешно завершен

### 3.2. Процесс оплаты:

```
1. Бот создает инвойс (createInvoiceLink или sendInvoice)
   ↓
2. Пользователь нажимает на кнопку оплаты
   ↓
3. Telegram показывает диалог оплаты
   ↓
4. Пользователь подтверждает оплату
   ↓
5. Бот получает pre_checkout_query
   ↓
6. Бот проверяет платеж и вызывает answerPreCheckoutQuery(ok=True)
   ↓
7. Telegram обрабатывает платеж
   ↓
8. Бот получает successful_payment
   ↓
9. Бот активирует услугу (увеличивает лимит плейлистов)
```

---

## 4. Интеграция в текущий проект

### 4.1. Текущая реализация лимитов

**Файлы:**
- `handlers/commands.py` — проверка лимита при создании плейлиста
- `database/base.py` — интерфейс БД
- `database/sqlite_db.py` / `database/postgresql_db.py` — реализация БД

**Текущая логика:**
```python
PLAYLIST_LIMIT = int(os.getenv("PLAYLIST_LIMIT", 2))  # Базовый лимит: 2

# Проверка при создании плейлиста
current_count = self.db.count_user_playlists(telegram_id)
if current_count >= PLAYLIST_LIMIT:
    # Отказать в создании
```

### 4.2. Необходимые изменения

#### 4.2.1. Структура базы данных

**Новая таблица: `user_subscriptions`**

```sql
CREATE TABLE user_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    subscription_type TEXT NOT NULL,  -- 'playlist_limit_5', 'playlist_limit_10', 'unlimited'
    stars_amount INTEGER NOT NULL,    -- Сколько Stars было заплачено
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,             -- NULL для бессрочных подписок
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

CREATE INDEX idx_user_subscriptions_telegram_id ON user_subscriptions(telegram_id);
CREATE INDEX idx_user_subscriptions_active ON user_subscriptions(telegram_id, is_active);
```

**Альтернативный вариант: `user_limits`**

```sql
CREATE TABLE user_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    limit_type TEXT NOT NULL,         -- 'playlist_limit'
    limit_value INTEGER NOT NULL,     -- Значение лимита (5, 10, -1 для unlimited)
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,             -- NULL для бессрочных
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);
```

**Таблица для истории платежей: `payments`**

```sql
CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    invoice_payload TEXT NOT NULL,    -- Уникальный идентификатор платежа
    stars_amount INTEGER NOT NULL,
    subscription_type TEXT NOT NULL,
    status TEXT NOT NULL,             -- 'pending', 'completed', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

CREATE INDEX idx_payments_telegram_id ON payments(telegram_id);
CREATE INDEX idx_payments_payload ON payments(invoice_payload);
```

#### 4.2.2. Обновление DatabaseInterface

**Новые методы в `database/base.py`:**

```python
# Работа с подписками/лимитами
@abstractmethod
def get_user_playlist_limit(self, telegram_id: int) -> int:
    """Получить текущий лимит плейлистов для пользователя.
    
    Возвращает:
        - Базовый лимит (PLAYLIST_LIMIT), если нет активной подписки
        - Лимит из активной подписки, если есть
        - -1 для unlimited
    """
    pass

@abstractmethod
def create_subscription(self, telegram_id: int, subscription_type: str, 
                       stars_amount: int, expires_at: Optional[datetime] = None) -> int:
    """Создать подписку для пользователя."""
    pass

@abstractmethod
def get_active_subscription(self, telegram_id: int) -> Optional[Dict]:
    """Получить активную подписку пользователя."""
    pass

# Работа с платежами
@abstractmethod
def create_payment(self, telegram_id: int, invoice_payload: str, 
                  stars_amount: int, subscription_type: str) -> int:
    """Создать запись о платеже."""
    pass

@abstractmethod
def update_payment_status(self, invoice_payload: str, status: str):
    """Обновить статус платежа."""
    pass

@abstractmethod
def get_payment_by_payload(self, invoice_payload: str) -> Optional[Dict]:
    """Получить платеж по payload."""
    pass
```

#### 4.2.3. Новый сервис: `PaymentService`

**Файл: `services/payment_service.py`**

```python
"""
Сервис для работы с платежами через Telegram Stars.
"""
import logging
import uuid
from typing import Optional, Dict
from datetime import datetime, timedelta

from database import DatabaseInterface

logger = logging.getLogger(__name__)

# Тарифы
SUBSCRIPTION_PLANS = {
    'playlist_limit_5': {
        'stars': 100,  # Примерная цена
        'limit': 5,
        'name': '5 плейлистов',
        'duration_days': None  # Бессрочно
    },
    'playlist_limit_10': {
        'stars': 200,
        'limit': 10,
        'name': '10 плейлистов',
        'duration_days': None
    },
    'playlist_limit_unlimited': {
        'stars': 500,
        'limit': -1,  # -1 означает unlimited
        'name': 'Безлимитные плейлисты',
        'duration_days': None
    }
}

class PaymentService:
    """Сервис для работы с платежами."""
    
    def __init__(self, db: DatabaseInterface):
        self.db = db
    
    def get_available_plans(self) -> Dict[str, Dict]:
        """Получить доступные тарифные планы."""
        return SUBSCRIPTION_PLANS
    
    def generate_invoice_payload(self, telegram_id: int, subscription_type: str) -> str:
        """Генерировать уникальный payload для инвойса."""
        # Формат: telegram_id:subscription_type:uuid
        unique_id = str(uuid.uuid4())
        return f"{telegram_id}:{subscription_type}:{unique_id}"
    
    def parse_invoice_payload(self, payload: str) -> Optional[Dict]:
        """Распарсить payload инвойса."""
        try:
            parts = payload.split(':')
            if len(parts) != 3:
                return None
            return {
                'telegram_id': int(parts[0]),
                'subscription_type': parts[1],
                'unique_id': parts[2]
            }
        except (ValueError, IndexError):
            return None
    
    def create_payment(self, telegram_id: int, subscription_type: str) -> Optional[Dict]:
        """Создать платеж и вернуть данные для инвойса."""
        if subscription_type not in SUBSCRIPTION_PLANS:
            return None
        
        plan = SUBSCRIPTION_PLANS[subscription_type]
        payload = self.generate_invoice_payload(telegram_id, subscription_type)
        
        # Создаем запись о платеже
        payment_id = self.db.create_payment(
            telegram_id=telegram_id,
            invoice_payload=payload,
            stars_amount=plan['stars'],
            subscription_type=subscription_type
        )
        
        return {
            'payment_id': payment_id,
            'payload': payload,
            'stars_amount': plan['stars'],
            'subscription_type': subscription_type,
            'plan_name': plan['name']
        }
    
    def process_successful_payment(self, telegram_id: int, invoice_payload: str, 
                                   stars_amount: int) -> bool:
        """Обработать успешный платеж."""
        # Обновляем статус платежа
        self.db.update_payment_status(invoice_payload, 'completed')
        
        # Парсим payload
        payload_data = self.parse_invoice_payload(invoice_payload)
        if not payload_data:
            logger.error(f"Не удалось распарсить payload: {invoice_payload}")
            return False
        
        subscription_type = payload_data['subscription_type']
        
        # Получаем план
        if subscription_type not in SUBSCRIPTION_PLANS:
            logger.error(f"Неизвестный тип подписки: {subscription_type}")
            return False
        
        plan = SUBSCRIPTION_PLANS[subscription_type]
        
        # Создаем подписку
        expires_at = None
        if plan.get('duration_days'):
            expires_at = datetime.now() + timedelta(days=plan['duration_days'])
        
        self.db.create_subscription(
            telegram_id=telegram_id,
            subscription_type=subscription_type,
            stars_amount=stars_amount,
            expires_at=expires_at
        )
        
        logger.info(f"Подписка активирована для пользователя {telegram_id}: {subscription_type}")
        return True
```

#### 4.2.4. Обновление логики проверки лимитов

**В `handlers/commands.py`:**

```python
def create_playlist_name(self, update: Update, context: CallbackContext) -> int:
    # ...
    telegram_id = update.effective_user.id
    
    # Получаем текущий лимит пользователя (с учетом подписки)
    user_limit = self.db.get_user_playlist_limit(telegram_id)
    current_count = self.db.count_user_playlists(telegram_id)
    
    # Проверка лимита
    if user_limit == -1:
        # Unlimited
        pass
    elif current_count >= user_limit:
        # Показываем предложение купить расширенный лимит
        update.effective_message.reply_text(
            f"❌ Достигнут лимит плейлистов!\n\n"
            f"📊 У вас уже создано {current_count} из {user_limit} плейлистов.\n\n"
            f"💡 Хотите увеличить лимит? Используйте /buy_limit",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    # Создаем плейлист...
```

#### 4.2.5. Новые обработчики для платежей

**В `handlers/commands.py`:**

```python
def buy_limit(self, update: Update, context: CallbackContext):
    """Команда для покупки расширенного лимита."""
    telegram_id = update.effective_user.id
    self.db.ensure_user(telegram_id, update.effective_user.username)
    
    # Получаем доступные планы
    payment_service = PaymentService(self.db)
    plans = payment_service.get_available_plans()
    
    # Формируем клавиатуру с тарифами
    keyboard = []
    for plan_id, plan_data in plans.items():
        button_text = f"⭐ {plan_data['name']} — {plan_data['stars']} Stars"
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"buy_{plan_id}"
        )])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.effective_message.reply_text(
        "💳 Выберите тарифный план:\n\n"
        "⭐ Stars — это внутренняя валюта Telegram\n"
        "Вы можете купить Stars прямо в приложении Telegram",
        reply_markup=reply_markup
    )

def handle_pre_checkout_query(self, update: Update, context: CallbackContext):
    """Обработка pre_checkout_query."""
    query = update.pre_checkout_query
    telegram_id = query.from_user.id
    
    # Проверяем платеж
    payment_service = PaymentService(self.db)
    payment = self.db.get_payment_by_payload(query.invoice_payload)
    
    if not payment or payment['status'] != 'pending':
        # Отклоняем платеж
        context.bot.answer_pre_checkout_query(
            pre_checkout_query_id=query.id,
            ok=False,
            error_message="Платеж не найден или уже обработан"
        )
        return
    
    # Подтверждаем платеж
    context.bot.answer_pre_checkout_query(
        pre_checkout_query_id=query.id,
        ok=True
    )

def handle_successful_payment(self, update: Update, context: CallbackContext):
    """Обработка успешного платежа."""
    payment = update.message.successful_payment
    telegram_id = update.effective_user.id
    
    payment_service = PaymentService(self.db)
    success = payment_service.process_successful_payment(
        telegram_id=telegram_id,
        invoice_payload=payment.invoice_payload,
        stars_amount=payment.total_amount
    )
    
    if success:
        # Получаем информацию о новой подписке
        subscription = self.db.get_active_subscription(telegram_id)
        if subscription:
            plan = payment_service.get_available_plans()[subscription['subscription_type']]
            limit = plan['limit']
            limit_text = "безлимитно" if limit == -1 else f"{limit} плейлистов"
            
            update.message.reply_text(
                f"✅ Платеж успешно обработан!\n\n"
                f"🎉 Ваш лимит увеличен до {limit_text}\n\n"
                f"Теперь вы можете создавать больше плейлистов!",
                reply_markup=get_main_menu_keyboard()
            )
    else:
        update.message.reply_text(
            "❌ Произошла ошибка при обработке платежа.\n"
            "Пожалуйста, свяжитесь с поддержкой.",
            reply_markup=get_main_menu_keyboard()
        )
```

**В `handlers/callbacks.py`:**

```python
def handle_buy_subscription(self, update: Update, context: CallbackContext, plan_id: str):
    """Обработка нажатия на кнопку покупки подписки."""
    telegram_id = update.effective_user.id
    
    payment_service = PaymentService(self.db)
    payment_data = payment_service.create_payment(telegram_id, plan_id)
    
    if not payment_data:
        update.callback_query.answer("Ошибка при создании платежа", show_alert=True)
        return
    
    plan = payment_service.get_available_plans()[plan_id]
    
    # Создаем инвойс
    try:
        invoice_link = context.bot.create_invoice_link(
            title=f"Расширенный лимит: {plan['name']}",
            description=f"Увеличьте лимит плейлистов до {plan['name']}",
            payload=payment_data['payload'],
            provider_token="",  # Не требуется для Stars
            currency="XTR",  # Telegram Stars
            prices=[LabeledPrice(label=plan['name'], amount=plan['stars'])]
        )
        
        # Отправляем сообщение с кнопкой оплаты
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("💳 Оплатить", url=invoice_link)
        ]])
        
        update.callback_query.message.reply_text(
            f"💳 Оплата: {plan['name']}\n\n"
            f"💰 Стоимость: {plan['stars']} Stars\n\n"
            f"Нажмите кнопку ниже для оплаты:",
            reply_markup=keyboard
        )
        
        update.callback_query.answer()
    except Exception as e:
        logger.error(f"Ошибка при создании инвойса: {e}")
        update.callback_query.answer("Ошибка при создании платежа", show_alert=True)
```

#### 4.2.6. Регистрация обработчиков в `bot.py`

```python
# Обработчики платежей
dp.add_handler(PreCheckoutQueryHandler(command_handlers.handle_pre_checkout_query))
dp.add_handler(MessageHandler(Filters.successful_payment, command_handlers.handle_successful_payment))

# Команда покупки лимита
dp.add_handler(CommandHandler("buy_limit", command_handlers.buy_limit))
```

---

## 5. Система тарифов

### 5.1. Предлагаемые тарифы:

| Тариф | Лимит плейлистов | Цена (Stars) | Описание |
|-------|------------------|--------------|----------|
| Базовый | 2 | 0 (бесплатно) | По умолчанию для всех пользователей |
| Расширенный | 5 | 100 | Для активных пользователей |
| Премиум | 10 | 200 | Для продвинутых пользователей |
| Безлимит | ∞ | 500 | Для максимальной гибкости |

### 5.2. Альтернативные варианты:

**Вариант 1: Подписка на месяц**
- 5 плейлистов — 50 Stars/месяц
- 10 плейлистов — 100 Stars/месяц
- Безлимит — 200 Stars/месяц

**Вариант 2: Разовая покупка (бессрочно)**
- 5 плейлистов — 100 Stars (разово)
- 10 плейлистов — 200 Stars (разово)
- Безлимит — 500 Stars (разово)

**Рекомендация:** Начать с разовой покупки (бессрочно), так как это проще в реализации и понятнее для пользователей.

---

## 6. Вывод Stars разработчиками

### 6.1. Как выводить Stars:

1. **Через Telegram Bot API:**
   - Telegram автоматически начисляет Stars на баланс бота
   - Вывод через официальный канал Telegram (требуется верификация)

2. **Требования:**
   - Бот должен быть верифицирован
   - Минимальная сумма для вывода (уточнить в документации Telegram)
   - Комиссия Telegram (обычно 5-10%)

3. **Процесс:**
   - Stars накапливаются на балансе бота
   - Разработчик запрашивает вывод через официальный интерфейс
   - Деньги переводятся на указанный счет

### 6.2. Ограничения:

- ⚠️ Вывод возможен только в определенных странах (список уточнить)
- ⚠️ Требуется верификация личности разработчика
- ⚠️ Минимальная сумма для вывода
- ⚠️ Комиссия Telegram

---

## 7. Безопасность

### 7.1. Важные моменты:

1. **Проверка payload:**
   - Всегда проверяйте `invoice_payload` при получении `pre_checkout_query`
   - Убедитесь, что платеж существует в БД и имеет статус `pending`
   - Проверяйте соответствие суммы Stars

2. **Защита от дублирования:**
   - Используйте уникальные `invoice_payload` для каждого платежа
   - Проверяйте, что платеж не был обработан ранее

3. **Валидация данных:**
   - Проверяйте `telegram_id` в payload
   - Проверяйте тип подписки
   - Проверяйте сумму платежа

4. **Логирование:**
   - Логируйте все платежи (успешные и неуспешные)
   - Храните историю платежей в БД

---

## 8. UX/UI рекомендации

### 8.1. Сообщения пользователю:

**При достижении лимита:**
```
❌ Достигнут лимит плейлистов!

📊 У вас уже создано 2 из 2 плейлистов.

💡 Хотите увеличить лимит?

[💳 Купить расширенный лимит] [🏠 Главное меню]
```

**При покупке:**
```
💳 Выберите тарифный план:

⭐ 5 плейлистов — 100 Stars
⭐ 10 плейлистов — 200 Stars
⭐ Безлимитные плейлисты — 500 Stars

💡 Stars — это внутренняя валюта Telegram.
Вы можете купить Stars прямо в приложении.
```

**После успешной оплаты:**
```
✅ Платеж успешно обработан!

🎉 Ваш лимит увеличен до 5 плейлистов

Теперь вы можете создавать больше плейлистов!
```

### 8.2. Команды:

- `/buy_limit` — покупка расширенного лимита
- `/my_subscription` — информация о текущей подписке
- `/payment_history` — история платежей (опционально)

---

## 9. План реализации

### Этап 1: Подготовка БД
- [ ] Создать таблицы `user_subscriptions` и `payments`
- [ ] Добавить методы в `DatabaseInterface`
- [ ] Реализовать методы в `SQLiteDatabase` и `PostgreSQLDatabase`
- [ ] Создать миграции для существующих БД

### Этап 2: Сервис платежей
- [ ] Создать `services/payment_service.py`
- [ ] Реализовать логику создания платежей
- [ ] Реализовать обработку успешных платежей
- [ ] Добавить валидацию и безопасность

### Этап 3: Обновление логики лимитов
- [ ] Обновить `get_user_playlist_limit` в БД
- [ ] Обновить проверку лимитов в `create_playlist_name`
- [ ] Обновить отображение лимитов в `my_playlists`

### Этап 4: Обработчики платежей
- [ ] Добавить команду `/buy_limit`
- [ ] Добавить обработчик `PreCheckoutQueryHandler`
- [ ] Добавить обработчик `MessageHandler` для `successful_payment`
- [ ] Добавить callback для кнопок покупки

### Этап 5: Тестирование
- [ ] Протестировать создание инвойсов
- [ ] Протестировать обработку платежей (в тестовом режиме)
- [ ] Протестировать активацию подписок
- [ ] Протестировать проверку лимитов

### Этап 6: Документация
- [ ] Обновить `docs/features.md`
- [ ] Обновить `docs/commands.md`
- [ ] Обновить `docs/architecture.md`
- [ ] Добавить инструкции по настройке

---

## 10. Вопросы для уточнения

1. **Цены:**
   - Какие цены установить для каждого тарифа?
   - Нужна ли подписка на месяц или разовая покупка?

2. **Лимиты:**
   - Какие лимиты предлагать? (5, 10, unlimited?)
   - Нужны ли промежуточные варианты?

3. **Верификация:**
   - Готов ли проект к верификации бота для вывода Stars?
   - В какой стране будет выводиться?

4. **Тестирование:**
   - Есть ли тестовый режим для Stars?
   - Как тестировать платежи без реальных Stars?

---

## 11. Полезные ссылки

- [Telegram Bot API - Payments](https://core.telegram.org/bots/api#payments)
- [Telegram Bot API - createInvoiceLink](https://core.telegram.org/bots/api#createinvoicelink)
- [Telegram Bot API - sendInvoice](https://core.telegram.org/bots/api#sendinvoice)
- [python-telegram-bot Documentation](https://python-telegram-bot.readthedocs.io/)
- [Telegram Stars для разработчиков](https://core.telegram.org/bots/payments#stars)

---

## 12. Заключение

Интеграция оплаты через Telegram Stars технически возможна и реализуема в текущем проекте. Основные шаги:

1. ✅ Добавить таблицы для подписок и платежей в БД
2. ✅ Создать сервис для работы с платежами
3. ✅ Обновить логику проверки лимитов
4. ✅ Добавить обработчики платежей в бота
5. ✅ Настроить тарифы и цены

**Следующие шаги:**
- Определить тарифы и цены
- Реализовать изменения в БД
- Создать сервис платежей
- Добавить обработчики в бота
- Протестировать интеграцию

---

**Статус исследования:** ✅ Завершено  
**Готовность к реализации:** 🟡 Требуется уточнение тарифов и цен

