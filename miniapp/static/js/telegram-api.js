/**
 * Обертка для Telegram Web App API
 * Упрощает работу с Telegram Web App SDK
 */
class TelegramAPI {
    constructor() {
        this.webApp = window.Telegram?.WebApp;
        
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
    }

    /**
     * Получить данные инициализации от Telegram
     * @returns {string} initData строка
     */
    getInitData() {
        return this.webApp?.initData || '';
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
        return !!this.webApp;
    }
}

// Создаем глобальный экземпляр
window.telegramAPI = new TelegramAPI();

