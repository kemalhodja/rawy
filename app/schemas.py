from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    timezone: str = Field(default="UTC", max_length=64)


class UserProfilePatch(BaseModel):
    timezone: str = Field(..., max_length=64)


class UserOut(BaseModel):
    id: int
    email: str
    plan: str
    is_active: bool
    is_verified: bool = False
    timezone: str
    created_at: datetime | None

    model_config = {"from_attributes": True}


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterOut(BaseModel):
    user: UserOut
    verify_token: str


class RefreshBody(BaseModel):
    refresh_token: str


class FocusBlockCreate(BaseModel):
    title: str = Field(..., max_length=500)
    start_at: datetime
    end_at: datetime
    is_focus: bool = True
    source: str | None = "manual"


class FocusBlockOut(BaseModel):
    id: int
    title: str
    start_at: datetime
    end_at: datetime
    is_focus: bool
    source: str | None = None

    model_config = {"from_attributes": True}


class VoicePlanBody(BaseModel):
    text: str = Field(..., min_length=3, max_length=4000)
    allow_shallow: bool = False


class VoicePlanResult(BaseModel):
    block: FocusBlockOut
    parsed_title: str
    adjusted_for_buffer: bool
    duration_hours: float


class UserAvailabilitySlice(BaseModel):
    user_id: int
    email: str
    timezone: str
    blocks: list[FocusBlockOut]


class AvailabilityMapOut(BaseModel):
    date: str
    default_timezone: str
    team: list[UserAvailabilitySlice]
    note: str | None = None


# ===== REMINDER SCHEMAS =====

class ReminderCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    note: str | None = Field(None, max_length=2000)
    remind_at: datetime
    timezone: str = Field(default="UTC", max_length=64)
    recurrence: str | None = Field(None, pattern="^(daily|weekly|monthly)$")
    recurrence_count: int | None = Field(None, ge=1, le=100)
    notify_methods: list[str] = Field(default=["push"])


class ReminderOut(BaseModel):
    id: int
    user_id: int
    title: str
    note: str | None
    remind_at: datetime
    timezone: str
    recurrence: str | None
    recurrence_count: int | None
    is_triggered: bool
    is_dismissed: bool
    is_snoozed: bool
    snooze_until: datetime | None
    notify_methods: list[str]
    linked_task_id: int | None
    trigger_count: int
    last_triggered_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReminderUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    note: str | None = Field(None, max_length=2000)
    remind_at: datetime | None = None
    recurrence: str | None = Field(None, pattern="^(daily|weekly|monthly)$")
    recurrence_count: int | None = Field(None, ge=1, le=100)


class ReminderSnooze(BaseModel):
    minutes: int = Field(..., ge=5, le=1440)  # 5 dk - 24 saat


class ReminderDismiss(BaseModel):
    dismiss_permanently: bool = Field(default=False)  # True = tekrarlamayı da durdur


class ReminderListOut(BaseModel):
    upcoming: list[ReminderOut]
    overdue: list[ReminderOut]
    today: list[ReminderOut]


class VoiceReminderCommand(BaseModel):
    """Sesle hatırlatıcı komutu"""
    text: str = Field(..., min_length=3, max_length=500)
    timezone: str = Field(default="UTC")
