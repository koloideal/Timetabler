from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class User:
    user_id: int
    username: str | None
    is_admin: bool
    is_banned: bool
    groups: list[str]
    created_at: datetime


@dataclass
class GroupChat:
    chat_id: int
    title: str | None
    groups: list[str]
    created_at: datetime


@dataclass
class TimetableEntry:
    date: date
    group: str
    position: int
    subject: str
    audience: str | None = None


@dataclass
class Timetable:
    date: date
    entries: list[TimetableEntry] = field(default_factory=list)
