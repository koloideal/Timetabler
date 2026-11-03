from dataclasses import dataclass, field
from datetime import date, datetime, time


@dataclass
class User:
    user_id: int
    username: str | None
    is_banned: bool
    notifications_enabled: bool
    groups: list[str]
    created_at: datetime


@dataclass
class GroupChat:
    chat_id: int
    title: str | None
    groups: list[str]
    created_at: datetime


@dataclass
class StudyGroup:
    group_id: int
    alias: str | None
    created_at: datetime

    @property
    def display_name(self) -> str:
        return f"{self.group_id} — {self.alias}" if self.alias else str(self.group_id)


@dataclass
class TimetableEntry:
    group_id: int
    date: date
    position: int | None
    subject: str
    teacher: str | None = None
    audience: str | None = None
    starts_at: time | None = None
    subgroup: int | None = None


@dataclass
class ParsedTimetable:
    entries: list[TimetableEntry] = field(default_factory=list)
    base_audiences: dict[int, str] = field(default_factory=dict)


@dataclass
class Timetable:
    id: int
    for_date: date
    filename: str | None
    uploaded_by: int
    created_at: datetime


@dataclass
class SheetSource:
    weekday: int
    spreadsheet_id: str | None
    last_header: str | None


@dataclass
class SheetsSettings:
    schedule_range: str
    date_cell: str
    poll_interval_seconds: int
    require_confirmation: bool


@dataclass
class PendingBroadcast:
    weekday: int
    marker: str
    dates: list[date]
