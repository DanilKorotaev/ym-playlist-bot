#!/bin/bash

# Скрипт для запуска бота в фоне
# Использование: ./run_background.sh

cd "$(dirname "$0")"

# Активируем виртуальное окружение
source venv/bin/activate

# Запускаем бота в фоне с логированием
nohup python bot.py > bot.log 2>&1 &

echo "Бот запущен в фоне. PID: $!"
echo "Логи сохраняются в bot.log"
echo "Для просмотра логов: tail -f bot.log"
echo "Для остановки: pkill -f 'python.*bot.py'"

