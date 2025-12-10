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
        this.currentRevision = null; // Для проверки обновлений плейлиста
        
        this.init();
    }

    async init() {
        // Ждем инициализации Telegram API
        let attempts = 0;
        while (!this.telegramAPI.isAvailable() && attempts < 50) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        
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
        
        // Небольшая задержка для завершения инициализации
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Инициализируем Media Session API при старте (важно для iOS)
        this.initMediaSession();
        
        this.hideLoading();
        this.showContent();
        this.showPlaylistSelector();
    }
    
    /**
     * Инициализировать Media Session API при старте приложения
     * Это нужно делать заранее, чтобы iOS правильно обработал кнопки
     */
    initMediaSession() {
        if (!('mediaSession' in navigator)) {
            return; // Media Session API не поддерживается
        }
        
        try {
            // КРИТИЧНО для iOS: отключаем перемотку, чтобы кнопки переключали треки
            navigator.mediaSession.setActionHandler('seekbackward', null);
            navigator.mediaSession.setActionHandler('seekforward', null);
            
            // Устанавливаем переключение треков
            navigator.mediaSession.setActionHandler('previoustrack', async () => {
                await this.playPrevious();
            });
            
            navigator.mediaSession.setActionHandler('nexttrack', async () => {
                await this.playNext();
            });
            
            navigator.mediaSession.setActionHandler('play', async () => {
                if (this.player) {
                    await this.player.play();
                }
            });
            
            navigator.mediaSession.setActionHandler('pause', () => {
                if (this.player) {
                    this.player.pause();
                }
            });
        } catch (error) {
            console.warn('Ошибка при инициализации Media Session:', error);
        }
    }
    
    initPlayer() {
        // Создаем экземпляр плеера
        this.player = new Player();
        
        // Настраиваем обработчики событий плеера
        this.player.onPlay = () => {
            this.updatePlayPauseButton(true);
            this.updateActiveTrack(); // Обновляем кнопки в списке
            this.updateMediaSessionPlaybackState();
        };
        
        this.player.onPause = () => {
            this.updatePlayPauseButton(false);
            this.updateActiveTrack(); // Обновляем кнопки в списке
            this.updateMediaSessionPlaybackState();
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
            // Обновляем кнопку после загрузки метаданных
            this.updatePlayPauseButton(this.player.getIsPlaying(), false);
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
        
        // Форматируем сообщение (заменяем \n на <br>)
        const formattedMessage = message.replace(/\n/g, '<br>');
        
        if (errorMessage) {
            errorMessage.innerHTML = formattedMessage;
            errorMessage.style.textAlign = 'left';
            errorMessage.style.padding = '20px';
            errorMessage.style.lineHeight = '1.6';
        }
        
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
        // Загружаем плейлисты через REST API
        const playlistsList = document.getElementById('playlists-list');
        if (playlistsList) {
            playlistsList.innerHTML = '<p style="text-align: center; color: #999;">Загрузка плейлистов...</p>';
        }
        
        try {
            // Выполняем запрос к REST API
            const data = await this.telegramAPI.apiGet('/playlists');
            
            // Отображаем плейлисты
            if (data.playlists && data.playlists.length > 0) {
                this.displayPlaylists(data.playlists);
            } else {
                if (playlistsList) {
                    playlistsList.innerHTML = '<p style="text-align: center; color: #999;">Нет доступных плейлистов</p>';
                }
            }
        } catch (error) {
            console.error('Ошибка при загрузке плейлистов:', error);
            
            if (playlistsList) {
                playlistsList.innerHTML = `<p style="text-align: center; color: #ff4444;">Ошибка: ${error.message}</p>`;
            }
            
            this.showError(`Ошибка при загрузке плейлистов: ${error.message}`);
            this.telegramAPI.showAlert(`Ошибка при загрузке плейлистов: ${error.message}`);
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
        
        // Показываем загрузку
        const tracksList = document.getElementById('tracks-list');
        if (tracksList) {
            tracksList.innerHTML = '<p style="text-align: center; color: #999;">Загрузка треков...</p>';
        }
        
        try {
            // Запрашиваем треки через REST API
            const data = await this.telegramAPI.apiGet(`/playlists/${playlist.id}/tracks`);
            
            // Сохраняем revision для будущих проверок обновлений
            this.currentRevision = data.revision;
            
            // Отображаем треки
            if (data.tracks && data.tracks.length > 0) {
                this.displayTracks(data.tracks);
            } else {
                if (tracksList) {
                    tracksList.innerHTML = '<p style="text-align: center; color: #999;">Плейлист пуст</p>';
                }
            }
        } catch (error) {
            console.error('Ошибка при загрузке треков:', error);
            
            if (tracksList) {
                tracksList.innerHTML = `<p style="text-align: center; color: #ff4444;">Ошибка: ${error.message}</p>`;
            }
            
            this.showError(`Ошибка при загрузке треков: ${error.message}`);
            this.telegramAPI.showAlert(`Ошибка при загрузке треков: ${error.message}`);
        }
    }
    
    /**
     * Отобразить список треков
     * @param {Array} tracks - Массив треков
     */
    displayTracks(tracks) {
        if (!tracks || tracks.length === 0) {
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
            // Безопасная обработка артистов (может быть массивом или строкой)
            const artistsText = Array.isArray(track.artists) 
                ? track.artists.join(', ') 
                : (track.artists || 'Неизвестный артист');
            
            // Определяем иконку кнопки play/pause
            const isCurrentTrack = index === this.currentTrackIndex;
            const isPlaying = isCurrentTrack && this.player && this.player.getIsPlaying();
            const playPauseIcon = isPlaying ? '⏸' : '▶';
            
            trackItem.innerHTML = `
                <div class="track-item-content">
                    <div class="track-item-info">
                        <h4>${this.escapeHtml(track.title || 'Без названия')}</h4>
                        <p>${this.escapeHtml(artistsText)} • ${duration}</p>
                    </div>
                    <button class="track-play-btn" data-track-index="${index}">${playPauseIcon}</button>
                </div>
            `;
            
            // Обработчик клика на трек
            trackItem.addEventListener('click', (e) => {
                // Если клик по кнопке play/pause, не переключаем трек
                if (e.target.classList.contains('track-play-btn') || e.target.closest('.track-play-btn')) {
                    return;
                }
                this.currentTrackIndex = index;
                this.loadTrack(track);
            });
            
            // Обработчик клика на кнопку play/pause
            const playBtn = trackItem.querySelector('.track-play-btn');
            if (playBtn) {
                playBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (index === this.currentTrackIndex) {
                        // Если это текущий трек, переключаем play/pause
                        this.togglePlayPause();
                    } else {
                        // Иначе переключаемся на этот трек
                        this.currentTrackIndex = index;
                        this.loadTrack(track);
                    }
                });
            }
            
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
            return;
        }
        
        // Обновляем UI с информацией о треке
        const trackTitle = document.getElementById('track-title');
        const trackArtist = document.getElementById('track-artist');
        
        if (trackTitle) trackTitle.textContent = track.title || '-';
        // Безопасная обработка артистов (может быть массивом или строкой)
        const artistsText = Array.isArray(track.artists) 
            ? track.artists.join(', ') 
            : (track.artists || '-');
        if (trackArtist) trackArtist.textContent = artistsText;
        
        // Обновляем активный трек в списке
        this.updateActiveTrack();
        
        // Обновляем Media Session для нативного плеера
        this.updateMediaSession(track);
        
        // Если URL уже есть (например, был получен ранее), используем его
        if (track.url) {
            await this.playTrackUrl(track.url, track);
            return;
        }
        
        // Иначе запрашиваем URL у бота через REST API
        if (!this.currentPlaylistId) {
            this.showError('Не выбран плейлист');
            return;
        }
        
        try {
            // Запрашиваем URL трека через REST API
            const data = await this.telegramAPI.apiGet(
                `/tracks/${track.id}/stream?playlist_id=${this.currentPlaylistId}`
            );
            
            // Воспроизводим трек по полученному URL
            if (data.url) {
                await this.playTrackUrl(data.url, track);
            } else {
                this.showError('Не удалось получить URL трека');
            }
        } catch (error) {
            console.error('Ошибка при получении URL трека:', error);
            this.showError(`Ошибка: ${error.message}`);
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
        trackItems.forEach((item, index) => {
            item.classList.remove('active');
            
            // Обновляем кнопку play/pause
            const playBtn = item.querySelector('.track-play-btn');
            if (playBtn) {
                const isCurrentTrack = index === this.currentTrackIndex;
                const isPlaying = isCurrentTrack && this.player && this.player.getIsPlaying();
                playBtn.textContent = isCurrentTrack && isPlaying ? '⏸' : '▶';
            }
        });
        
        // Добавляем класс active текущему треку
        if (trackItems[this.currentTrackIndex]) {
            trackItems[this.currentTrackIndex].classList.add('active');
            // Обновляем кнопку для текущего трека
            const playBtn = trackItems[this.currentTrackIndex].querySelector('.track-play-btn');
            if (playBtn) {
                const isPlaying = this.player && this.player.getIsPlaying();
                playBtn.textContent = isPlaying ? '⏸' : '▶';
            }
        }
    }
    
    /**
     * Обновить Media Session для нативного плеера (iOS, Android)
     * Позволяет отображать информацию о треке на экране блокировки
     */
    updateMediaSession(track) {
        if (!('mediaSession' in navigator)) {
            return; // Media Session API не поддерживается
        }
        
        const artistsText = Array.isArray(track.artists) 
            ? track.artists.join(', ') 
            : (track.artists || 'Неизвестный артист');
        
        // Устанавливаем метаданные трека
        navigator.mediaSession.metadata = new MediaMetadata({
            title: track.title || 'Без названия',
            artist: artistsText,
            album: '', // Можно добавить, если будет доступно
            artwork: track.cover_url ? [
                { src: track.cover_url, sizes: '512x512', type: 'image/jpeg' }
            ] : []
        });
        
        // На iOS нужно переустанавливать обработчики при каждом обновлении трека
        // чтобы кнопки работали правильно
        try {
            // Отключаем перемотку (критично для iOS)
            navigator.mediaSession.setActionHandler('seekbackward', null);
            navigator.mediaSession.setActionHandler('seekforward', null);
            
            // Устанавливаем переключение треков
            navigator.mediaSession.setActionHandler('previoustrack', async () => {
                await this.playPrevious();
            });
            
            navigator.mediaSession.setActionHandler('nexttrack', async () => {
                await this.playNext();
            });
            
            navigator.mediaSession.setActionHandler('play', async () => {
                await this.player.play();
            });
            
            navigator.mediaSession.setActionHandler('pause', () => {
                this.player.pause();
            });
        } catch (error) {
            console.warn('Ошибка при обновлении обработчиков Media Session:', error);
        }
        
        // Обновляем состояние воспроизведения
        this.updateMediaSessionPlaybackState();
    }
    
    /**
     * Обновить состояние воспроизведения в Media Session
     */
    updateMediaSessionPlaybackState() {
        if (!('mediaSession' in navigator)) {
            return;
        }
        
        if (this.player && this.player.getIsPlaying()) {
            navigator.mediaSession.playbackState = 'playing';
        } else {
            navigator.mediaSession.playbackState = 'paused';
        }
    }
}

// Инициализируем приложение при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    window.miniApp = new MiniApp();
});

