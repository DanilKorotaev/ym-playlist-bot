"""
Авторизация для Telegram Mini App через initData.
"""
import hmac
import hashlib
import json
import logging
from urllib.parse import parse_qsl
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def validate_telegram_init_data(init_data: str, bot_token: str) -> Dict[str, str]:
    """
    Валидация initData от Telegram Web App.
    
    Args:
        init_data: Строка с данными от Telegram Web App (query string)
        bot_token: Токен бота для проверки подписи
        
    Returns:
        Словарь с распарсенными данными
        
    Raises:
        ValueError: Если подпись неверна
    """
    # Парсим данные
    parsed_data = dict(parse_qsl(init_data))
    
    # Извлекаем hash
    received_hash = parsed_data.pop('hash', '')
    
    if not received_hash:
        raise ValueError("Missing hash in initData")
    
    # Создаем строку для проверки (сортируем ключи)
    data_check_string = '\n'.join(
        f"{k}={v}" for k, v in sorted(parsed_data.items())
    )
    
    # Вычисляем секретный ключ
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode(),
        digestmod=hashlib.sha256
    ).digest()
    
    # Вычисляем hash
    calculated_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()
    
    # Проверяем
    if calculated_hash != received_hash:
        raise ValueError("Invalid initData signature")
    
    return parsed_data


def extract_user_id(init_data: str, bot_token: str) -> Optional[int]:
    """
    Извлечь user_id из initData.
    
    Args:
        init_data: Строка с данными от Telegram Web App
        bot_token: Токен бота для проверки подписи
        
    Returns:
        user_id или None при ошибке
    """
    try:
        data = validate_telegram_init_data(init_data, bot_token)
        
        # Извлекаем user из JSON строки
        user_str = data.get('user', '')
        if not user_str:
            return None
        
        # Парсим JSON
        user_data = json.loads(user_str)
        user_id = user_data.get('id')
        
        if user_id:
            return int(user_id)
        
        return None
    except Exception as e:
        logger.error(f"Ошибка при извлечении user_id: {e}")
        return None

