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
    subgroup_mode: str = "a"


@dataclass
class Channel:
    chat_id: int
    title: str | None
    status: str
    created_at: datetime


@dataclass
class GroupChat:
    chat_id: int
    title: str | None
    status: str
    study_groups: list[int]
    pin_enabled: bool
    pinned_message_ids: list[int]
    added_by_user_id: int | None
    configured_by_user_id: int | None
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
class Revision:
    id: int
    for_date: date
    weekday: int
    header: str | None
    content_hash: str | None
    group_hashes: dict[int, str]
    base_audiences: dict[int, str]
    kind: str
    changed_groups: list[int]
    diff: dict[int, list[str]]
    parent_revision_id: int | None
    status: str
    stable_polls: int
    detected_at: datetime
    settled_at: datetime | None
    published_at: datetime | None


@dataclass
class SentMessage:
    id: int
    revision_id: int | None
    for_date: date
    chat_id: int
    message_id: int
    kind: str
    groups: list[str]
    sent_at: datetime


@dataclass
class Delivery:
    id: int
    revision_id: int
    kind: str
    chat_id: int
    status: str
    sent_at: datetime | None


@dataclass
class SheetSource:
    weekday: int
    spreadsheet_id: str | None
    last_header: str | None
    last_hash: str | None


@dataclass
class DaySchedule:
    by_group: dict[int, list[TimetableEntry]]
    audiences: dict[int, str]
    labels: dict[int, str]
    split: set[int]


@dataclass
class SheetsSettings:
    schedule_range: str
    date_cell: str
    poll_interval_seconds: int
    require_confirmation: bool
