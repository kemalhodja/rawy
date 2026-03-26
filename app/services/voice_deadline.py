"""
Sesli görevler için son tarih (deadline) çıkarımı — Türkçe odaklı.
Örnek: 'Bu yarın öğlene kadar', 'bugün akşam 6'ya kadar'
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def _day_anchor(text: str, now_local: datetime) -> date:
    t = text.lower()
    d = now_local.date()
    if any(x in t for x in ("yarın", "yarin", "tomorrow")):
        return d + timedelta(days=1)
    if any(x in t for x in ("bugün", "bugun", "today")):
        return d
    if any(x in t for x in ("dün", "dun", "yesterday")):
        return d - timedelta(days=1)
    return d


def _parse_hour_minute(text: str) -> tuple[int, int] | None:
    """'18', '18:30', '7'ye' gibi saat dilimleri. Akşam + 1–11 → 13–23."""
    s = text.lower()
    m = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*'?(?:ya|ye|de|da)\b", s)
    if m:
        h, mn = int(m.group(1)), m.group(2)
        mn_i = int(mn) if mn else 0
        if 0 <= h <= 23:
            if ("akşam" in s or "aksam" in s) and 1 <= h <= 11:
                h += 12
            return (h, mn_i)
    m2 = re.search(r"\b(\d{1,2})[:.](\d{2})\b", s)
    if m2:
        h, mn = int(m2.group(1)), int(m2.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return (h, mn)
    return None


def has_deadline_speech(text: str) -> bool:
    """Görev + son tarih niyeti (takvim aralığından ayrı)."""
    if not text or not text.strip():
        return False
    t = text.lower()
    if re.search(r"\d{1,2}\s*(?:'?(?:dan|ten|den)|\s*[-–—])\s*\d{1,2}", t):
        # Saat aralığı — takvim hattına bırak
        return False
    if "kadar" in t or "deadline" in t or "son gün" in t or "son tarih" in t:
        return True
    if any(x in t for x in ("öğlene kadar", "ogleye kadar", "öğlen", "ogle")) and any(
        x in t for x in ("yarın", "yarin", "bugün", "bugun", "tomorrow", "today")
    ):
        return True
    return False


def parse_task_deadline(text: str, user_timezone: str) -> datetime | None:
    """
    Tek bir son tarih/saat döner; anlaşılamazsa None.
    Kullanıcı saat diliminde, timezone-aware.
    """
    if not text or not text.strip():
        return None

    tz = ZoneInfo(user_timezone)
    now = datetime.now(tz)
    t = text.lower()
    day = _day_anchor(text, now)

    # Öğle / noon
    if "öğlene" in t or "ogleye" in t or "öğlen " in t or " öğlen" in t:
        if "yarın" in t or "yarin" in t or "tomorrow" in t:
            d = now.date() + timedelta(days=1)
        elif "bugün" in t or "bugun" in t or "today" in t:
            d = now.date()
        else:
            d = day
        return datetime.combine(d, time(12, 0), tzinfo=tz)

    # Akşam (varsayılan 18:00; 'akşam 7' → 19:00)
    if "akşam" in t or "aksam" in t:
        hm = _parse_hour_minute(text)
        if hm:
            h, m = hm
        else:
            h, m = 18, 0
        return datetime.combine(day, time(h, m), tzinfo=tz)

    # Sabah (varsayılan 09:00)
    if "sabah" in t:
        hm = _parse_hour_minute(text)
        h, m = (hm if hm else (9, 0))
        return datetime.combine(day, time(h, m), tzinfo=tz)

    # "5'e kadar" / saat ile
    if "kadar" in t or "'e kadar" in t or "'ya kadar" in t:
        hm = _parse_hour_minute(text)
        if hm:
            h, m = hm
            return datetime.combine(day, time(h, m), tzinfo=tz)

    # Yarın / bugün + ham saat
    if any(x in t for x in ("yarın", "yarin", "bugün", "bugun")):
        hm = _parse_hour_minute(text)
        if hm:
            h, m = hm
            return datetime.combine(day, time(h, m), tzinfo=tz)

    return None
