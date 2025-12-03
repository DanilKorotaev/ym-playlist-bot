"""
Определения состояний FSM для Telegram бота.
"""
from aiogram.fsm.state import State, StatesGroup


class CreatePlaylistStates(StatesGroup):
    """Состояния для создания плейлиста."""
    waiting_playlist_name = State()


class SetTokenStates(StatesGroup):
    """Состояния для установки токена."""
    waiting_token = State()


class EditNameStates(StatesGroup):
    """Состояния для редактирования названия плейлиста."""
    waiting_edit_name = State()


class DeleteTrackStates(StatesGroup):
    """Состояния для удаления трека."""
    waiting_track_number = State()


class SetCoverStates(StatesGroup):
    """Состояния для установки обложки плейлиста."""
    waiting_playlist_cover = State()

