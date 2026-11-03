from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    supported_extensions: tuple[str, ...] = (".xlsx", ".csv")
    required_columns: tuple[str, ...] = ("group", "date", "position", "subject")
    audience_column: str = "audience"
    date_formats: tuple[str, ...] = ("%d.%m.%Y", "%Y-%m-%d")
    max_alias_length: int = 64
    format_hint: str = (
        "📄 Поддерживаю только <b>.xlsx</b> и <b>.csv</b>\n\n"
        "Формат — первая строка заголовок, колонки:\n"
        "<blockquote><code>group,date,position,subject,audience</code></blockquote>\n"
        "• <code>group</code> — 4-значный ID группы\n"
        "• <code>date</code> — ДД.ММ.ГГГГ\n"
        "• <code>position</code> — номер пары\n"
        "• <code>subject</code> — предмет\n"
        "• <code>audience</code> — аудитория (можно пустым)\n\n"
        "Лишние колонки игнорируются."
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
        "• Формат: заголовок <code>group,date,position,subject,audience</code>, "
        "дата ДД.ММ.ГГГГ, group — 4-значный ID\n"
        "• Группы из файла должны существовать в справочнике\n"
        "• Повторная загрузка на ту же дату заменяет расписание\n"
        "• После загрузки бот покажет отчёт: даты, пары, группы"
    )
    creator_help_extra: str = "\n\n• /admin — админ-панель"
