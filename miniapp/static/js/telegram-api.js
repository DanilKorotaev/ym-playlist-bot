/**
 * Обертка для Telegram Web App API
 * Упрощает работу с Telegram Web App SDK
 */
class TelegramAPI {
    constructor() {
        this.webApp = null;
        this.initData = null;
        this.isReady = false;
        
        // Ждем загрузки Telegram Web App API
        this._waitForTelegramAPI();
    }

    /**
     * Ожидание загрузки Telegram Web App API
     * @private
     */
    _waitForTelegramAPI() {
        // Проверяем, доступен ли API
        if (window.Telegram && window.Telegram.WebApp) {
            this._initWebApp();
        } else {
            // Ждем загрузки скрипта
            const checkInterval = setInterval(() => {
                if (window.Telegram && window.Telegram.WebApp) {
                    clearInterval(checkInterval);
                    this._initWebApp();
                }
            }, 100);
            
            // Таймаут через 5 секунд
            setTimeout(() => {
                clearInterval(checkInterval);
            }, 5000);
        }
    }

    /**
     * Инициализация Web App
     * @private
     */
    _initWebApp() {
        this.webApp = window.Telegram.WebApp;
        
        if (!this.webApp) {
            console.error('Telegram Web App API не доступен');
            return;
        }

        // Инициализируем Web App
        this.webApp.ready();
        
        // Расширяем Web App на весь экран
        this.webApp.expand();
        
        // Устанавливаем цвет фона (опционально)
        this.webApp.setHeaderColor('#3390ec');
        this.webApp.setBackgroundColor('#ffffff');
        
        // Ждем немного, чтобы initData успел загрузиться
        // Иногда initData доступен не сразу после ready()
        setTimeout(() => {
            // Сохраняем initData (пробуем несколько раз)
            this.initData = this.webApp.initData || '';
            
            // Если все еще пустой, пробуем еще раз через небольшую задержку
            if (!this.initData) {
                setTimeout(() => {
                    this.initData = this.webApp.initData || '';
                    this._finalizeInit();
                }, 200);
            } else {
                this._finalizeInit();
            }
        }, 100);
    }
    
    /**
     * Завершение инициализации
     * @private
     */
    _finalizeInit() {
        this.isReady = true;
        
        // Проверяем режим разработки через query параметр (только если initData пустой)
        if (!this.initData) {
            const urlParams = new URLSearchParams(window.location.search);
            const devMode = urlParams.get('dev') === 'true';
            const devUserId = urlParams.get('user_id');
            
            if (devMode && devUserId) {
                // В режиме разработки создаем моковый initData
                // Это не будет работать с реальным API, но позволит тестировать UI
                this.initData = `user=%7B%22id%22%3A${devUserId}%7D&auth_date=${Math.floor(Date.now() / 1000)}&hash=dev_mode`;
            }
        }
    }

    /**
     * Получить данные инициализации от Telegram
     * @returns {string} initData строка
     */
    getInitData() {
        // Пробуем получить из сохраненного значения
        if (this.initData) {
            return this.initData;
        }
        
        // Пробуем получить из webApp
        if (this.webApp) {
            this.initData = this.webApp.initData || '';
            if (this.initData) {
                return this.initData;
            }
        }
        
        // Пробуем получить напрямую из window
        if (window.Telegram?.WebApp?.initData) {
            this.initData = window.Telegram.WebApp.initData;
            if (this.initData) {
                return this.initData;
            }
        }
        
        // Пробуем получить из URL параметров (для некоторых случаев)
        // В Telegram Desktop initData может быть в hash или query параметрах
        const urlParams = new URLSearchParams(window.location.search);
        const hashParams = new URLSearchParams(window.location.hash.substring(1));
        
        // Проверяем query параметры
        const queryInitData = urlParams.get('tgWebAppData') || urlParams.get('initData');
        if (queryInitData) {
            this.initData = queryInitData;
            return this.initData;
        }
        
        // Проверяем hash параметры
        const hashInitData = hashParams.get('tgWebAppData') || hashParams.get('initData');
        if (hashInitData) {
            this.initData = hashInitData;
            return this.initData;
        }
        
        // Пробуем извлечь из всего hash (может быть закодирован)
        const hash = window.location.hash;
        if (hash && hash.includes('tgWebAppData=')) {
            const match = hash.match(/tgWebAppData=([^&]+)/);
            if (match && match[1]) {
                this.initData = decodeURIComponent(match[1]);
                return this.initData;
            }
        }
        
        return '';
    }

    /**
     * Получить информацию о пользователе
     * @returns {Object|null} Объект с данными пользователя или null
     */
    getUser() {
        return this.webApp?.initDataUnsafe?.user || null;
    }

    /**
     * Отправить данные боту через sendData
     * @param {Object} data - Данные для отправки
     */
    sendData(data) {
        if (!this.webApp) {
            console.error('Telegram Web App API не доступен');
            return;
        }

        try {
            const jsonData = JSON.stringify(data);
            this.webApp.sendData(jsonData);
        } catch (error) {
            console.error('Ошибка при отправке данных:', error);
        }
    }

    /**
     * Показать главную кнопку
     * @param {Object} options - Опции кнопки
     */
    showMainButton(options = {}) {
        if (!this.webApp) return;

        const {
            text = 'Открыть',
            color = '#3390ec',
            textColor = '#ffffff',
            isActive = true,
            isVisible = true,
            onClick = null
        } = options;

        this.webApp.MainButton.setText(text);
        this.webApp.MainButton.setParams({
            color: color,
            text_color: textColor,
            is_active: isActive,
            is_visible: isVisible
        });

        if (onClick) {
            this.webApp.MainButton.onClick(onClick);
        }
    }

    /**
     * Скрыть главную кнопку
     */
    hideMainButton() {
        if (!this.webApp) return;
        this.webApp.MainButton.hide();
    }

    /**
     * Показать уведомление
     * @param {string} message - Текст уведомления
     */
    showAlert(message) {
        if (!this.webApp) {
            alert(message);
            return;
        }
        this.webApp.showAlert(message);
    }

    /**
     * Показать подтверждение
     * @param {string} message - Текст подтверждения
     * @returns {Promise<boolean>} Результат подтверждения
     */
    showConfirm(message) {
        if (!this.webApp) {
            return Promise.resolve(confirm(message));
        }
        return new Promise((resolve) => {
            this.webApp.showConfirm(message, (confirmed) => {
                resolve(confirmed);
            });
        });
    }

    /**
     * Закрыть Mini App
     */
    close() {
        if (!this.webApp) return;
        this.webApp.close();
    }

    /**
     * Получить версию платформы
     * @returns {string} Версия платформы
     */
    getPlatform() {
        return this.webApp?.platform || 'unknown';
    }

    /**
     * Проверить, доступен ли Telegram Web App API
     * @returns {boolean}
     */
    isAvailable() {
        return !!this.webApp && this.isReady;
    }

    /**
     * Получить базовый URL для API запросов
     * @returns {string} Базовый URL API
     */
    getApiBaseUrl() {
        // В продакшене это будет настраиваться через переменные окружения
        // Для разработки используем относительный путь или текущий домен
        const protocol = window.location.protocol;
        const host = window.location.host;
        
        // Если мы на том же домене, используем относительный путь
        // Иначе используем полный URL (для разработки через туннель)
        return `${protocol}//${host}/api`;
    }

    /**
     * Выполнить запрос к REST API с авторизацией через initData
     * @param {string} endpoint - Эндпоинт API (например, '/playlists')
     * @param {Object} options - Опции для fetch (method, body, etc.)
     * @returns {Promise<Response>} Ответ от сервера
     */
    async apiRequest(endpoint, options = {}) {
        // Ждем готовности API (максимум 5 секунд)
        let attempts = 0;
        while (!this.isReady && attempts < 50) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        
        if (!this.isReady) {
            const errorMsg = 'Telegram Web App API не загрузился. ' +
                'Убедитесь, что:\n' +
                '1. Вы открыли приложение через кнопку "🎵 Открыть плеер" в Telegram\n' +
                '2. Используется HTTPS (не HTTP)\n' +
                '3. Скрипт telegram-web-app.js загружается правильно';
            throw new Error(errorMsg);
        }
        
        const baseUrl = this.getApiBaseUrl();
        const url = `${baseUrl}${endpoint}`;
        
        // Получаем initData для авторизации
        const initData = this.getInitData();
        if (!initData) {
            // Проверяем, открыто ли через Telegram
            const isTelegram = !!window.Telegram?.WebApp;
            
            if (!isTelegram) {
                throw new Error(
                    'Приложение открыто не через Telegram.\n\n' +
                    'Для работы Mini App необходимо:\n' +
                    '1. Открыть бота в Telegram\n' +
                    '2. Нажать кнопку "🎵 Открыть плеер"\n' +
                    '3. Не открывать ссылку напрямую в браузере'
                );
            }
            
            throw new Error(
                'Telegram initData не доступен.\n\n' +
                'Попробуйте:\n' +
                '1. Закрыть и снова открыть Mini App через кнопку\n' +
                '2. Обновить Telegram до последней версии\n' +
                '3. Использовать inline-кнопку вместо кнопки в меню'
            );
        }
        
        // Устанавливаем заголовки
        const headers = {
            'Content-Type': 'application/json',
            'X-Telegram-Init-Data': initData,
            ...options.headers
        };
        
        // Выполняем запрос
        const response = await fetch(url, {
            ...options,
            headers
        });
        
        // Проверяем статус ответа
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
        }
        
        return response;
    }

    /**
     * Выполнить GET запрос к API
     * @param {string} endpoint - Эндпоинт API
     * @returns {Promise<Object>} JSON ответ
     */
    async apiGet(endpoint) {
        const response = await this.apiRequest(endpoint, {
            method: 'GET'
        });
        return await response.json();
    }

    /**
     * Выполнить POST запрос к API
     * @param {string} endpoint - Эндпоинт API
     * @param {Object} data - Данные для отправки
     * @returns {Promise<Object>} JSON ответ
     */
    async apiPost(endpoint, data) {
        const response = await this.apiRequest(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
        return await response.json();
    }
}

// Создаем глобальный экземпляр
window.telegramAPI = new TelegramAPI();


