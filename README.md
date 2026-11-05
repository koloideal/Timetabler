# Timetabler

**Timetabler** — your college timetable, delivered. Google Sheets in, native schedule tables out.

A powerful Telegram bot that watches Google Sheets for schedule changes, builds revisions, and broadcasts timetable updates to students, group chats, and channels.

---

## ✨ Features

Timetabler turns your messy spreadsheets into a proper schedule delivery system:

- **📊 Google Sheets Polling**: One spreadsheet per weekday, watched on a configurable interval with retries
- **🔄 Revision Pipeline**: Detected changes become revisions; optional creator confirmation before broadcast
- **📅 Native Rich Tables**: Schedule rendered as real Telegram tables (rich blocks), compact layout — no horizontal scroll
- **🎓 Group Subscriptions**: Users pick study groups; subgroup mode (1st / 2nd / all) is remembered per user
- **💬 Group Chats**: Per-chat group selection with optional auto-pin of the schedule message
- **📢 Channels**: Approval workflow — pending → approved → disabled
- **📤 XLSX Export**: Any day's raw spreadsheet delivered as a file
- **🗓 Admin Calendar**: Pick a date, preview any group's schedule or export it
- **🔕 Notification Toggle**: Users can mute and unmute schedule delivery anytime

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- PostgreSQL
- Telegram Bot Token (via [@BotFather](https://t.me/BotFather))
- Google Service Account JSON key (share your sheets with its email)

### Setup

```bash
uv sync                                 # install deps (just install)
cp secret_data/config.example.toml secret_data/config.toml
# fill in: bot token, creator_id, postgres creds, path to SA key
.venv/bin/alembic upgrade head          # just migrate
uv run python -m timetabler             # just run
```

## 👨‍💼 Admin Features

Access the admin panel with `/admin` command:

- 👥 **Users**: List, ban/unban (creator can't be banned)
- 💬 **Chats**: Status overview for every connected group chat
- 📢 **Channels**: Approve, disable, send schedule on demand, remove
- 🎓 **Groups**: Aliases for group IDs, deletion (creator only)
- 📊 **Sheets**: Bind a spreadsheet ID to each weekday, validate access on save
- ⚙️ **Settings**: Poll interval, schedule range, date cell, revision confirmation — all editable live
- 📅 **Schedule**: Calendar picker with today/tomorrow shortcuts → per-group TG preview (with subgroup toggle) or XLSX export

## 👤 User Features

- 📅 **Today / Tomorrow**: One-tap schedule from the main menu
- 🎓 **Subscriptions**: Pick which groups to follow
- 🔀 **Subgroups**: Switch between 1st / 2nd / all subgroups inline — the choice persists
- 💬 **My Chats**: Configure your own group chats: groups + pin mode
- 🔔 **Notifications**: Toggle schedule delivery on/off

## 🛠 Stack

`aiogram 3` · `aiogram-dialog` · `dishka` · `SQLAlchemy async + asyncpg` · `Alembic` · `google-api-python-client` · `uv` + `just`

Layered architecture under `src/timetabler`: `domain` → `application` → `infrastructure` → `presentation`.

```bash
just verify    # ruff + mypy
just watch     # dev mode with autoreload
```

## 📝 License

MIT — see [LICENSE](LICENSE)

---

Made with ❤️ for NGAEK students by <b>kolo</b>
