/**
 * Основная логика приложения Mini App
 */
class MiniApp {
    constructor() {
        this.telegramAPI = window.telegramAPI;
        this.currentPlaylistId = null;
        this.currentTracks = [];
        this.currentTrackIndex = 0;
        
        this.init();
    }

    init() {
        // Проверяем доступность Telegram API
        if (!this.telegramAPI.isAvailable()) {
            this.showError('Telegram Web App API не доступен. Откройте приложение через Telegram.');
            return;
        }

        // Инициализируем UI
        this.setupEventListeners();
        
        // Показываем загрузку
        this.showLoading();
        
        // Имитируем загрузку (пока нет API)
        setTimeout(() => {
            this.hideLoading();
            this.showContent();
            this.showPlaylistSelector();
        }, 1000);
    }

    setupEventListeners() {
        // Кнопки управления плеером
        const playPauseBtn = document.getElementById('play-pause-btn');
        const prevBtn = document.getElementById('prev-btn');
        const nextBtn = document.getElementById('next-btn');

        if (playPauseBtn) {
            playPauseBtn.addEventListener('click', () => this.togglePlayPause());
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', () => this.playPrevious());
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => this.playNext());
        }
    }

    showLoading() {
        const loading = document.getElementById('loading');
        const content = document.getElementById('content');
        const error = document.getElementById('error');
        
        if (loading) loading.classList.remove('hidden');
        if (content) content.classList.add('hidden');
        if (error) error.classList.add('hidden');
    }

    hideLoading() {
        const loading = document.getElementById('loading');
        if (loading) loading.classList.add('hidden');
    }

    showContent() {
        const content = document.getElementById('content');
        if (content) content.classList.remove('hidden');
    }

    showError(message) {
        const error = document.getElementById('error');
        const errorMessage = document.getElementById('error-message');
        const content = document.getElementById('content');
        const loading = document.getElementById('loading');
        
        if (errorMessage) errorMessage.textContent = message;
        if (error) error.classList.remove('hidden');
        if (content) content.classList.add('hidden');
        if (loading) loading.classList.add('hidden');
    }

    showPlaylistSelector() {
        const selector = document.getElementById('playlist-selector');
        const playerSection = document.getElementById('player-section');
        
        if (selector) selector.classList.remove('hidden');
        if (playerSection) playerSection.classList.add('hidden');
        
        // Пока заглушка - запрос плейлистов будет через API
        this.loadPlaylists();
    }

    showPlayer() {
        const selector = document.getElementById('playlist-selector');
        const playerSection = document.getElementById('player-section');
        
        if (selector) selector.classList.add('hidden');
        if (playerSection) playerSection.classList.remove('hidden');
    }

    async loadPlaylists() {
        // Отправляем запрос на получение плейлистов через sendData()
        const playlistsList = document.getElementById('playlists-list');
        if (playlistsList) {
            playlistsList.innerHTML = '<p style="text-align: center; color: #999;">Загрузка плейлистов...</p>';
        }
        
        // Отправляем запрос боту через Telegram Web App API
        if (this.telegramAPI.isAvailable()) {
            this.telegramAPI.sendData({
                action: 'get_playlists'
            });
            
            // Показываем уведомление пользователю
            this.telegramAPI.showAlert('Запрос на получение плейлистов отправлен. Ответ придет в виде сообщения в боте.');
        } else {
            if (playlistsList) {
                playlistsList.innerHTML = '<p style="text-align: center; color: #ff4444;">Ошибка: Telegram Web App API не доступен</p>';
            }
        }
    }

    togglePlayPause() {
        const btn = document.getElementById('play-pause-btn');
        if (!btn) return;
        
        // TODO: Реализовать логику воспроизведения
        if (btn.classList.contains('playing')) {
            btn.classList.remove('playing');
            btn.textContent = '▶';
        } else {
            btn.classList.add('playing');
            btn.textContent = '⏸';
        }
    }

    playPrevious() {
        if (this.currentTrackIndex > 0) {
            this.currentTrackIndex--;
            this.loadTrack(this.currentTracks[this.currentTrackIndex]);
        }
    }

    playNext() {
        if (this.currentTrackIndex < this.currentTracks.length - 1) {
            this.currentTrackIndex++;
            this.loadTrack(this.currentTracks[this.currentTrackIndex]);
        }
    }

    loadTrack(track) {
        // TODO: Реализовать загрузку и воспроизведение трека
        const trackTitle = document.getElementById('track-title');
        const trackArtist = document.getElementById('track-artist');
        
        if (trackTitle) trackTitle.textContent = track?.title || '-';
        if (trackArtist) trackArtist.textContent = track?.artists?.join(', ') || '-';
    }
}

// Инициализируем приложение при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    window.miniApp = new MiniApp();
});

