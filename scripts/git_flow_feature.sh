#!/bin/bash

# Скрипт для работы с feature-ветками в Git Flow
# Использование:
#   ./scripts/git_flow_feature.sh start название-фичи
#   ./scripts/git_flow_feature.sh finish название-фичи

set -e

ACTION=$1
FEATURE_NAME=$2

if [ -z "$ACTION" ] || [ -z "$FEATURE_NAME" ]; then
    echo "❌ Ошибка: не указаны параметры"
    echo ""
    echo "Использование:"
    echo "  $0 start <название-фичи>   - создать feature-ветку"
    echo "  $0 finish <название-фичи>  - завершить feature-ветку"
    echo ""
    echo "Примеры:"
    echo "  $0 start playlist-stats"
    echo "  $0 finish playlist-stats"
    exit 1
fi

FEATURE_BRANCH="feature/$FEATURE_NAME"

case "$ACTION" in
    start)
        echo "🚀 Создание feature-ветки: $FEATURE_BRANCH"
        echo ""
        
        # Проверка, что мы в репозитории
        if ! git rev-parse --git-dir > /dev/null 2>&1; then
            echo "❌ Ошибка: не найден git репозиторий"
            exit 1
        fi
        
        # Проверка, что ветка не существует
        if git show-ref --verify --quiet refs/heads/$FEATURE_BRANCH; then
            echo "❌ Ошибка: ветка $FEATURE_BRANCH уже существует"
            exit 1
        fi
        
        if git show-ref --verify --quiet refs/remotes/origin/$FEATURE_BRANCH; then
            echo "❌ Ошибка: удаленная ветка $FEATURE_BRANCH уже существует"
            exit 1
        fi
        
        # Проверка, что нет незакоммиченных изменений
        if ! git diff-index --quiet HEAD --; then
            echo "⚠️  Предупреждение: есть незакоммиченные изменения"
            echo "   Сохраните или отмените изменения перед созданием ветки"
            read -p "Продолжить? (y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
        
        # Обновить develop
        echo "📥 Обновление develop..."
        git checkout develop
        git pull origin develop
        
        # Создать feature-ветку
        echo "🌿 Создание ветки $FEATURE_BRANCH..."
        git checkout -b $FEATURE_BRANCH develop
        
        echo ""
        echo "✅ Feature-ветка $FEATURE_BRANCH создана!"
        echo ""
        echo "📝 Следующие шаги:"
        echo "   1. Внесите изменения"
        echo "   2. Коммитьте изменения: git commit -m 'feat: описание'"
        echo "   3. Отправьте ветку: git push origin $FEATURE_BRANCH"
        echo "   4. После завершения: $0 finish $FEATURE_NAME"
        ;;
        
    finish)
        echo "🏁 Завершение feature-ветки: $FEATURE_BRANCH"
        echo ""
        
        # Проверка, что мы в репозитории
        if ! git rev-parse --git-dir > /dev/null 2>&1; then
            echo "❌ Ошибка: не найден git репозиторий"
            exit 1
        fi
        
        # Проверка, что ветка существует
        if ! git show-ref --verify --quiet refs/heads/$FEATURE_BRANCH; then
            echo "❌ Ошибка: локальная ветка $FEATURE_BRANCH не найдена"
            echo "   Убедитесь, что вы находитесь в нужной ветке или создайте её"
            exit 1
        fi
        
        # Проверка, что нет незакоммиченных изменений
        if ! git diff-index --quiet HEAD --; then
            echo "⚠️  Предупреждение: есть незакоммиченные изменения"
            echo "   Сохраните или отмените изменения перед завершением ветки"
            read -p "Продолжить? (y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
        
        # Переключиться на feature-ветку
        git checkout $FEATURE_BRANCH
        
        # Обновить develop
        echo "📥 Обновление develop..."
        git checkout develop
        git pull origin develop
        
        # Мерж feature-ветки
        echo "🔀 Мерж $FEATURE_BRANCH в develop..."
        git merge --no-ff $FEATURE_BRANCH -m "Merge branch '$FEATURE_BRANCH' into develop"
        
        # Отправить изменения
        echo "📤 Отправка изменений в develop..."
        git push origin develop
        
        # Удалить локальную ветку
        echo "🗑️  Удаление локальной ветки $FEATURE_BRANCH..."
        git branch -d $FEATURE_BRANCH
        
        # Удалить удаленную ветку (если существует)
        if git show-ref --verify --quiet refs/remotes/origin/$FEATURE_BRANCH; then
            echo "🗑️  Удаление удаленной ветки $FEATURE_BRANCH..."
            git push origin --delete $FEATURE_BRANCH
        fi
        
        echo ""
        echo "✅ Feature-ветка $FEATURE_BRANCH успешно завершена!"
        echo "   Изменения мержены в develop"
        ;;
        
    *)
        echo "❌ Ошибка: неизвестное действие '$ACTION'"
        echo ""
        echo "Использование:"
        echo "  $0 start <название-фичи>   - создать feature-ветку"
        echo "  $0 finish <название-фичи>  - завершить feature-ветку"
        exit 1
        ;;
esac

