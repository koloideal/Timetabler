from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    required_columns: tuple[str, ...] = ("group", "position", "subject")
    date_formats: tuple[str, ...] = ("%d.%m.%Y", "%Y-%m-%d")
    time_format: str = "%H:%M"
    max_alias_length: int = 64
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
