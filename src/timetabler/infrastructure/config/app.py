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
class LessonSlotConfig:
    start: str
    end: str
    half_b_start: str | None = None


_WEEKDAY_SLOTS: tuple[LessonSlotConfig, ...] = (
    LessonSlotConfig("09:00", "10:35", "09:50"),
    LessonSlotConfig("10:45", "12:20", "11:35"),
    LessonSlotConfig("13:20", "14:55", "14:10"),
    LessonSlotConfig("15:05", "16:40", "15:55"),
    LessonSlotConfig("16:50", "18:25", "17:40"),
)
_SATURDAY_SLOTS: tuple[LessonSlotConfig, ...] = (
    LessonSlotConfig("09:00", "10:25"),
    LessonSlotConfig("10:35", "12:00"),
    LessonSlotConfig("12:10", "13:35"),
)


@dataclass(frozen=True)
class LessonTimingConfig:
    pe_markers: tuple[str, ...] = ("физическая культура", "физическая культура и здоровье")
    kur_markers: tuple[str, ...] = ("кураторск", "кур. час", "кур час")
    half_len: tuple[int | None, ...] = (2700, 2700, 2700, 2700, 2700, None, None)
    weekday_slots: tuple[tuple[LessonSlotConfig, ...], ...] = (
        _WEEKDAY_SLOTS,
        _WEEKDAY_SLOTS,
        _WEEKDAY_SLOTS,
        _WEEKDAY_SLOTS,
        _WEEKDAY_SLOTS,
        _SATURDAY_SLOTS,
        (),
    )


@dataclass(frozen=True)
class RevisionsConfig:
    stable_polls: int = 2
    max_settle_seconds: int = 1200
    update_timezone: str = "Europe/Moscow"
    send_delay_seconds: float = 0.05
    chat_send_failed_text: str = (
        "⚠️ <b>Не смог отправить расписание в «{title}»</b> — рассылка выключена.\n\n"
        "Проверьте, что я состою в чате и могу писать, "
        "затем включите её снова в «💬 Мои чаты»."
    )
    chat_pin_failed_text: str = (
        "⚠️ <b>Не смог закрепить расписание в «{title}»</b> — закреп выключен.\n\n"
        "Выдайте мне право «Закрепление сообщений» и включите его снова в «💬 Мои чаты»."
    )
    channel_send_failed_text: str = (
        "⚠️ <b>Не смог отправить расписание в канал <code>{chat_id}</code></b> — канал отключён."
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
    lesson_timing: LessonTimingConfig = field(default_factory=LessonTimingConfig)
    user_help: str = (
        "<b>ℹ️ Справка</b>\n\n"
        "Я присылаю расписание пар: в личку по вашим подпискам "
        "и в чаты, куда меня добавили. Когда расписание меняется — "
        "приходит обновление.\n\n"
        "<b>Команды</b>\n"
        "/start — главное меню\n"
        "/help — эта справка\n\n"
        "<b>Меню</b>\n"
        "📅 Моё расписание — расписание на ближайший учебный день\n"
        "🎓 Подписки — выбор групп для личной рассылки\n"
        "💬 Мои чаты — настройка чатов, где вы админ\n"
        "🔔 Уведомления — вкл/выкл автоматической рассылки"
    )
    creator_help: str = (
        "👑 <b>Панель создателя</b>\n\n"
        "/admin — открыть панель управления\n\n"
        "<b>Разделы панели</b>\n"
        "👥 Пользователи — список, блокировка\n"
        "📊 Таблицы — привязка Google-таблиц по дням недели\n"
        "🎓 Группы — номера и алиасы учебных групп\n"
        "📅 Расписание — превью по группам и скачивание XLSX\n"
        "💬 Чаты — подключённые групповые чаты\n"
        "📢 Каналы — модерация каналов, отправка расписания\n"
        "⚙️ Настройки — диапазон, ячейка даты, интервал опроса, "
        "подтверждение рассылки\n\n"
        "Бот сам следит за таблицами: новая версия или правка — "
        "уведомление на одобрение (если включено в настройках) "
        "или сразу рассылка."
    )
    group_help: str = (
        "<b>ℹ️ Справка</b>\n\n"
        "Я присылаю в этот чат расписание выбранных учебных групп "
        "и присылаю обновления при изменениях.\n\n"
        "Настройка — только в личке: админ группы открывает диалог со мной, "
        "жмёт «💬 Мои чаты» в меню и выбирает этот чат — там группы "
        "расписания, закреп и вкл/выкл рассылки."
    )
    weekdays_short: tuple[str, ...] = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
