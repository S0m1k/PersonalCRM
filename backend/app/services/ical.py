"""
iCalendar (RFC 5545) для CalDAV: событие CRM ↔ VEVENT iPhone / Android (DAVx⁵).

Запись: время выдаётся в UTC (`...Z`), поэтому VTIMEZONE не нужен; «весь день» — `VALUE=DATE`.
Чтение: понимает `TZID` (IANA), UTC, «плавающее» время (берётся как UTC), `DURATION` вместо `DTEND`.
Всё, что CRM не хранит (RRULE, EXDATE, VALARM, ORGANIZER …), сохраняется строками в `dav_extra`
и возвращается телефону как есть — повторяющиеся встречи и напоминания не теряются.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..models.event import EventOut

PRODID = "-//PersonalCRM//CalDAV//RU"
MAX_LINE_OCTETS = 75
NO_TITLE = "Без названия"

# Свойства VEVENT, которые CRM разбирает сам; остальные уходят в dav_extra
_HANDLED = {"UID", "SUMMARY", "DTSTART", "DTEND", "DURATION", "LOCATION", "DESCRIPTION", "ATTENDEE",
            "DTSTAMP", "CREATED", "LAST-MODIFIED", "PRODID", "VERSION"}

_PARTSTAT = {"accepted": "ACCEPTED", "declined": "DECLINED", "tentative": "TENTATIVE", "needsaction": "NEEDS-ACTION"}
_PARTSTAT_BACK = {v: k for k, v in _PARTSTAT.items()}
_PARTSTAT_BACK["NEEDS-ACTION"] = "needsAction"


class IcalError(ValueError):
    """Событие нельзя принять: нет даты начала, неизвестный пояс и т.п."""


# ---------------------------------------------------------------------------
# Строки: экранирование и перенос
# ---------------------------------------------------------------------------


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\").replace("\r\n", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")
    )


def _unescape(value: str) -> str:
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


def _param_escape(value: str) -> str:
    """Значение параметра (CN=…): без разделителей; кавычки, если есть запятая или двоеточие."""
    clean = value.replace('"', "'").replace("\r", " ").replace("\n", " ")
    return f'"{clean}"' if re.search(r"[,:;]", clean) else clean


def _fold(line: str) -> str:
    chunks: list[str] = []
    current, size, limit = "", 0, MAX_LINE_OCTETS
    for ch in line:
        width = len(ch.encode())
        if size + width > limit:
            chunks.append(current)
            current, size, limit = "", 0, MAX_LINE_OCTETS - 1
        current += ch
        size += width
    chunks.append(current)
    return "\r\n ".join(chunks)


def _unfold(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [line for line in re.sub(r"\n[ \t]", "", text).split("\n") if line.strip()]


def _utc_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# Запись
# ---------------------------------------------------------------------------


def _attendee_line(attendee) -> Optional[str]:
    if not attendee.email:
        return None
    params = []
    if attendee.name:
        params.append(f"CN={_param_escape(attendee.name)}")
    partstat = _PARTSTAT.get(attendee.response.lower())
    if partstat:
        params.append(f"PARTSTAT={partstat}")
    head = ";".join(["ATTENDEE", *params])
    return f"{head}:mailto:{attendee.email}"


def event_to_ical(event: EventOut, uid: Optional[str] = None, extra: Optional[list[str]] = None) -> str:
    """VCALENDAR с одним VEVENT, строки через CRLF."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "BEGIN:VEVENT",
        f"UID:{uid or event.id}",
        f"DTSTAMP:{_utc_stamp(event.updated_at)}",
        f"CREATED:{_utc_stamp(event.created_at)}",
        f"LAST-MODIFIED:{_utc_stamp(event.updated_at)}",
        f"SUMMARY:{_escape(event.title)}",
    ]
    if event.all_day:
        lines.append(f"DTSTART;VALUE=DATE:{event.start.strftime('%Y%m%d')}")
        lines.append(f"DTEND;VALUE=DATE:{event.end.strftime('%Y%m%d')}")
    else:
        lines.append(f"DTSTART:{_utc_stamp(event.start)}")
        lines.append(f"DTEND:{_utc_stamp(event.end)}")
    if event.location:
        lines.append(f"LOCATION:{_escape(event.location)}")
    if event.description:
        lines.append(f"DESCRIPTION:{_escape(event.description)}")
    lines.extend(filter(None, (_attendee_line(a) for a in event.attendees)))
    lines.extend(extra or [])
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "".join(_fold(line) + "\r\n" for line in lines)


# ---------------------------------------------------------------------------
# Чтение
# ---------------------------------------------------------------------------


def _parse_line(line: str) -> tuple[str, dict[str, str], str]:
    """`ATTENDEE;CN="Иванов, П.";PARTSTAT=ACCEPTED:mailto:x@y` → (имя, параметры, значение)."""
    in_quotes, split_at = False, -1
    for i, ch in enumerate(line):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == ":" and not in_quotes:
            split_at = i
            break
    if split_at < 0:
        return line.upper(), {}, ""
    head, value = line[:split_at], line[split_at + 1 :]
    parts = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', head)
    params: dict[str, str] = {}
    for part in parts[1:]:
        key, _, raw = part.partition("=")
        params[key.upper()] = raw.strip('"')
    return parts[0].split(".")[-1].upper(), params, value


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise IcalError(f"Неизвестный часовой пояс {name!r}") from None


def _parse_dt(params: dict[str, str], value: str) -> tuple[datetime, bool, str]:
    """(момент в UTC, «весь день», пояс события)."""
    value = value.strip()
    try:
        if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
            day = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
            return datetime(day.year, day.month, day.day, tzinfo=timezone.utc), True, "UTC"
        naive = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    except ValueError:
        raise IcalError(f"Не удалось разобрать дату {value!r}") from None
    if value.endswith("Z"):
        return naive.replace(tzinfo=timezone.utc), False, "UTC"
    tzid = params.get("TZID")
    if tzid:
        return naive.replace(tzinfo=_tz(tzid)).astimezone(timezone.utc), False, tzid
    return naive.replace(tzinfo=timezone.utc), False, "UTC"


def _parse_duration(value: str) -> timedelta:
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip())
    if not m or value.strip() in ("P", "PT"):
        raise IcalError(f"Не удалось разобрать длительность {value!r}")
    sign, w, d, h, mi, s = m.groups()
    delta = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0), seconds=int(s or 0))
    return -delta if sign == "-" else delta


def _vevent_lines(text: str) -> list[str]:
    inside, lines = False, []
    for line in _unfold(text):
        upper = line.upper()
        if upper == "BEGIN:VEVENT":
            inside, lines = True, []
        elif upper == "END:VEVENT" and inside:
            return lines
        elif inside:
            lines.append(line)
    raise IcalError("В календаре нет события (VEVENT)")


def ical_uid(text: str) -> Optional[str]:
    try:
        lines = _vevent_lines(text)
    except IcalError:
        return None
    for line in lines:
        name, _, value = _parse_line(line)
        if name == "UID":
            return _unescape(value).strip() or None
    return None


def ical_to_fields(text: str) -> dict:
    """
    Поля события CRM из VEVENT. Ключи: title, start, end, all_day, timezone, location, description,
    attendees, dav_extra. Отсутствующие в карточке location/description возвращаются пустыми —
    чтобы очистка на телефоне дошла до CRM.
    """
    fields: dict = {"title": "", "location": "", "description": "", "attendees": [], "timezone": "UTC"}
    start: Optional[tuple[datetime, bool, str]] = None
    end: Optional[tuple[datetime, bool, str]] = None
    duration: Optional[timedelta] = None
    extra: list[str] = []
    depth = 0  # вложенные компоненты (VALARM) сохраняем целиком

    for line in _vevent_lines(text):
        upper = line.upper()
        if upper.startswith("BEGIN:"):
            depth += 1
            extra.append(line)
            continue
        if upper.startswith("END:"):
            depth -= 1
            extra.append(line)
            continue
        if depth > 0:
            extra.append(line)
            continue
        name, params, value = _parse_line(line)
        if name == "SUMMARY":
            fields["title"] = _unescape(value).strip()
        elif name == "LOCATION":
            fields["location"] = _unescape(value).strip()
        elif name == "DESCRIPTION":
            fields["description"] = _unescape(value)
        elif name == "DTSTART":
            start = _parse_dt(params, value)
        elif name == "DTEND":
            end = _parse_dt(params, value)
        elif name == "DURATION":
            duration = _parse_duration(value)
        elif name == "ATTENDEE":
            email = re.sub(r"^mailto:", "", value.strip(), flags=re.IGNORECASE).lower()
            if email:
                fields["attendees"].append(
                    {
                        "email": email,
                        "name": params.get("CN", ""),
                        "phone": "",
                        "response": _PARTSTAT_BACK.get(params.get("PARTSTAT", "").upper(), ""),
                    }
                )
        elif name not in _HANDLED:
            extra.append(line)

    if start is None:
        raise IcalError("У события нет даты начала (DTSTART)")
    start_utc, all_day, tz_name = start
    if end is not None:
        end_utc = end[0]
    elif duration is not None:
        end_utc = start_utc + duration
    else:
        end_utc = start_utc + (timedelta(days=1) if all_day else timedelta(hours=1))
    if end_utc < start_utc:
        raise IcalError("Конец события раньше начала")
    if all_day and end_utc <= start_utc:
        end_utc = start_utc + timedelta(days=1)

    fields.update(
        title=fields["title"] or NO_TITLE,
        start=start_utc,
        end=end_utc,
        all_day=all_day,
        timezone=tz_name,
        dav_extra=extra,
    )
    return fields
