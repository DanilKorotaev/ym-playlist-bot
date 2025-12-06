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
    
    async def create_payment(self, telegram_id: int, subscription_type: str) -> Optional[Dict]:
        """Создать платеж и вернуть данные для инвойса."""
        if subscription_type not in SUBSCRIPTION_PLANS:
            return None
        
        plan = SUBSCRIPTION_PLANS[subscription_type]
        payload = self.generate_invoice_payload(telegram_id, subscription_type)
        
        # Создаем запись о платеже
        payment_id = await self.db.create_payment(
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
    
    async def process_successful_payment(self, telegram_id: int, invoice_payload: str, 
                                   stars_amount: int) -> bool:
        """Обработать успешный платеж."""
        # Обновляем статус платежа
        await self.db.update_payment_status(invoice_payload, 'completed')
        
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
        
        await self.db.create_subscription(
            telegram_id=telegram_id,
            subscription_type=subscription_type,
            stars_amount=stars_amount,
            expires_at=expires_at
        )
        
        logger.info(f"Подписка активирована для пользователя {telegram_id}: {subscription_type}")
        return True

