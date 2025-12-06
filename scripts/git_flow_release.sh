#!/bin/bash

# Скрипт для работы с release-ветками в Git Flow
# Использование:
#   ./scripts/git_flow_release.sh start 4.1.0
#   ./scripts/git_flow_release.sh finish 4.1.0

set -e

ACTION=$1
VERSION=$2

if [ -z "$ACTION" ] || [ -z "$VERSION" ]; then
    echo "❌ Ошибка: не указаны параметры"
    echo ""
    echo "Использование:"
    echo "  $0 start <version>   - создать release-ветку"
    echo "  $0 finish <version>  - завершить release-ветку"
    echo ""
    echo "Примеры:"
    echo "  $0 start 4.1.0"
    echo "  $0 finish 4.1.0"
    exit 1
fi

# Проверка формата версии (X.Y.Z)
if ! [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "❌ Ошибка: неверный формат версии"
    echo "Используйте формат X.Y.Z (например: 4.1.0)"
    exit 1
fi

RELEASE_BRANCH="release/v$VERSION"
TAG="v$VERSION"

case "$ACTION" in
    start)
        echo "🚀 Создание release-ветки: $RELEASE_BRANCH"
        echo ""
        
        # Проверка, что мы в репозитории
        if ! git rev-parse --git-dir > /dev/null 2>&1; then
            echo "❌ Ошибка: не найден git репозиторий"
            exit 1
        fi
        
        # Проверка, что ветка не существует
        if git show-ref --verify --quiet refs/heads/$RELEASE_BRANCH; then
            echo "❌ Ошибка: ветка $RELEASE_BRANCH уже существует"
            exit 1
        fi
        
        if git show-ref --verify --quiet refs/remotes/origin/$RELEASE_BRANCH; then
            echo "❌ Ошибка: удаленная ветка $RELEASE_BRANCH уже существует"
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
        
        # Обновить develop
        echo "📥 Обновление develop..."
        git checkout develop
        git pull origin develop
        
        # Создать release-ветку
        echo "🌿 Создание ветки $RELEASE_BRANCH..."
        git checkout -b $RELEASE_BRANCH develop
        
        echo ""
        echo "✅ Release-ветка $RELEASE_BRANCH создана!"
        echo ""
        echo "📝 Следующие шаги:"
        echo "   1. Обновите CHANGELOG.md (переместите записи из [Unreleased] в [$VERSION])"
        echo "   2. Обновите README.md (версия)"
        echo "   3. Проведите финальное тестирование"
        echo "   4. Закоммитьте изменения:"
        echo "      git add CHANGELOG.md README.md"
        echo "      git commit -m 'chore: подготовка к релизу $TAG'"
        echo "      git push origin $RELEASE_BRANCH"
        echo "   5. После завершения: $0 finish $VERSION"
        ;;
        
    finish)
        echo "🏁 Завершение release-ветки: $RELEASE_BRANCH"
        echo ""
        
        # Проверка, что мы в репозитории
        if ! git rev-parse --git-dir > /dev/null 2>&1; then
            echo "❌ Ошибка: не найден git репозиторий"
            exit 1
        fi
        
        # Проверка, что ветка существует
        if ! git show-ref --verify --quiet refs/heads/$RELEASE_BRANCH; then
            echo "❌ Ошибка: локальная ветка $RELEASE_BRANCH не найдена"
            echo "   Убедитесь, что вы находитесь в нужной ветке или создайте её"
            exit 1
        fi
        
        # Проверка, что тег не существует
        if git rev-parse "$TAG" >/dev/null 2>&1; then
            echo "❌ Ошибка: тег $TAG уже существует"
            exit 1
        fi
        
        # Проверка, что CHANGELOG.md обновлен
        if grep -q "## \[Unreleased\]" CHANGELOG.md 2>/dev/null; then
            if ! grep -q "## \[$VERSION\]" CHANGELOG.md 2>/dev/null; then
                echo "⚠️  Предупреждение: в CHANGELOG.md есть записи в разделе [Unreleased]"
                echo "   Убедитесь, что вы переместили их в раздел [$VERSION]"
                read -p "Продолжить? (y/n) " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    exit 1
                fi
            fi
        fi
        
        # Переключиться на release-ветку
        git checkout $RELEASE_BRANCH
        
        # Обновить main
        echo "📥 Обновление main..."
        git checkout main
        git pull origin main
        
        # Мерж release-ветки в main
        echo "🔀 Мерж $RELEASE_BRANCH в main..."
        git merge --no-ff $RELEASE_BRANCH -m "Merge branch '$RELEASE_BRANCH' into main"
        
        # Создать тег
        echo "📌 Создание тега $TAG..."
        git tag -a "$TAG" -m "Release version $VERSION"
        
        # Отправить main и тег
        echo "📤 Отправка main и тега..."
        git push origin main
        git push origin "$TAG"
        
        # Мерж release-ветки в develop
        echo "🔀 Мерж $RELEASE_BRANCH в develop..."
        git checkout develop
        git pull origin develop
        git merge --no-ff $RELEASE_BRANCH -m "Merge branch '$RELEASE_BRANCH' into develop"
        git push origin develop
        
        # Удалить локальную ветку
        echo "🗑️  Удаление локальной ветки $RELEASE_BRANCH..."
        git branch -d $RELEASE_BRANCH
        
        # Удалить удаленную ветку (если существует)
        if git show-ref --verify --quiet refs/remotes/origin/$RELEASE_BRANCH; then
            echo "🗑️  Удаление удаленной ветки $RELEASE_BRANCH..."
            git push origin --delete $RELEASE_BRANCH
        fi
        
        echo ""
        echo "✅ Release-ветка $RELEASE_BRANCH успешно завершена!"
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
        echo "  $0 start <version>   - создать release-ветку"
        echo "  $0 finish <version>  - завершить release-ветку"
        exit 1
        ;;
esac

