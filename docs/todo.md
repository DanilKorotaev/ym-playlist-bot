# TODO

## Выполнено ✅

Все выполненные задачи перенесены в отдельный файл для удобной навигации: [completed.md](completed.md)

## В процессе 🚧

- [ ] [Дополнительные улучшения документации](tasks/pending/task-doc-improvements.md)

## Запланировано 📋

### Улучшения UX

- [ ] [Добавить предпросмотр трека перед добавлением](tasks/pending/task-ux-track-preview.md)

### Технические улучшения

- [ ] [Вынос Mini App API в отдельный контейнер](tasks/pending/task-tech-separate-api-container.md)
- [ ] [Добавить pydantic-based settings для валидации конфигурации](tasks/pending/task-tech-pydantic-settings.md)
- [ ] [Улучшить логирование (структурированные логи)](tasks/pending/task-tech-structured-logging.md)
- [ ] [Внедрение процессов тестирования](tasks/pending/task-testing-implementation.md)

### Новые функции

- [ ] [Автоматическое обновление очереди воспроизведения при добавлении новых треков](tasks/pending/task-feature-auto-queue-update.md)
- [ ] [Реализация музыкального плеера в Telegram Mini App](tasks/pending/task-feature-miniapp-player.md)
- [ ] [Доработка Mini App плеера: исправление воспроизведения и улучшения](tasks/pending/task-feature-miniapp-player-fixes.md)
- [ ] [Уведомления о новых треках в общих плейлистах](tasks/pending/task-feature-notifications.md)
- [ ] [Управление неиспользуемыми плейлистами в аккаунте Яндекс.Музыки](tasks/pending/task-feature-unused-playlists.md)
- [ ] [Админка для управления лимитами пользователей](tasks/pending/task-feature-admin-panel.md)
- [ ] [Управление треками по авторству](tasks/pending/task-feature-track-ownership.md)
- [ ] [Статистика по плейлистам](tasks/pending/task-feature-playlist-stats.md)
- [ ] [Улучшение ссылок на плейлисты](tasks/pending/task-feature-playlist-link-format.md)
- [ ] [Миграция треков между музыкальными сервисами](tasks/pending/task-feature-playlist-migration.md)
- [ ] [Интеграция других музыкальных сервисов (ВК-музыка, Spotify)](tasks/pending/task-feature-music-services-integration.md)

### Документация

- [ ] [Создать API документацию](tasks/pending/task-doc-api-documentation.md)
- [ ] [Создать видео-инструкции](tasks/pending/task-doc-video-tutorials.md)

---

## Структура задач

Каждая задача имеет свой файл-артефакт в папке [`docs/tasks/pending/`](tasks/pending/) (для невыполненных задач) или [`docs/tasks/completed/`](tasks/completed/) (для выполненных задач), где хранится:
- Описание задачи
- Проблема/цель
- Декомпозиция на подзадачи
- План реализации
- Чеклист выполнения
- Связанные файлы
- Приоритет и статус

## Организация документации

Документация организована по категориям:
- [`research/`](research/) - исследования и анализ
- [`plans/`](plans/) - планы реализации
- [`reports/`](reports/) - отчеты и саммари
- [`instructions/`](instructions/) - инструкции и руководства
- [`architecture/`](architecture/) - архитектурная документация
- [`tasks/pending/`](tasks/pending/) - невыполненные задачи
- [`tasks/completed/`](tasks/completed/) - выполненные задачи
