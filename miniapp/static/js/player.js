/**
 * Класс для управления воспроизведением аудио в Mini App
 * Использует HTML5 Audio API и Fetch API для стриминга
 */
class Player {
    constructor() {
        this.audio = null;
        this.currentTrack = null;
        this.currentUrl = null;
        this.isPlaying = false;
        this.isLoading = false;
        this.blobUrl = null;
        
        // Callbacks
        this.onPlay = null;
        this.onPause = null;
        this.onTimeUpdate = null;
        this.onEnded = null;
        this.onError = null;
        this.onLoadStart = null;
        this.onLoadedMetadata = null;
        
        this.init();
    }
    
    init() {
        // Создаем HTML5 Audio элемент
        this.audio = new Audio();
        
        // Настраиваем обработчики событий
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        if (!this.audio) return;
        
        // События воспроизведения
        this.audio.addEventListener('play', () => {
            this.isPlaying = true;
            if (this.onPlay) this.onPlay();
        });
        
        this.audio.addEventListener('pause', () => {
            this.isPlaying = false;
            if (this.onPause) this.onPause();
        });
        
        // Обновление времени воспроизведения
        this.audio.addEventListener('timeupdate', () => {
            if (this.onTimeUpdate) {
                this.onTimeUpdate({
                    currentTime: this.audio.currentTime,
                    duration: this.audio.duration,
                    progress: this.audio.duration > 0 
                        ? (this.audio.currentTime / this.audio.duration) * 100 
                        : 0
                });
            }
        });
        
        // Трек закончился
        this.audio.addEventListener('ended', () => {
            this.isPlaying = false;
            if (this.onEnded) this.onEnded();
        });
        
        // Ошибки
        this.audio.addEventListener('error', (e) => {
            console.error('Ошибка воспроизведения:', e);
            this.isPlaying = false;
            if (this.onError) {
                this.onError({
                    message: 'Ошибка воспроизведения трека',
                    error: e
                });
            }
        });
        
        // Начало загрузки
        this.audio.addEventListener('loadstart', () => {
            this.isLoading = true;
            if (this.onLoadStart) this.onLoadStart();
        });
        
        // Метаданные загружены (длительность доступна)
        this.audio.addEventListener('loadedmetadata', () => {
            this.isLoading = false;
            if (this.onLoadedMetadata) {
                this.onLoadedMetadata({
                    duration: this.audio.duration
                });
            }
        });
        
        // Загрузка завершена
        this.audio.addEventListener('canplay', () => {
            this.isLoading = false;
            if (this.onLoadedMetadata) {
                this.onLoadedMetadata({
                    duration: this.audio.duration
                });
            }
        });
        
        // Загрузка завершена и можно воспроизводить
        this.audio.addEventListener('canplaythrough', () => {
            this.isLoading = false;
        });
    }
    
    /**
     * Загрузить трек для воспроизведения
     * @param {string} url - URL трека для стриминга
     * @param {Object} trackInfo - Информация о треке (title, artists, etc.)
     * @returns {Promise<void>}
     */
    async loadTrack(url, trackInfo = {}) {
        try {
            // Останавливаем текущее воспроизведение
            this.stop();
            
            // Очищаем предыдущий Blob URL
            this.cleanup();
            
            this.currentTrack = trackInfo;
            this.currentUrl = url;
            this.isLoading = true;
            
            // Загружаем трек через Fetch API с Range Requests
            const blobUrl = await this.loadTrackAsBlob(url);
            
            if (!blobUrl) {
                throw new Error('Не удалось загрузить трек');
            }
            
            this.blobUrl = blobUrl;
            
            // Устанавливаем источник для Audio элемента
            this.audio.src = blobUrl;
            
            // Предзагрузка метаданных
            await this.audio.load();
            
        } catch (error) {
            console.error('Ошибка при загрузке трека:', error);
            this.isLoading = false;
            if (this.onError) {
                this.onError({
                    message: 'Не удалось загрузить трек',
                    error: error
                });
            }
            throw error;
        }
    }
    
    /**
     * Загрузить трек через Fetch API и создать Blob URL
     * Использует Range Requests для оптимизации загрузки
     * @param {string} url - URL трека
     * @returns {Promise<string>} Blob URL
     */
    async loadTrackAsBlob(url) {
        try {
            // Загружаем первые байты для быстрого старта воспроизведения
            // Первый 1MB обычно достаточно для начала воспроизведения
            const initialChunkSize = 1024 * 1024; // 1MB
            
            const response = await fetch(url, {
                headers: {
                    'Range': `bytes=0-${initialChunkSize}`
                }
            });
            
            if (!response.ok && response.status !== 206) {
                // Если Range не поддерживается, загружаем полностью
                const fullResponse = await fetch(url);
                if (!fullResponse.ok) {
                    throw new Error(`HTTP ${fullResponse.status}: ${fullResponse.statusText}`);
                }
                const blob = await fullResponse.blob();
                return URL.createObjectURL(new Blob([blob], { type: 'audio/mpeg' }));
            }
            
            // Получаем Blob из ответа
            const blob = await response.blob();
            
            // Создаем Blob URL с правильным Content-Type
            // Важно: указываем audio/mpeg для правильного воспроизведения
            const blobUrl = URL.createObjectURL(
                new Blob([blob], { type: 'audio/mpeg' })
            );
            
            return blobUrl;
            
        } catch (error) {
            console.error('Ошибка при загрузке трека через Fetch:', error);
            
            // Fallback: пробуем использовать URL напрямую
            // (некоторые браузеры могут воспроизводить напрямую)
            return url;
        }
    }
    
    /**
     * Воспроизвести трек
     */
    async play() {
        if (!this.audio || !this.audio.src) {
            return;
        }
        
        try {
            await this.audio.play();
        } catch (error) {
            console.error('Ошибка при воспроизведении:', error);
            if (this.onError) {
                this.onError({
                    message: 'Не удалось начать воспроизведение',
                    error: error
                });
            }
        }
    }
    
    /**
     * Приостановить воспроизведение
     */
    pause() {
        if (this.audio && this.isPlaying) {
            this.audio.pause();
        }
    }
    
    /**
     * Переключить воспроизведение (play/pause)
     */
    async togglePlayPause() {
        if (this.isPlaying) {
            this.pause();
        } else {
            await this.play();
        }
    }
    
    /**
     * Остановить воспроизведение
     */
    stop() {
        if (this.audio) {
            this.audio.pause();
            this.audio.currentTime = 0;
        }
        this.isPlaying = false;
    }
    
    /**
     * Перемотать на указанное время
     * @param {number} time - Время в секундах
     */
    seek(time) {
        if (this.audio && !isNaN(time)) {
            this.audio.currentTime = Math.max(0, Math.min(time, this.audio.duration || 0));
        }
    }
    
    /**
     * Установить громкость
     * @param {number} volume - Громкость от 0 до 1
     */
    setVolume(volume) {
        if (this.audio) {
            this.audio.volume = Math.max(0, Math.min(1, volume));
        }
    }
    
    /**
     * Получить текущее время воспроизведения
     * @returns {number} Время в секундах
     */
    getCurrentTime() {
        return this.audio ? this.audio.currentTime : 0;
    }
    
    /**
     * Получить длительность трека
     * @returns {number} Длительность в секундах
     */
    getDuration() {
        return this.audio ? this.audio.duration : 0;
    }
    
    /**
     * Получить информацию о текущем треке
     * @returns {Object|null}
     */
    getCurrentTrack() {
        return this.currentTrack;
    }
    
    /**
     * Проверить, воспроизводится ли трек
     * @returns {boolean}
     */
    getIsPlaying() {
        return this.isPlaying;
    }
    
    /**
     * Проверить, загружается ли трек
     * @returns {boolean}
     */
    getIsLoading() {
        return this.isLoading;
    }
    
    /**
     * Очистить ресурсы (Blob URL)
     */
    cleanup() {
        if (this.blobUrl) {
            try {
                URL.revokeObjectURL(this.blobUrl);
            } catch (e) {
                // Игнорируем ошибки при очистке Blob URL
            }
            this.blobUrl = null;
        }
    }
    
    /**
     * Уничтожить плеер и очистить ресурсы
     */
    destroy() {
        this.stop();
        this.cleanup();
        
        if (this.audio) {
            this.audio.src = '';
            this.audio = null;
        }
        
        this.currentTrack = null;
        this.currentUrl = null;
    }
}

