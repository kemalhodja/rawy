"""
Sesli / metin planlama: 'Yarın 9'dan 12'ye yazı yazıyorum' -> başlangıç, bitiş, başlık.
Türkçe ve basit İngilizce kalıplar desteklenir (MVP).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def _extract_day_anchor(text: str, now_local: datetime) -> date:
    t = text.lower()
    d = now_local.date()
    if any(x in t for x in ("yarın", "yarin", "tomorrow")):
        return d + timedelta(days=1)
    if any(x in t for x in ("bugün", "bugun", "today")):
        return d
    if any(x in t for x in ("dün", "dun", "yesterday")):
        return d - timedelta(days=1)
    return d


def _parse_time_range(text: str) -> tuple[int, int, int, int] | None:
    """
    (h1, m1, h2, m2) veya None.
    Örnekler: 9'dan 12'ye, 9-12, 09:00-12:30, 14:00 to 16:00
    """
    s = text.lower().strip()

    m = re.search(
        r"(\d{1,2})(?:[:.](\d{2}))?\s*(?:'?(?:dan|ten|den)|\s*[-–—]\s*|(?:\s+to\s+)|(?:\s+until\s+))\s*(\d{1,2})(?:[:.](\d{2}))?",
        s,
        re.IGNORECASE,
    )
    if m:
        h1, m1, h2, m2 = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
        return (h1, int(m1) if m1 else 0, h2, int(m2) if m2 else 0)

    m2 = re.search(
        r"(\d{1,2})\s*[-–—]\s*(\d{1,2})(?!\d)",
        s,
    )
    if m2:
        h1, h2 = int(m2.group(1)), int(m2.group(2))
        if 0 <= h1 <= 23 and 0 <= h2 <= 23:
            return (h1, 0, h2, 0)

    return None


def _extract_title(text: str) -> str:
    s = re.sub(r"\s+", " ", text).strip()
    s = re.sub(
        r"(\d{1,2})(?:[:.](\d{2}))?\s*(?:'?(?:dan|ten|den)|\s*[-–—]\s*|(?:\s+to\s+)|(?:\s+until\s+))\s*(\d{1,2})(?:[:.](\d{2}))?",
        " ",
        s,
        flags=re.IGNORECASE,
    )
    for w in (
        "yarın",
        "yarin",
        "bugün",
        "bugun",
        "dün",
        "dun",
        "tomorrow",
        "today",
        "yesterday",
    ):
        s = re.sub(rf"\b{w}\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "Odak bloğu"


def parse_voice_planning(text: str, user_timezone: str) -> tuple[datetime, datetime, str]:
    """
    Raises ValueError açıklamalı mesajlarla.
    """
    if not text or not text.strip():
        raise ValueError("Metin boş olamaz")

    tz = ZoneInfo(user_timezone)
    now = datetime.now(tz)
    day = _extract_day_anchor(text, now)
    tr = _parse_time_range(text)
    if not tr:
        raise ValueError(
            "Saat aralığı anlaşılamadı. Örnek: 'Yarın 9'dan 12'ye yazı yazıyorum' veya '09:00-12:00'"
        )

    h1, m1, h2, m2 = tr
    if not (0 <= h1 <= 23 and 0 <= m1 <= 59 and 0 <= h2 <= 23 and 0 <= m2 <= 59):
        raise ValueError("Geçersiz saat değerleri")

    start = datetime.combine(day, time(h1, m1), tzinfo=tz)
    end = datetime.combine(day, time(h2, m2), tzinfo=tz)
    if end <= start:
        end = end + timedelta(days=1)

    title = _extract_title(text)
    return start, end, title


def has_time_range(text: str) -> bool:
    """Metinde takvim için kullanılabilecek saat aralığı var mı?"""
    return _parse_time_range(text) is not None
