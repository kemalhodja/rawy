from app.config import settings


class GoogleCalendarService:
    """
    Lightweight placeholder for 2-way Google Calendar sync.
    Real OAuth token storage and webhook sync can be added incrementally.
    """

    def is_enabled(self) -> bool:
        return bool(settings.GOOGLE_CALENDAR_ENABLED and settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)

    def push_event(self, *, title: str, start_time, end_time, user_id: int) -> dict:
        if not self.is_enabled():
            return {"synced": False, "reason": "google_calendar_disabled"}
        # Placeholder integration point.
        return {"synced": False, "reason": "not_implemented"}

    def pull_updates(self, *, user_id: int) -> dict:
        if not self.is_enabled():
            return {"synced": False, "reason": "google_calendar_disabled", "items": []}
        # Placeholder integration point.
        return {"synced": False, "reason": "not_implemented", "items": []}


google_calendar_service = GoogleCalendarService()
