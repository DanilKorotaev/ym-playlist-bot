/**
 * Класс для автоматического обновления очереди плейлиста
 */
class PlaylistUpdater {
    constructor(playlistId, currentRevision, queue, telegramAPI, onTracksAdded) {
        this.playlistId = playlistId;
        this.currentRevision = currentRevision;
        this.queue = queue; // Объект с методами для работы с очередью
        this.telegramAPI = telegramAPI;
        this.onTracksAdded = onTracksAdded; // Callback при добавлении треков
        this.checkInterval = 10000; // 10 секунд (настраивается через конфиг)
        this.intervalId = null;
        this.isChecking = false; // Флаг для предотвращения параллельных проверок
    }
    
    /**
     * Начать периодическую проверку обновлений
     */
    start() {
        if (this.intervalId) {
            return; // Уже запущен
        }
        
        this.intervalId = setInterval(() => {
            this.checkForUpdates();
        }, this.checkInterval);
        
        console.log(`PlaylistUpdater: Запущена проверка обновлений для плейлиста ${this.playlistId} (интервал: ${this.checkInterval}ms)`);
    }
    
    /**
     * Остановить проверку обновлений
     */
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
            console.log(`PlaylistUpdater: Остановлена проверка обновлений для плейлиста ${this.playlistId}`);
        }
    }
    
    /**
     * Обновить revision после получения обновлений
     * @param {number} newRevision - Новая версия плейлиста
     */
    updateRevision(newRevision) {
        this.currentRevision = newRevision;
    }
    
    /**
     * Проверить обновления плейлиста
     */
    async checkForUpdates() {
        // Предотвращаем параллельные проверки
        if (this.isChecking) {
            return;
        }
        
        // Проверяем, близок ли текущий трек к концу очереди
        const currentIndex = this.queue.getCurrentIndex();
        const queueLength = this.queue.getTracks().length;
        const remainingTracks = queueLength - currentIndex;
        
        // Проверяем только если осталось 2-3 трека или меньше
        if (remainingTracks > 3) {
            return; // Не проверяем, если очередь еще длинная
        }
        
        this.isChecking = true;
        
        try {
            const response = await this.telegramAPI.apiGet(
                `/playlists/${this.playlistId}/updates?revision=${this.currentRevision}`
            );
            
            // Всегда обновляем revision, если он изменился
            if (response.new_revision && response.new_revision !== this.currentRevision) {
                this.currentRevision = response.new_revision;
            }
            
            if (response.has_updates && response.new_tracks && response.new_tracks.length > 0) {
                // Получаем текущие треки для сравнения
                const currentTracks = this.queue.getTracks();
                const currentTrackIds = new Set(currentTracks.map(t => t.id));
                
                // Фильтруем только новые треки (которых еще нет в очереди)
                const newTracks = response.new_tracks.filter(track => !currentTrackIds.has(track.id));
                
                if (newTracks.length > 0) {
                    // Добавляем новые треки в конец очереди
                    this.queue.addTracks(newTracks);
                    
                    // Вызываем callback для уведомления
                    if (this.onTracksAdded) {
                        this.onTracksAdded(newTracks.length, response.new_tracks_count);
                    }
                    
                    console.log(`PlaylistUpdater: Добавлено ${newTracks.length} новых треков в очередь`);
                } else {
                    // Обновления есть, но все треки уже в очереди (возможно, порядок изменился)
                    console.log('PlaylistUpdater: Обновления есть, но все треки уже в очереди');
                }
            }
        } catch (error) {
            console.error('PlaylistUpdater: Ошибка при проверке обновлений:', error);
            // Не показываем ошибку пользователю, чтобы не мешать воспроизведению
        } finally {
            this.isChecking = false;
        }
    }
}

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
        this.playlistUpdater = null; // Экземпляр PlaylistUpdater
        
        // Режимы воспроизведения
        this.isShuffled = false;
        this.repeatMode = 'none'; // 'none', 'all', 'one'
        this.shuffledIndices = []; // Индексы треков в перемешанном порядке
        
        this.init();
    }

    async init() {
        try {
            console.log('MiniApp: Начало инициализации...');
            
            // Ждем инициализации Telegram API
            let attempts = 0;
            while (!this.telegramAPI.isAvailable() && attempts < 50) {
                await new Promise(resolve => setTimeout(resolve, 100));
                attempts++;
            }
            
            // Проверяем доступность Telegram API
            if (!this.telegramAPI.isAvailable()) {
                console.error('MiniApp: Telegram Web App API не доступен');
                this.showError('Telegram Web App API не доступен. Откройте приложение через Telegram.');
                return;
            }
            
            console.log('MiniApp: Telegram API доступен');

            // Инициализируем тему Telegram
            this.initTheme();
            
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
            
            console.log('MiniApp: Инициализация завершена, загрузка плейлистов...');
            
            this.hideLoading();
            this.showContent();
            this.showPlaylistSelector();
        } catch (error) {
            console.error('MiniApp: Критическая ошибка при инициализации:', error);
            this.showError(`Ошибка инициализации: ${error.message}\n\nПроверьте консоль браузера для деталей.`);
        }
    }
    
    /**
     * Инициализировать тему Telegram
     */
    initTheme() {
        if (!this.telegramAPI.webApp) return;
        
        const webApp = this.telegramAPI.webApp;
        const colorScheme = webApp.colorScheme || 'light';
        
        // Применяем тему к body
        if (colorScheme === 'dark') {
            document.body.classList.add('theme-dark');
            
            // Устанавливаем CSS переменные из Telegram API
            const themeParams = webApp.themeParams || {};
            if (themeParams.bg_color) {
                document.documentElement.style.setProperty('--tg-dark-bg-color', themeParams.bg_color);
            }
            if (themeParams.text_color) {
                document.documentElement.style.setProperty('--tg-dark-text-color', themeParams.text_color);
            }
            if (themeParams.hint_color) {
                document.documentElement.style.setProperty('--tg-dark-hint-color', themeParams.hint_color);
            }
            if (themeParams.link_color) {
                document.documentElement.style.setProperty('--tg-dark-link-color', themeParams.link_color);
            }
            if (themeParams.button_color) {
                document.documentElement.style.setProperty('--tg-dark-button-color', themeParams.button_color);
            }
            if (themeParams.button_text_color) {
                document.documentElement.style.setProperty('--tg-dark-button-text-color', themeParams.button_text_color);
            }
            if (themeParams.secondary_bg_color) {
                document.documentElement.style.setProperty('--tg-dark-secondary-bg-color', themeParams.secondary_bg_color);
            }
        } else {
            document.body.classList.remove('theme-dark');
            
            // Устанавливаем CSS переменные для светлой темы
            const themeParams = webApp.themeParams || {};
            if (themeParams.bg_color) {
                document.documentElement.style.setProperty('--tg-theme-bg-color', themeParams.bg_color);
            }
            if (themeParams.text_color) {
                document.documentElement.style.setProperty('--tg-theme-text-color', themeParams.text_color);
            }
            if (themeParams.hint_color) {
                document.documentElement.style.setProperty('--tg-theme-hint-color', themeParams.hint_color);
            }
            if (themeParams.link_color) {
                document.documentElement.style.setProperty('--tg-theme-link-color', themeParams.link_color);
            }
            if (themeParams.button_color) {
                document.documentElement.style.setProperty('--tg-theme-button-color', themeParams.button_color);
            }
            if (themeParams.button_text_color) {
                document.documentElement.style.setProperty('--tg-theme-button-text-color', themeParams.button_text_color);
            }
            if (themeParams.secondary_bg_color) {
                document.documentElement.style.setProperty('--tg-theme-secondary-bg-color', themeParams.secondary_bg_color);
            }
        }
        
        // Слушаем изменения темы
        if (webApp.onEvent) {
            webApp.onEvent('themeChanged', () => {
                this.initTheme();
            });
        }
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
        
        // Устанавливаем максимальную громкость (управление громкостью через системные настройки)
        this.player.setVolume(1.0);
        
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
            // Обрабатываем окончание трека в зависимости от режима повтора
            if (this.repeatMode === 'one') {
                // Повторяем текущий трек
                this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            } else {
                // Переходим к следующему треку
                this.playNext();
            }
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
        const shuffleBtn = document.getElementById('shuffle-btn');
        const repeatBtn = document.getElementById('repeat-btn');

        if (playPauseBtn) {
            playPauseBtn.addEventListener('click', () => this.togglePlayPause());
        }

        if (prevBtn) {
            prevBtn.addEventListener('click', () => this.playPrevious());
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => this.playNext());
        }
        
        if (shuffleBtn) {
            shuffleBtn.addEventListener('click', () => this.toggleShuffle());
        }
        
        if (repeatBtn) {
            repeatBtn.addEventListener('click', () => this.toggleRepeat());
        }
        
        // Прогресс-бар для перемотки
        const progressBar = document.querySelector('.progress-bar');
        if (progressBar) {
            progressBar.addEventListener('click', (e) => this.handleProgressBarClick(e));
            progressBar.addEventListener('mousedown', (e) => this.handleProgressBarMouseDown(e));
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
    
    /**
     * Обработать начало перетаскивания прогресс-бара
     * @param {Event} e - Событие mousedown
     */
    handleProgressBarMouseDown(e) {
        const progressBar = e.currentTarget;
        progressBar.classList.add('dragging');
        
        const handleMouseMove = (moveEvent) => {
            if (!this.player) return;
            
            const rect = progressBar.getBoundingClientRect();
            const clickX = moveEvent.clientX - rect.left;
            const percentage = Math.max(0, Math.min(1, clickX / rect.width));
            
            const duration = this.player.getDuration();
            if (duration > 0) {
                const newTime = duration * percentage;
                this.player.seek(newTime);
            }
        };
        
        const handleMouseUp = () => {
            progressBar.classList.remove('dragging');
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };
        
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
        
        // Также обрабатываем клик
        this.handleProgressBarClick(e);
    }
    
    /**
     * Переключить режим перемешивания
     */
    toggleShuffle() {
        this.isShuffled = !this.isShuffled;
        this.updateShuffleButton();
        
        if (this.isShuffled) {
            this.shuffleTracks();
        } else {
            this.shuffledIndices = [];
        }
    }
    
    /**
     * Перемешать треки
     */
    shuffleTracks() {
        this.shuffledIndices = Array.from({ length: this.currentTracks.length }, (_, i) => i);
        
        // Алгоритм Fisher-Yates для перемешивания
        for (let i = this.shuffledIndices.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [this.shuffledIndices[i], this.shuffledIndices[j]] = [this.shuffledIndices[j], this.shuffledIndices[i]];
        }
        
        // Находим текущий трек в перемешанном списке
        const currentOriginalIndex = this.currentTrackIndex;
        const shuffledIndex = this.shuffledIndices.indexOf(currentOriginalIndex);
        if (shuffledIndex !== -1) {
            // Перемещаем текущий трек в начало перемешанного списка
            this.shuffledIndices.splice(shuffledIndex, 1);
            this.shuffledIndices.unshift(currentOriginalIndex);
        }
    }
    
    /**
     * Обновить кнопку перемешивания
     */
    updateShuffleButton() {
        const shuffleBtn = document.getElementById('shuffle-btn');
        if (shuffleBtn) {
            if (this.isShuffled) {
                shuffleBtn.classList.add('active');
                shuffleBtn.title = 'Перемешивание включено';
            } else {
                shuffleBtn.classList.remove('active');
                shuffleBtn.title = 'Перемешать';
            }
        }
    }
    
    /**
     * Переключить режим повтора
     */
    toggleRepeat() {
        const modes = ['none', 'all', 'one'];
        const currentIndex = modes.indexOf(this.repeatMode);
        this.repeatMode = modes[(currentIndex + 1) % modes.length];
        this.updateRepeatButton();
    }
    
    /**
     * Обновить кнопку повтора
     */
    updateRepeatButton() {
        const repeatBtn = document.getElementById('repeat-btn');
        if (repeatBtn) {
            repeatBtn.classList.remove('active');
            if (this.repeatMode === 'all') {
                repeatBtn.classList.add('active');
                repeatBtn.textContent = '↻';
            } else if (this.repeatMode === 'one') {
                repeatBtn.classList.add('active');
                repeatBtn.textContent = '↻';
                repeatBtn.title = 'Повтор одного трека';
            } else {
                repeatBtn.textContent = '↻';
                repeatBtn.title = 'Повтор';
            }
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
            
            const coverHtml = playlist.cover_url 
                ? `<img src="${this.escapeHtml(playlist.cover_url)}" alt="Обложка плейлиста" class="playlist-cover" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />`
                : '';
            const coverPlaceholder = playlist.cover_url 
                ? `<div class="playlist-cover-placeholder" style="display: none;">🎵</div>`
                : `<div class="playlist-cover-placeholder">🎵</div>`;
            
            playlistItem.innerHTML = `
                ${coverHtml}
                ${coverPlaceholder}
                <div class="playlist-item-info">
                    <h3>${this.escapeHtml(playlist.title || 'Без названия')}</h3>
                    <p>${playlist.track_count || 0} треков ${playlist.is_shared ? '(Общий)' : ''}</p>
                </div>
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
        
        // Останавливаем предыдущий updater, если он был
        if (this.playlistUpdater) {
            this.playlistUpdater.stop();
            this.playlistUpdater = null;
        }
        
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
                
                // Запускаем автоматическое обновление очереди
                this.startPlaylistUpdater(playlist.id, data.revision);
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
        
        // Сбрасываем режимы воспроизведения при загрузке нового плейлиста
        this.isShuffled = false;
        this.repeatMode = 'none';
        this.shuffledIndices = [];
        this.updateShuffleButton();
        this.updateRepeatButton();
        
        this.renderTracksList();
        
        // Показываем плеер
        this.showPlayer();
    }
    
    /**
     * Отрендерить список треков в UI
     */
    renderTracksList() {
        const tracksList = document.getElementById('tracks-list');
        if (!tracksList) return;
        
        tracksList.innerHTML = '';
        
        this.currentTracks.forEach((track, index) => {
            const trackItem = document.createElement('div');
            trackItem.className = 'track-item';
            if (index === this.currentTrackIndex) {
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
            
            const coverHtml = track.cover_url 
                ? `<img src="${this.escapeHtml(track.cover_url)}" alt="Обложка трека" class="track-item-cover" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />`
                : '';
            const coverPlaceholder = track.cover_url 
                ? `<div class="track-item-cover-placeholder" style="display: none;">🎵</div>`
                : `<div class="track-item-cover-placeholder">🎵</div>`;
            
            trackItem.innerHTML = `
                <div class="track-item-content">
                    ${coverHtml}
                    ${coverPlaceholder}
                    <div class="track-item-content-with-cover">
                        <div class="track-item-info">
                            <h4>${this.escapeHtml(track.title || 'Без названия')}</h4>
                            <p>${this.escapeHtml(artistsText)} • ${duration}</p>
                        </div>
                        <button class="track-play-btn" data-track-index="${index}">${playPauseIcon}</button>
                    </div>
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
    }
    
    /**
     * Запустить автоматическое обновление очереди плейлиста
     * @param {number} playlistId - ID плейлиста
     * @param {number} revision - Текущая версия плейлиста
     */
    startPlaylistUpdater(playlistId, revision) {
        // Останавливаем предыдущий updater, если он был
        if (this.playlistUpdater) {
            this.playlistUpdater.stop();
        }
        
        // Создаем объект-обертку для работы с очередью
        const queueWrapper = {
            getCurrentIndex: () => this.currentTrackIndex,
            getTracks: () => this.currentTracks,
            addTracks: (newTracks) => this.addTracksToQueue(newTracks)
        };
        
        // Создаем экземпляр PlaylistUpdater
        this.playlistUpdater = new PlaylistUpdater(
            playlistId,
            revision,
            queueWrapper,
            this.telegramAPI,
            (newTracksCount, totalNewTracks) => this.onTracksAdded(newTracksCount, totalNewTracks)
        );
        
        // Запускаем проверку
        this.playlistUpdater.start();
    }
    
    /**
     * Добавить новые треки в конец очереди
     * @param {Array} newTracks - Массив новых треков
     */
    addTracksToQueue(newTracks) {
        if (!newTracks || newTracks.length === 0) {
            return;
        }
        
        // Добавляем новые треки в конец очереди
        this.currentTracks = [...this.currentTracks, ...newTracks];
        
        // Обновляем UI
        this.renderTracksList();
        
        console.log(`MiniApp: Добавлено ${newTracks.length} новых треков в очередь. Всего треков: ${this.currentTracks.length}`);
    }
    
    /**
     * Callback при добавлении новых треков
     * @param {number} newTracksCount - Количество добавленных треков
     * @param {number} totalNewTracks - Общее количество новых треков в плейлисте
     */
    onTracksAdded(newTracksCount, totalNewTracks) {
        // Показываем toast-уведомление
        this.showToast(`Добавлено ${newTracksCount} новых треков`);
        
        // Синхронизируем revision с updater (он уже обновлен в checkForUpdates)
        if (this.playlistUpdater) {
            this.currentRevision = this.playlistUpdater.currentRevision;
        }
    }
    
    /**
     * Показать toast-уведомление
     * @param {string} message - Текст уведомления
     * @param {number} duration - Длительность показа в миллисекундах (по умолчанию 3000)
     */
    showToast(message, duration = 3000) {
        const toast = document.getElementById('toast');
        if (!toast) return;
        
        toast.textContent = message;
        toast.classList.remove('hidden');
        toast.classList.add('show');
        
        // Скрываем через указанное время
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.classList.add('hidden');
            }, 300); // Ждем завершения анимации
        }, duration);
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
                btn.title = 'Пауза';
            } else {
                btn.classList.remove('playing');
                btn.textContent = '▶';
                btn.title = 'Воспроизвести';
            }
        }
    }

    async playPrevious() {
        if (this.isShuffled && this.shuffledIndices.length > 0) {
            // Находим текущий трек в перемешанном списке
            const currentOriginalIndex = this.currentTrackIndex;
            const shuffledIndex = this.shuffledIndices.indexOf(currentOriginalIndex);
            
            if (shuffledIndex > 0) {
                // Переходим к предыдущему треку в перемешанном списке
                const prevOriginalIndex = this.shuffledIndices[shuffledIndex - 1];
                this.currentTrackIndex = prevOriginalIndex;
                await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            } else if (this.repeatMode === 'all') {
                // Если включен повтор, переходим к последнему треку
                const lastOriginalIndex = this.shuffledIndices[this.shuffledIndices.length - 1];
                this.currentTrackIndex = lastOriginalIndex;
                await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            }
        } else {
            // Обычный режим
            if (this.currentTrackIndex > 0) {
                this.currentTrackIndex--;
                await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            } else if (this.repeatMode === 'all') {
                // Если включен повтор, переходим к последнему треку
                this.currentTrackIndex = this.currentTracks.length - 1;
                await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            }
        }
    }

    async playNext() {
        if (this.isShuffled && this.shuffledIndices.length > 0) {
            // Находим текущий трек в перемешанном списке
            const currentOriginalIndex = this.currentTrackIndex;
            const shuffledIndex = this.shuffledIndices.indexOf(currentOriginalIndex);
            
            if (shuffledIndex < this.shuffledIndices.length - 1) {
                // Переходим к следующему треку в перемешанном списке
                const nextOriginalIndex = this.shuffledIndices[shuffledIndex + 1];
                this.currentTrackIndex = nextOriginalIndex;
                await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            } else if (this.repeatMode === 'all') {
                // Если включен повтор, переходим к первому треку
                const firstOriginalIndex = this.shuffledIndices[0];
                this.currentTrackIndex = firstOriginalIndex;
                await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            } else {
                // Проверяем обновления плейлиста
                await this.checkForMoreTracks();
            }
        } else {
            // Обычный режим
            if (this.currentTrackIndex < this.currentTracks.length - 1) {
                this.currentTrackIndex++;
                await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            } else if (this.repeatMode === 'all') {
                // Если включен повтор, переходим к первому треку
                this.currentTrackIndex = 0;
                await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            } else {
                // Проверяем обновления плейлиста
                await this.checkForMoreTracks();
            }
        }
    }
    
    /**
     * Проверить наличие новых треков в плейлисте
     */
    async checkForMoreTracks() {
        // Если достигли конца очереди, проверяем обновления вручную
        if (this.playlistUpdater) {
            await this.playlistUpdater.checkForUpdates();
            // Если после проверки появились новые треки, переходим к следующему
            if (this.currentTrackIndex < this.currentTracks.length - 1) {
                this.currentTrackIndex++;
                await this.loadTrack(this.currentTracks[this.currentTrackIndex]);
            }
        }
    }

    async loadTrack(track) {
        if (!track) {
            return;
        }
        
        // Обновляем UI с информацией о треке
        const trackTitle = document.getElementById('track-title');
        const trackArtist = document.getElementById('track-artist');
        const trackCover = document.getElementById('track-cover');
        const trackCoverPlaceholder = document.querySelector('.track-cover-placeholder');
        
        if (trackTitle) trackTitle.textContent = track.title || '-';
        // Безопасная обработка артистов (может быть массивом или строкой)
        const artistsText = Array.isArray(track.artists) 
            ? track.artists.join(', ') 
            : (track.artists || '-');
        if (trackArtist) trackArtist.textContent = artistsText;
        
        // Обновляем обложку трека
        if (trackCover && trackCoverPlaceholder) {
            if (track.cover_url) {
                // Устанавливаем обработчики до изменения src
                trackCover.onload = () => {
                    trackCover.style.display = 'block';
                    trackCoverPlaceholder.style.display = 'none';
                };
                trackCover.onerror = () => {
                    trackCover.style.display = 'none';
                    trackCoverPlaceholder.style.display = 'flex';
                };
                // Устанавливаем src - это запустит загрузку
                trackCover.src = track.cover_url;
                // Если изображение уже загружено (из кеша), onload может не сработать
                if (trackCover.complete && trackCover.naturalWidth > 0) {
                    trackCover.style.display = 'block';
                    trackCoverPlaceholder.style.display = 'none';
                } else {
                    // Показываем placeholder пока загружается
                    trackCover.style.display = 'none';
                    trackCoverPlaceholder.style.display = 'flex';
                }
            } else {
                trackCover.src = '';
                trackCover.style.display = 'none';
                trackCoverPlaceholder.style.display = 'flex';
            }
        }
        
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

