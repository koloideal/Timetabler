import re

from timetabler.domain.schemas import StudyGroup

_COURSE_RE = re.compile(r"(\d+)\s*курс", re.IGNORECASE)
_TAIL_RE = re.compile(r",?\s*\d+\s*курс.*$", re.IGNORECASE)
_AFTER_RE = re.compile(r"\s+после\s+\d+\b", re.IGNORECASE)


def course_of(group: StudyGroup) -> int | None:
    if group.alias and (m := _COURSE_RE.search(group.alias)):
        return int(m.group(1))
    last = group.group_id % 10
    return 7 - last if 3 <= last <= 6 else None


def specialty_code(group: StudyGroup) -> str:
    return str(group.group_id)[0]


def specialty_labels(groups: list[StudyGroup]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for g in sorted(groups, key=lambda g: g.group_id):
        code = specialty_code(g)
        if code in labels or not g.alias:
            continue
        label = _AFTER_RE.sub("", _TAIL_RE.sub("", g.alias)).strip()
        if label:
            labels[code] = label
    return {code: labels.get(code, f"Спец. {code}") for code in {specialty_code(g) for g in groups}}
