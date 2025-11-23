#!/bin/bash

# Скрипт для проверки статуса бота
# Использование: ./check_bot_status.sh

echo "=== Проверка статуса бота ==="
echo ""

# 1. Проверка локальных процессов Python
echo "1. Проверка локальных процессов Python:"
LOCAL_PYTHON=$(ps aux | grep -E "python.*bot\.py|bot\.py" | grep -v grep)
if [ -z "$LOCAL_PYTHON" ]; then
    echo "   ❌ Бот не запущен локально (через Python)"
else
    echo "   ✅ Найден локальный процесс:"
    echo "$LOCAL_PYTHON" | sed 's/^/      /'
fi
echo ""

# 2. Проверка Docker контейнеров
echo "2. Проверка Docker контейнеров:"
if command -v docker &> /dev/null; then
    DOCKER_BOT=$(docker ps -a | grep -i "ym_bot\|bot" | grep -v grep)
    if [ -z "$DOCKER_BOT" ]; then
        echo "   ❌ Бот не запущен в Docker"
    else
        echo "   ✅ Найден Docker контейнер:"
        echo "$DOCKER_BOT" | sed 's/^/      /'
        echo ""
        echo "   Статус контейнера:"
        docker ps -a --filter "name=ym_bot" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | sed 's/^/      /'
    fi
else
    echo "   ⚠️  Docker не установлен или не доступен"
fi
echo ""

# 3. Проверка systemd сервисов (локально)
echo "3. Проверка systemd сервисов (локально):"
if systemctl list-units --type=service --all 2>/dev/null | grep -qi "liza-bot\|ym-bot\|bot"; then
    echo "   ✅ Найден systemd сервис бота:"
    systemctl list-units --type=service --all 2>/dev/null | grep -i "liza-bot\|ym-bot\|bot" | sed 's/^/      /'
    echo ""
    echo "   Статус сервиса:"
    systemctl status liza-bot.service 2>/dev/null | head -5 | sed 's/^/      /' || echo "      Сервис не найден"
else
    echo "   ❌ Systemd сервис бота не найден локально"
fi
echo ""

# 4. Проверка файла логов
echo "4. Проверка файла логов:"
if [ -f "bot.log" ]; then
    echo "   ✅ Файл bot.log существует"
    echo "   Последние строки лога:"
    tail -5 bot.log | sed 's/^/      /'
    echo ""
    echo "   Размер файла: $(ls -lh bot.log | awk '{print $5}')"
    echo "   Последнее изменение: $(stat -f "%Sm" bot.log 2>/dev/null || stat -c "%y" bot.log 2>/dev/null)"
else
    echo "   ❌ Файл bot.log не найден"
fi
echo ""

# 5. Проверка активных сетевых соединений
echo "5. Проверка активных сетевых соединений Python:"
PYTHON_CONNECTIONS=$(lsof -i -P 2>/dev/null | grep -i python | grep -v grep)
if [ -z "$PYTHON_CONNECTIONS" ]; then
    echo "   ❌ Нет активных сетевых соединений Python"
else
    echo "   ✅ Найдены активные соединения:"
    echo "$PYTHON_CONNECTIONS" | sed 's/^/      /'
fi
echo ""

# 6. Рекомендации
echo "=== Рекомендации ==="
echo ""
if [ -z "$LOCAL_PYTHON" ] && [ -z "$DOCKER_BOT" ]; then
    echo "Бот не запущен локально."
    echo ""
    echo "Если бот должен работать на удаленном сервере:"
    echo "  1. Подключитесь к серверу по SSH"
    echo "  2. Выполните: sudo systemctl status liza-bot.service"
    echo "  3. Или проверьте Docker: docker ps | grep bot"
    echo ""
    echo "Если бот должен работать локально:"
    echo "  - Запустите: ./run.sh (в терминале)"
    echo "  - Или в фоне: ./run_background.sh"
    echo "  - Или через Docker: docker compose up -d bot"
fi

