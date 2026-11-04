from dataclasses import dataclass
from datetime import date
from typing import Iterable

from aiogram.types import InlineKeyboardMarkup

from timetabler.domain.schemas import DaySchedule
from timetabler.infrastructure.config.app import AppConfig
from timetabler.presentation.messages.timetable_text import (
    build_broadcast_message,
    build_channel_html,
    format_group_schedule,
    format_group_schedule_html,
    subgroup_markup,
)


@dataclass
class SchedulePreview:
    markdown: str
    groups: int
    lessons: int


def _part(day: DaySchedule, group_id: int, config: AppConfig, mode: str = "a") -> str:
    return format_group_schedule(
        day.labels[group_id],
        day.audiences.get(group_id),
        day.by_group[group_id],
        config,
        mode,
    )


def group_messages(
    day: DaySchedule,
    for_date: date,
    groups: Iterable[str],
    config: AppConfig,
) -> list[tuple[str, InlineKeyboardMarkup | None]]:
    messages = []
    for g in groups:
        if not g.isdigit() or int(g) not in day.by_group:
            continue
        group_id = int(g)
        markup = subgroup_markup(group_id, for_date) if group_id in day.split else None
        messages.append((
            build_broadcast_message(for_date, [_part(day, group_id, config)], config),
            markup,
        ))
    return messages


def group_content(
    day: DaySchedule,
    for_date: date,
    group_id: int,
    mode: str,
    config: AppConfig,
) -> tuple[str, InlineKeyboardMarkup | None] | None:
    if group_id not in day.by_group:
        return None
    markdown = build_broadcast_message(
        for_date, [_part(day, group_id, config, mode)], config
    )
    markup = (
        subgroup_markup(group_id, for_date, mode) if group_id in day.split else None
    )
    return markdown, markup


def preview(
    day: DaySchedule,
    for_date: date,
    config: AppConfig,
    group_id: int | None = None,
) -> SchedulePreview | None:
    group_ids = [group_id] if group_id is not None else sorted(day.by_group)
    group_ids = [g for g in group_ids if g in day.by_group]
    if not group_ids:
        return None
    return SchedulePreview(
        markdown=build_broadcast_message(
            for_date, [_part(day, gid, config) for gid in group_ids], config
        ),
        groups=len(group_ids),
        lessons=sum(len(day.by_group[gid]) for gid in group_ids),
    )


def channel_html(day: DaySchedule, for_date: date, config: AppConfig) -> str:
    parts = [
        (
            day.labels[gid],
            format_group_schedule_html(
                day.audiences.get(gid), group_entries, config
            ),
        )
        for gid, group_entries in sorted(day.by_group.items())
    ]
    return build_channel_html(for_date, parts, config)
