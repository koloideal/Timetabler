from dataclasses import dataclass, field


@dataclass(frozen=True)
class GridParserConfig:
    # Расписание занимает колонки A..I, всё правее — служебный буфер
    main_columns: int = 9
    group_col: int = 0
    position_col: int = 1
    subject_col: int = 2
    # (subgroup, time, teacher, audience)
    subgroup_sets: tuple[tuple[int, int, int, int], ...] = ((1, 3, 4, 5), (2, 6, 7, 8))
    group_pattern: str = r"^\s*(\d{3,4})\s*(?:,\s*ауд\.?\s*(.+?))?\s*$"
    skipped_cell_values: tuple[str, ...] = ("", "-", "—")


@dataclass(frozen=True)
class SheetsClientConfig:
    scopes: tuple[str, ...] = (
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    )
    max_attempts: int = 4
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0


@dataclass(frozen=True)
class SheetsSettingsConfig:
    schedule_range_key: str = "sheets.schedule_range"
    date_cell_key: str = "sheets.date_cell"
    poll_interval_key: str = "sheets.poll_interval_seconds"
    confirmation_key: str = "sheets.require_confirmation"
    schedule_range_label: str = "диапазон расписания"
    date_cell_label: str = "ячейка даты"
    poll_interval_label: str = "интервал опроса, сек"
    confirmation_label: str = "подтверждение рассылки"
    default_schedule_range: str = "A1:I200"
    default_date_cell: str = "A1"
    default_poll_interval_seconds: int = 180
    min_poll_interval_seconds: int = 10
    spreadsheet_id_pattern: str = r"[A-Za-z0-9_-]+"
    spreadsheet_url_pattern: str = r"/d/([A-Za-z0-9_-]+)"
    a1_range_pattern: str = r"[A-Za-z]+\d+:[A-Za-z]+\d+"
    a1_cell_pattern: str = r"[A-Za-z]+\d+"

    @property
    def fields(self) -> tuple[tuple[str, str], ...]:
        return (
            (self.schedule_range_key, self.schedule_range_label),
            (self.date_cell_key, self.date_cell_label),
            (self.poll_interval_key, self.poll_interval_label),
            (self.confirmation_key, self.confirmation_label),
        )

    @property
    def text_fields(self) -> tuple[tuple[str, str], ...]:
        return self.fields[:3]


@dataclass(frozen=True)
class RevisionsConfig:
    stable_polls: int = 2
    max_settle_seconds: int = 1200
    update_timezone: str = "Europe/Moscow"
    send_delay_seconds: float = 0.05
    chat_send_failed_text: str = (
        "⚠️ Не смог отправить расписание в «{title}» — рассылка выключена. "
        "Проверьте, что я состою в чате и могу писать, "
        "затем включите её снова в «Мои группы»."
    )
    chat_pin_failed_text: str = (
        "⚠️ Не смог закрепить расписание в «{title}» — закреп выключен. "
        "Выдайте мне право «Закрепление сообщений» и включите его снова в «Мои группы»."
    )
    channel_send_failed_text: str = (
        "⚠️ Не смог отправить расписание в канал <code>{chat_id}</code> — канал отключён."
    )


@dataclass(frozen=True)
class AppConfig:
    required_columns: tuple[str, ...] = ("group", "position", "subject")
    date_formats: tuple[str, ...] = ("%d.%m.%Y", "%Y-%m-%d")
    time_format: str = "%H:%M"
    max_alias_length: int = 64
    separator: str = "━━━━━━━━━━━━━━━━━━"
    rich_message_limit: int = 32000
    grid: GridParserConfig = field(default_factory=GridParserConfig)
    sheets_client: SheetsClientConfig = field(default_factory=SheetsClientConfig)
    sheets_settings: SheetsSettingsConfig = field(default_factory=SheetsSettingsConfig)
    revisions: RevisionsConfig = field(default_factory=RevisionsConfig)
    user_help: str = (
        "ℹ️ <b>КАК ПОЛЬЗОВАТЬСЯ</b>\n"
        "<pre>━━━━━━━━━━━━━━━━━━\n"
        "/start     регистрация\n"
        "подписки   скоро появятся\n\n"
        "Когда выходит новое\n"
        "расписание — бот присылает\n"
        "его сюда. Работает и в\n"
        "групповых чатах.\n"
        "━━━━━━━━━━━━━━━━━━</pre>"
    )
    creator_help: str = (
        "🛠 <b>ПАНЕЛЬ СОЗДАТЕЛЯ</b>\n"
        "<pre>━━━━━━━━━━━━━━━━━━\n"
        "• /admin — панель управления\n"
        "• 📊 Таблицы — ID гугл-таблиц\n"
        "  и все настройки Sheets\n"
        "• Расписание подтягивается\n"
        "  из таблиц само и рассылается\n"
        "  подписчикам\n"
        "━━━━━━━━━━━━━━━━━━</pre>"
    )
    weekdays_short: tuple[str, ...] = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
