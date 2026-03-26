VALID_RECORDING_TYPES = frozenset(
    {
        "quick_note",
        "quick_capture",  # ~30 sn widget; sunucu süre uyarısı
        "meeting",
        "walking",
        "reflection",
        "focus_idea",  # aktif odakta anlık fikir (deep modda da)
        "focus_debrief",  # blok bitişi: "nasıl geçti?" sesli log
    }
)


def normalize_recording_type(value: str) -> str:
    v = (value or "quick_note").strip().lower()
    if v not in VALID_RECORDING_TYPES:
        return "quick_note"
    return v
