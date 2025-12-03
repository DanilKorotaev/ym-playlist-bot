"""
Модуль для управления контекстом пользователей.
Хранит информацию о выбранном плейлисте для каждого пользователя.
"""
import asyncio
from typing import Optional, Dict
from database import DatabaseInterface


class UserContextManager:
    """Менеджер контекста пользователей."""
    
    def __init__(self, db: DatabaseInterface):
        """
        Инициализация менеджера.
        
        Args:
            db: Интерфейс базы данных
        """
        self.db = db
        self._contexts: Dict[int, Dict] = {}  # {telegram_id: {"current_playlist_id": ...}}
    
    async def get_active_playlist_id(self, telegram_id: int) -> Optional[int]:
        """
        Получить ID активного плейлиста пользователя.
        
        Args:
            telegram_id: ID пользователя Telegram
            
        Returns:
            ID плейлиста или None
        """
        if telegram_id in self._contexts and "current_playlist_id" in self._contexts[telegram_id]:
            return self._contexts[telegram_id]["current_playlist_id"]
        
        # Пытаемся взять первый доступный плейлист
        playlists = await self.db.get_user_playlists(telegram_id)
        if playlists:
            playlist_id = playlists[0]["id"]
            if telegram_id not in self._contexts:
                self._contexts[telegram_id] = {}
            self._contexts[telegram_id]["current_playlist_id"] = playlist_id
            return playlist_id
        return None
    
    def set_active_playlist(self, telegram_id: int, playlist_id: int) -> None:
        """
        Установить активный плейлист для пользователя.
        
        Args:
            telegram_id: ID пользователя Telegram
            playlist_id: ID плейлиста
        """
        if telegram_id not in self._contexts:
            self._contexts[telegram_id] = {}
        self._contexts[telegram_id]["current_playlist_id"] = playlist_id
    
    def clear_active_playlist(self, telegram_id: int) -> None:
        """
        Очистить активный плейлист для пользователя.
        
        Args:
            telegram_id: ID пользователя Telegram
        """
        if telegram_id in self._contexts:
            self._contexts[telegram_id].pop("current_playlist_id", None)
    
    async def get_active_playlist_info(self, telegram_id: int) -> Optional[str]:
        """
        Получить информацию об активном плейлисте.
        
        Args:
            telegram_id: ID пользователя Telegram
            
        Returns:
            Строка с информацией о плейлисте или None
        """
        if telegram_id in self._contexts and "current_playlist_id" in self._contexts[telegram_id]:
            playlist_id = self._contexts[telegram_id]["current_playlist_id"]
            playlist = await self.db.get_playlist(playlist_id)
            if playlist:
                title = playlist.get("title") or "Без названия"
                return f"🎵 Активный плейлист: «{title}»"
        return None

