#!/bin/bash

# Скрипт для работы с hotfix-ветками в Git Flow
# Использование:
#   ./scripts/git_flow_hotfix.sh start 4.1.1
#   ./scripts/git_flow_hotfix.sh finish 4.1.1

set -e

ACTION=$1
VERSION=$2

if [ -z "$ACTION" ] || [ -z "$VERSION" ]; then
    echo "❌ Ошибка: не указаны параметры"
    echo ""
    echo "Использование:"
    echo "  $0 start <version>   - создать hotfix-ветку"
    echo "  $0 finish <version>  - завершить hotfix-ветку"
    echo ""
    echo "Примеры:"
    echo "  $0 start 4.1.1"
    echo "  $0 finish 4.1.1"
    exit 1
fi

# Проверка формата версии (X.Y.Z)
if ! [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "❌ Ошибка: неверный формат версии"
    echo "Используйте формат X.Y.Z (например: 4.1.1)"
    exit 1
fi

HOTFIX_BRANCH="hotfix/v$VERSION"
TAG="v$VERSION"

case "$ACTION" in
    start)
        echo "🚀 Создание hotfix-ветки: $HOTFIX_BRANCH"
        echo ""
        
        # Проверка, что мы в репозитории
        if ! git rev-parse --git-dir > /dev/null 2>&1; then
            echo "❌ Ошибка: не найден git репозиторий"
            exit 1
        fi
        
        # Проверка, что ветка не существует
        if git show-ref --verify --quiet refs/heads/$HOTFIX_BRANCH; then
            echo "❌ Ошибка: ветка $HOTFIX_BRANCH уже существует"
            exit 1
        fi
        
        if git show-ref --verify --quiet refs/remotes/origin/$HOTFIX_BRANCH; then
            echo "❌ Ошибка: удаленная ветка $HOTFIX_BRANCH уже существует"
            exit 1
        fi
        
        # Проверка, что тег не существует
        if git rev-parse "$TAG" >/dev/null 2>&1; then
            echo "❌ Ошибка: тег $TAG уже существует"
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
        
        # Обновить main
        echo "📥 Обновление main..."
        git checkout main
        git pull origin main
        
        # Создать hotfix-ветку
        echo "🌿 Создание ветки $HOTFIX_BRANCH..."
        git checkout -b $HOTFIX_BRANCH main
        
        echo ""
        echo "✅ Hotfix-ветка $HOTFIX_BRANCH создана!"
        echo ""
        echo "📝 Следующие шаги:"
        echo "   1. Внесите исправления"
        echo "   2. Обновите CHANGELOG.md (добавьте запись о hotfix)"
        echo "   3. Обновите README.md (версия, если нужно)"
        echo "   4. Закоммитьте изменения:"
        echo "      git add ."
        echo "      git commit -m 'fix: описание исправления'"
        echo "      git push origin $HOTFIX_BRANCH"
        echo "   5. После завершения: $0 finish $VERSION"
        ;;
        
    finish)
        echo "🏁 Завершение hotfix-ветки: $HOTFIX_BRANCH"
        echo ""
        
        # Проверка, что мы в репозитории
        if ! git rev-parse --git-dir > /dev/null 2>&1; then
            echo "❌ Ошибка: не найден git репозиторий"
            exit 1
        fi
        
        # Проверка, что ветка существует
        if ! git show-ref --verify --quiet refs/heads/$HOTFIX_BRANCH; then
            echo "❌ Ошибка: локальная ветка $HOTFIX_BRANCH не найдена"
            echo "   Убедитесь, что вы находитесь в нужной ветке или создайте её"
            exit 1
        fi
        
        # Проверка, что тег не существует
        if git rev-parse "$TAG" >/dev/null 2>&1; then
            echo "❌ Ошибка: тег $TAG уже существует"
            exit 1
        fi
        
        # Переключиться на hotfix-ветку
        git checkout $HOTFIX_BRANCH
        
        # Обновить main
        echo "📥 Обновление main..."
        git checkout main
        git pull origin main
        
        # Мерж hotfix-ветки в main
        echo "🔀 Мерж $HOTFIX_BRANCH в main..."
        git merge --no-ff $HOTFIX_BRANCH -m "Merge branch '$HOTFIX_BRANCH' into main"
        
        # Создать тег
        echo "📌 Создание тега $TAG..."
        git tag -a "$TAG" -m "Hotfix version $VERSION"
        
        # Отправить main и тег
        echo "📤 Отправка main и тега..."
        git push origin main
        git push origin "$TAG"
        
        # Мерж hotfix-ветки в develop
        echo "🔀 Мерж $HOTFIX_BRANCH в develop..."
        git checkout develop
        git pull origin develop
        git merge --no-ff $HOTFIX_BRANCH -m "Merge branch '$HOTFIX_BRANCH' into develop"
        git push origin develop
        
        # Удалить локальную ветку
        echo "🗑️  Удаление локальной ветки $HOTFIX_BRANCH..."
        git branch -d $HOTFIX_BRANCH
        
        # Удалить удаленную ветку (если существует)
        if git show-ref --verify --quiet refs/remotes/origin/$HOTFIX_BRANCH; then
            echo "🗑️  Удаление удаленной ветки $HOTFIX_BRANCH..."
            git push origin --delete $HOTFIX_BRANCH
        fi
        
        echo ""
        echo "✅ Hotfix-ветка $HOTFIX_BRANCH успешно завершена!"
        echo "   Тег $TAG создан и отправлен"
        echo ""
        echo "📝 Следующие шаги:"
        echo "   1. Откройте GitHub: https://github.com/$(git config --get remote.origin.url | sed 's/.*github.com[:/]\(.*\)\.git/\1/')/releases/new"
        echo "   2. Выберите тег $TAG"
        echo "   3. Скопируйте описание из CHANGELOG.md для версии $VERSION"
        echo "   4. Нажмите 'Publish release'"
        echo ""
        echo "🔄 Автоматический деплой запустится при создании тега"
        ;;
        
    *)
        echo "❌ Ошибка: неизвестное действие '$ACTION'"
        echo ""
        echo "Использование:"
        echo "  $0 start <version>   - создать hotfix-ветку"
        echo "  $0 finish <version>  - завершить hotfix-ветку"
        exit 1
        ;;
esac

