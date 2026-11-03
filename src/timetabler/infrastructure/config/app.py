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
        "📄 Поддерживаю только <b>.xlsx</b> и <b>.csv</b>\n\n"
        "Формат — первая строка заголовок, колонки:\n"
        "<blockquote><code>group,date,position,subject,teacher,audience,time,subgroup,base_audience</code></blockquote>\n"
        "Обязательные: <code>group</code>, <code>date</code>, <code>position</code>, <code>subject</code>\n"
        "• <code>group</code> — 4-значный ID группы\n"
        "• <code>date</code> — ДД.ММ.ГГГГ\n"
        "• <code>position</code> — номер пары\n"
        "• <code>subject</code> — предмет\n"
        "• <code>teacher</code> — преподаватель\n"
        "• <code>audience</code> — аудитория пары\n"
        "• <code>time</code> — время начала (ЧЧ:ММ)\n"
        "• <code>subgroup</code> — номер подгруппы\n"
        "• <code>base_audience</code> — аудитория сбора группы\n\n"
        "Необязательные можно пустить или опустить, лишние колонки игнорируются."
    )
    user_help: str = (
        "ℹ️ <b>Как пользоваться ботом</b>\n\n"
        "• /start — регистрация\n"
        "• Выберите свои учебные группы — подписки появятся совсем скоро\n"
        "• Когда админ загружает новое расписание — бот присылает его сюда\n\n"
        "<i>Бот также работает в групповых чатах.</i>"
    )
    staff_help: str = (
        "🛠 <b>Как работать с ботом</b>\n\n"
        "• Отправьте файл расписания (<b>.xlsx</b> или <b>.csv</b>) прямо в этот чат — "
        "бот разберёт его и сохранит\n"
        "• Обязательные колонки: <code>group,date,position,subject</code>\n"
        "• Опциональные: <code>teacher,audience,time,subgroup,base_audience</code>\n"
        "• Дата ДД.ММ.ГГГГ, время ЧЧ:ММ, group — 4-значный ID\n"
        "• Группы из файла должны существовать в справочнике\n"
        "• Повторная загрузка на ту же дату заменяет расписание\n"
        "• После загрузки бот покажет отчёт: даты, пары, группы"
    )
    creator_help_extra: str = "\n\n• /admin — админ-панель"
