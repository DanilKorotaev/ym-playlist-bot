/**
 * Основная логика приложения Mini App
 */
class MiniApp {
    constructor() {
        this.telegramAPI = window.telegramAPI;
        this.player = null;
        this.currentPlaylistId = null;
        this.currentTracks = [];
        this.currentTrackIndex = 0;
        this.pendingTrackUrl = null; // Для хранения URL, ожидающего загрузки
        
        this.init();
    }

    init() {
        // Проверяем доступность Telegram API
        if (!this.telegramAPI.isAvailable()) {
            this.showError('Telegram Web App API не доступен. Откройте приложение через Telegram.');
            return;
        }

        // Инициализируем плеер
        this.initPlayer();
        
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
    
    initPlayer() {
        // Создаем экземпляр плеера
        this.player = new Player();
        
        // Настраиваем обработчики событий плеера
        this.player.onPlay = () => {
            this.updatePlayPauseButton(true);
        };
        
        this.player.onPause = () => {
            this.updatePlayPauseButton(false);
        };
        
        this.player.onTimeUpdate = (data) => {
            this.updateProgress(data);
        };
        
        this.player.onEnded = () => {
            // Автоматически переходим к следующему треку
            this.playNext();
        };
        
        this.player.onError = (error) => {
            console.error('Ошибка плеера:', error);
            this.showError(error.message || 'Ошибка воспроизведения трека');
        };
        
        this.player.onLoadStart = () => {
            this.updatePlayPauseButton(false, true); // Показываем загрузку
        };
        
        this.player.onLoadedMetadata = (data) => {
            this.updateTotalTime(data.duration);
        };
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
        
        // Прогресс-бар для перемотки
        const progressBar = document.querySelector('.progress-bar');
        if (progressBar) {
            progressBar.addEventListener('click', (e) => this.handleProgressBarClick(e));
        }
    }
    
    /**
     * Обработать клик по прогресс-бару для перемотки
     * @param {Event} e - Событие клика
     */
    handleProgressBarClick(e) {
        if (!this.player) return;
        
        const progressBar = e.currentTarget;
        const rect = progressBar.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const percentage = clickX / rect.width;
        
        const duration = this.player.getDuration();
        if (duration > 0) {
            const newTime = duration * percentage;
            this.player.seek(newTime);
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
    
    /**
     * Отобразить список плейлистов
     * @param {Array} playlists - Массив плейлистов
     */
    displayPlaylists(playlists) {
        const playlistsList = document.getElementById('playlists-list');
        if (!playlistsList) return;
        
        if (!playlists || playlists.length === 0) {
            playlistsList.innerHTML = '<p style="text-align: center; color: #999;">Нет доступных плейлистов</p>';
            return;
        }
        
        playlistsList.innerHTML = '';
        
        playlists.forEach(playlist => {
            const playlistItem = document.createElement('div');
            playlistItem.className = 'playlist-item';
            playlistItem.innerHTML = `
                <h3>${this.escapeHtml(playlist.title || 'Без названия')}</h3>
                <p>${playlist.track_count || 0} треков ${playlist.is_shared ? '(Общий)' : ''}</p>
            `;
            
            playlistItem.addEventListener('click', () => {
                this.selectPlaylist(playlist);
            });
            
            playlistsList.appendChild(playlistItem);
        });
    }
    
    /**
     * Выбрать плейлист и загрузить его треки
     * @param {Object} playlist - Объект плейлиста
     */
    async selectPlaylist(playlist) {
        this.currentPlaylistId = playlist.id;
        
        // Запрашиваем треки из плейлиста
        if (this.telegramAPI.isAvailable()) {
            this.telegramAPI.sendData({
                action: 'get_tracks',
                playlist_id: playlist.id
            });
            
            this.telegramAPI.showAlert('Запрос треков отправлен. Ответ придет в виде сообщения в боте.');
        }
    }
    
    /**
     * Отобразить список треков
     * @param {Array} tracks - Массив треков
     */
    displayTracks(tracks) {
        if (!tracks || tracks.length === 0) {
            console.warn('Нет треков для отображения');
            return;
        }
        
        this.currentTracks = tracks;
        this.currentTrackIndex = 0;
        
        const tracksList = document.getElementById('tracks-list');
        if (!tracksList) return;
        
        tracksList.innerHTML = '';
        
        tracks.forEach((track, index) => {
            const trackItem = document.createElement('div');
            trackItem.className = 'track-item';
            if (index === 0) {
                trackItem.classList.add('active');
            }
            
            const duration = this.formatTime(track.duration || 0);
            trackItem.innerHTML = `
                <h4>${this.escapeHtml(track.title || 'Без названия')}</h4>
                <p>${this.escapeHtml(track.artists?.join(', ') || 'Неизвестный артист')} • ${duration}</p>
            `;
            
            trackItem.addEventListener('click', () => {
                this.currentTrackIndex = index;
                this.loadTrack(track);
            });
            
            tracksList.appendChild(trackItem);
        });
        
        // Показываем плеер
        this.showPlayer();
    }
    
    /**
     * Экранировать HTML для безопасности
     * @param {string} text - Текст для экранирования
     * @returns {string}
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async togglePlayPause() {
        if (!this.player) return;
        
        // Если нет загруженного трека, но есть текущий трек в очереди
        if (!this.player.audio?.src && this.currentTracks.length > 0) {
            // Загружаем текущий трек
            await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            return;
        }
        
        await this.player.togglePlayPause();
    }
    
    updatePlayPauseButton(isPlaying, isLoading = false) {
        const btn = document.getElementById('play-pause-btn');
        if (!btn) return;
        
        if (isLoading) {
            btn.textContent = '⏳';
            btn.disabled = true;
        } else {
            btn.disabled = false;
            if (isPlaying) {
                btn.classList.add('playing');
                btn.textContent = '⏸';
            } else {
                btn.classList.remove('playing');
                btn.textContent = '▶';
            }
        }
    }

    async playPrevious() {
        if (this.currentTrackIndex > 0) {
            this.currentTrackIndex--;
            await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
        }
    }

    async playNext() {
        if (this.currentTrackIndex < this.currentTracks.length - 1) {
            this.currentTrackIndex++;
            await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
        }
    }

    async loadTrack(track) {
        if (!track) {
            console.warn('Нет трека для загрузки');
            return;
        }
        
        // Обновляем UI с информацией о треке
        const trackTitle = document.getElementById('track-title');
        const trackArtist = document.getElementById('track-artist');
        
        if (trackTitle) trackTitle.textContent = track.title || '-';
        if (trackArtist) trackArtist.textContent = track.artists?.join(', ') || '-';
        
        // Обновляем активный трек в списке
        this.updateActiveTrack();
        
        // Если URL уже есть (например, был получен ранее), используем его
        if (track.url) {
            await this.playTrackUrl(track.url, track);
            return;
        }
        
        // Иначе запрашиваем URL у бота
        if (!this.currentPlaylistId) {
            this.showError('Не выбран плейлист');
            return;
        }
        
        // Отправляем запрос на получение URL трека
        if (this.telegramAPI.isAvailable()) {
            this.pendingTrackUrl = track; // Сохраняем трек для загрузки после получения URL
            this.telegramAPI.sendData({
                action: 'get_track_url',
                track_id: track.id,
                playlist_id: this.currentPlaylistId
            });
            
            // Показываем уведомление
            this.telegramAPI.showAlert('Запрос URL трека отправлен. Ответ придет в виде сообщения в боте.');
        } else {
            this.showError('Telegram Web App API не доступен');
        }
    }
    
    /**
     * Воспроизвести трек по URL
     * @param {string} url - URL трека
     * @param {Object} trackInfo - Информация о треке
     */
    async playTrackUrl(url, trackInfo) {
        if (!this.player) {
            this.showError('Плеер не инициализирован');
            return;
        }
        
        try {
            // Загружаем трек в плеер
            await this.player.loadTrack(url, trackInfo);
            
            // Автоматически начинаем воспроизведение
            await this.player.play();
        } catch (error) {
            console.error('Ошибка при загрузке трека:', error);
            this.showError('Не удалось загрузить трек');
        }
    }
    
    /**
     * Обработать URL трека, полученный от бота
     * @param {string} url - URL трека
     * @param {Object} trackInfo - Информация о треке
     */
    handleTrackUrl(url, trackInfo) {
        // Сохраняем URL в объекте трека
        if (trackInfo) {
            trackInfo.url = url;
        }
        
        // Если это ожидаемый трек, загружаем его
        if (this.pendingTrackUrl && 
            this.pendingTrackUrl.id === trackInfo?.id) {
            this.playTrackUrl(url, trackInfo || this.pendingTrackUrl);
            this.pendingTrackUrl = null;
        }
    }
    
    /**
     * Обновить прогресс воспроизведения
     * @param {Object} data - Данные о прогрессе {currentTime, duration, progress}
     */
    updateProgress(data) {
        const progressBar = document.getElementById('progress');
        const currentTimeEl = document.getElementById('current-time');
        
        if (progressBar) {
            progressBar.style.width = `${data.progress}%`;
        }
        
        if (currentTimeEl) {
            currentTimeEl.textContent = this.formatTime(data.currentTime);
        }
    }
    
    /**
     * Обновить общее время трека
     * @param {number} duration - Длительность в секундах
     */
    updateTotalTime(duration) {
        const totalTimeEl = document.getElementById('total-time');
        if (totalTimeEl) {
            totalTimeEl.textContent = this.formatTime(duration);
        }
    }
    
    /**
     * Форматировать время в формат MM:SS
     * @param {number} seconds - Время в секундах
     * @returns {string}
     */
    formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) {
            return '0:00';
        }
        
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }
    
    /**
     * Обновить активный трек в списке
     */
    updateActiveTrack() {
        const tracksList = document.getElementById('tracks-list');
        if (!tracksList) return;
        
        // Убираем класс active со всех треков
        const trackItems = tracksList.querySelectorAll('.track-item');
        trackItems.forEach(item => item.classList.remove('active'));
        
        // Добавляем класс active текущему треку
        if (trackItems[this.currentTrackIndex]) {
            trackItems[this.currentTrackIndex].classList.add('active');
        }
    }
}

// Инициализируем приложение при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    window.miniApp = new MiniApp();
});

