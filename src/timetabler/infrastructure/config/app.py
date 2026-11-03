from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    supported_extensions: tuple[str, ...] = (".xlsx", ".csv")
    required_columns: tuple[str, ...] = ("group", "date", "position", "subject")
    optional_columns: tuple[str, ...] = ("teacher", "audience", "time", "subgroup", "base_audience")
    date_formats: tuple[str, ...] = ("%d.%m.%Y", "%Y-%m-%d")
    time_format: str = "%H:%M"
    max_alias_length: int = 64
    format_hint: str = (
        "📄 <b>ФОРМАТ ФАЙЛА</b>\n"
        "<pre>━━━━━━━━━━━━━━━━━━\n"
        "Поддерживаю только .xlsx и .csv\n"
        "Первая строка — заголовок:\n\n"
        "group,date,position,subject,\n"
        "teacher,audience,time,subgroup,\n"
        "base_audience\n\n"
        "ОБЯЗАТЕЛЬНЫЕ\n"
        "group         4-зн. ID группы\n"
        "date          ДД.ММ.ГГГГ\n"
        "position      номер пары\n"
        "subject       предмет\n\n"
        "ОПЦИОНАЛЬНЫЕ\n"
        "teacher       преподаватель\n"
        "audience      аудитория пары\n"
        "time          ЧЧ:ММ\n"
        "subgroup      № подгруппы\n"
        "base_audience ауд. сбора\n"
        "━━━━━━━━━━━━━━━━━━</pre>"
    )
    user_help: str = (
        "ℹ️ <b>КАК ПОЛЬЗОВАТЬСЯ</b>\n"
        "<pre>━━━━━━━━━━━━━━━━━━\n"
        "/start     регистрация\n"
        "подписки   скоро появятся\n\n"
        "Когда админ заливает новое\n"
        "расписание — бот присылает\n"
        "его сюда. Работает и в\n"
        "групповых чатах.\n"
        "━━━━━━━━━━━━━━━━━━</pre>"
    )
    staff_help: str = (
        "🛠 <b>КАК РАБОТАТЬ С БОТОМ</b>\n"
        "<pre>━━━━━━━━━━━━━━━━━━\n"
        "• Отправьте .xlsx или .csv\n"
        "  прямо в этот чат\n"
        "• Обязательные колонки:\n"
        "  group,date,position,subject\n"
        "• Опциональные: teacher,\n"
        "  audience,time,subgroup,\n"
        "  base_audience\n"
        "• Дата ДД.ММ.ГГГГ, время ЧЧ:ММ\n"
        "• Группы должны быть в\n"
        "  справочнике\n"
        "• Повтор на дату = замена\n"
        "━━━━━━━━━━━━━━━━━━</pre>"
    )
    creator_help_extra: str = "\n\n• /admin — админ-панель"
    weekdays_short: tuple[str, ...] = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
