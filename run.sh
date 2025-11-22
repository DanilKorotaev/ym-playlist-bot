#!/bin/bash

# Скрипт для запуска бота
# Использование: ./run.sh

cd "$(dirname "$0")"

# Активируем виртуальное окружение
source venv/bin/activate

# Запускаем бота
python bot_v2.py

