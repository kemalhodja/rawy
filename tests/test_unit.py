"""Veritabanı gerektirmeyen birim testleri."""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import pytest

from app.services.note_graph_insights import extract_wikilinks, pair_theme_analysis
from app.services.calendar_logic import parse_event_from_voice
from app.services.recording_types import normalize_recording_type
from app.services.task_flow import nudge_cooldown_active, nudge_cooldown_until
from app.services.voice_deadline import parse_task_deadline


def test_parse_task_deadline_tomorrow_noon():
    d = parse_task_deadline("Bu yarın öğlene kadar bitireyim", "Europe/Istanbul")
    assert d is not None
    assert d.hour == 12


def test_parse_task_deadline_evening():
    d = parse_task_deadline("bugün akşam 7ye kadar", "Europe/Istanbul")
    assert d is not None
    assert d.hour == 19


def test_normalize_recording_type_focus():
    assert normalize_recording_type("focus_idea") == "focus_idea"
    assert normalize_recording_type("bogus") == "quick_note"


def test_wikilinks_and_pair_themes():
    t1 = "Toplantı [[Proje X]] bütçe milestone"
    t2 = "Yarın [[Proje X]] api bütçe milestone"
    assert extract_wikilinks(t1) == ["Proje X"]
    r = pair_theme_analysis(t1, t2)
    assert r["common_theme_count"] >= 1
    assert "Proje X" in r["shared_wikilinks"]
    assert "message_tr" in r


def test_nudge_cooldown():
    class MockUser:
        timezone = "UTC"
        last_task_nudge_at = datetime.now(dt_timezone.utc) - timedelta(hours=1)

    assert nudge_cooldown_active(MockUser()) is True
    assert nudge_cooldown_until(MockUser()) is not None

    class MockUser2:
        timezone = "UTC"
        last_task_nudge_at = None

    assert nudge_cooldown_active(MockUser2()) is False


def test_parse_event_from_voice_tomorrow_hour_and_duration():
    start, end, title, is_focus = parse_event_from_voice(
        "Yarin 3'te 2 saatlik yazi blogu", "Europe/Istanbul"
    )
    assert start.hour == 3
    assert int((end - start).total_seconds() / 3600) == 2
    assert "Yarin" in title
    assert is_focus is True
