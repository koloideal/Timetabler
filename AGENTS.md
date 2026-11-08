# Timetabler

Telegram-бот расписания НГАЭК: импортирует расписание из Google Sheets, детектит ревизии и рассылает обновления юзерам, чатам и каналам.

## Команды

```bash
just verify        # ruff (F,E9,PLE) + mypy — обязательно перед коммитом
.venv/bin/python -m pytest tests/ -q   # тесты (синхронные, asyncio.run внутри)
just run           # локальный запуск
just migrate       # alembic upgrade head
```

- Runtime: Python 3.13, `uv`, PostgreSQL (asyncpg), aiogram 3 + aiogram-dialog, Dishka DI.
- Конфиг: `secret_data/config.toml` (gitignored). Логи: `secret_data/logger-config.json` (tracked, dictConfig, уровень WARNING).

## Архитектура

`domain → application → infrastructure → presentation`, код в `src/timetabler/`.

- `domain/schemas.py` — датаклассы (`Revision`, `ResolvedLesson`, `DaySchedule`, `User`, `GroupChat`…)
- `application/services/` — `poller.py` (цикл опроса), `detection.py` (state-машина ревизий), `broadcast.py` (рассылка + идемпотентность), `lesson_timing.py` (резолвинг слотов/полупар)
- `application/ports/` — протоколы (`ScheduleSender`, `CreatorNotifier`, `ChatDelivery`)
- `infrastructure/` — `sheets/` (Google API через `asyncio.to_thread`), `parsing/grid_parser.py`, `database/` (async SQLAlchemy + DAO), `config/`, `ioc.py` (Dishka: APP-scope бот/клиенты/конфиг, REQUEST-scope сессия/DAO/сервисы)
- `presentation/` — `user_dialogs/` (aiogram-dialog окна), `admin_dialogs/`, handlers, `messages/` (rich-блоки), `telegram/schedule_sender.py`, `middlewares/`

## Ключевые инварианты

- **Ревизии**: `settling → approved → published` (или `pending_approval` при require_confirmation). `edit` требует `stable_polls` стабильных поллов или `max_settle_seconds`; `new` сеттлится сразу. `replace_snapshot` сбрасывает `stable_polls` — не ломать.
- **Полупары** (`kind` pe/kur): слот делится на `a`/`b`, занятость трекается по половинам (`full_slots` + `taken_halves`). Порядок a/b для безвременных полупар определяется порядком строк в таблице.
- **Парсер**: строка с данными только у sg2 → entry только для sg2; sg2 пуст → целая группа `(None, *sg1)`.
- **Идемпотентность рассылки**: `deliveries` (unique per revision+kind+chat) + `sent_messages` (dedup по группам). Повторный `_publish` не дублирует.
- **Telegram-ошибки**: `TelegramForbiddenError`/migrate → `forbidden=True` → чат дизейблится; `TelegramBadRequest` → `failed`, чат НЕ дизейблится.
- **Время**: вся бизнес-логика — `Europe/Minsk` через `app_config.revisions.update_timezone` (`schedule_today`, `_update_label`, `_now_info`). `detected_at`/`settled_at`/`sent_at` — tz-aware UTC в БД, это норма.

## aiogram-dialog грабли

- `manager.start(state, data=...)` кладёт в `start_data` (read-only), НЕ в `dialog_data`. Читай оба: `dialog_data` → fallback `start_data`.
- Геттеры вызываются на каждый рендер — без сайд-эффектов (`switch_to`, запись `dialog_data` — в on_click/on_start).
- `Multiselect` хранит отмеченные id как **строки**; префилл — `[str(g)]`, один раз на контекст (флаг в `dialog_data`), иначе перезапишешь клики.
- Онбординг: юзер в БД создаётся только по `complete_onboarding` («▶️ Продолжить»); до этого состояние в `dialog_data` (`pending_main`, `pending_groups`, `onboarding`).

## Деплой

Сервер `gitea-pi` (ssh alias): репо `~/bots/Timetabler`, сервис `timetabler.service`, venv `.venv`.

```bash
git push origin main
ssh gitea-pi 'cd ~/bots/Timetabler && git pull && .venv/bin/alembic upgrade head \
  && sudo -n systemctl restart timetabler && systemctl is-active timetabler'
```

Алиасы групп (`study_groups.alias`) правятся SQL напрямую в проде — подхватываются без рестарта.

## Прочее

- Без `assert` на продакшен-путях — явные проверки/`RuntimeError` (код может идти с `-O`).
- Секреты — только в `secret_data/` (gitignored кроме `logger-config.json`), ничего не коммитить.
- `CheckBanMiddleware` кэширует бан-статус на 60с (`_TTL_SECONDS`).
