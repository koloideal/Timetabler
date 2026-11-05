from dataclasses import dataclass
from datetime import date
from typing import Iterable

from aiogram.types import InlineKeyboardMarkup, InputRichBlockUnion

from timetabler.domain.schemas import DaySchedule
from timetabler.infrastructure.config.app import AppConfig
from timetabler.presentation.messages.timetable_text import (
    build_broadcast_blocks,
    build_channel_blocks,
    format_group_schedule,
    format_group_schedule_body,
    subgroup_markup,
)


@dataclass
class SchedulePreview:
    blocks: list[InputRichBlockUnion]
    groups: int
    lessons: int


def _part(
    day: DaySchedule,
    group_id: int,
    config: AppConfig,
    mode: str = "a",
    is_compact: bool = False,
) -> list[InputRichBlockUnion]:
    return format_group_schedule(
        day.labels[group_id],
        day.audiences.get(group_id),
        day.by_group[group_id],
        config,
        mode,
        is_compact,
    )


def group_messages(
    day: DaySchedule,
    for_date: date,
    groups: Iterable[str],
    config: AppConfig,
    mode: str = "a",
    is_compact: bool = False,
) -> list[tuple[list[InputRichBlockUnion], InlineKeyboardMarkup | None]]:
    messages = []
    for g in groups:
        if not g.isdigit() or int(g) not in day.by_group:
            continue
        group_id = int(g)
        markup = subgroup_markup(group_id, for_date, mode) if group_id in day.split else None
        messages.append((
            build_broadcast_blocks(
                for_date, [_part(day, group_id, config, mode, is_compact)], config
            ),
            markup,
        ))
    return messages


def group_content(
    day: DaySchedule,
    for_date: date,
    group_id: int,
    mode: str,
    config: AppConfig,
    is_compact: bool = False,
) -> tuple[list[InputRichBlockUnion], InlineKeyboardMarkup | None] | None:
    if group_id not in day.by_group:
        return None
    blocks = build_broadcast_blocks(
        for_date, [_part(day, group_id, config, mode, is_compact)], config
    )
    markup = (
        subgroup_markup(group_id, for_date, mode) if group_id in day.split else None
    )
    return blocks, markup


def preview(
    day: DaySchedule,
    for_date: date,
    config: AppConfig,
    group_id: int | None = None,
    mode: str = "a",
    is_compact: bool = False,
) -> SchedulePreview | None:
    group_ids = [group_id] if group_id is not None else sorted(day.by_group)
    group_ids = [g for g in group_ids if g in day.by_group]
    if not group_ids:
        return None
    return SchedulePreview(
        blocks=build_broadcast_blocks(
            for_date,
            [
                _part(day, gid, config, mode, is_compact)
                for gid in group_ids
            ],
            config,
        ),
        groups=len(group_ids),
        lessons=sum(len(day.by_group[gid]) for gid in group_ids),
    )


def channel_blocks(
    day: DaySchedule,
    for_date: date,
    config: AppConfig,
    is_compact: bool = False,
) -> list[InputRichBlockUnion]:
    parts = [
        (
            day.labels[gid],
            format_group_schedule_body(
                day.audiences.get(gid), group_entries, config,
                is_compact=is_compact,
            ),
        )
        for gid, group_entries in sorted(day.by_group.items())
    ]
    return build_channel_blocks(for_date, parts, config)
