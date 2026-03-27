from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "Rawy"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql://rawy:rawy@localhost:5432/rawy"

    # Storage
    UPLOAD_DIR: Path = Path("uploads")
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB

    # Whisper
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    # Widget hızlı kayıt — aşımda quick_capture_exceeded işaretlenir
    QUICK_CAPTURE_MAX_SECONDS: float = 30.0

    # JWT (üretimde SECRET_KEY mutlaka güçlü ve gizli tutulmalı)
    SECRET_KEY: str = "dev-only-change-me-use-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Ajanda / odak blokları
    FOCUS_BLOCK_MIN_HOURS: float = 2.0
    FOCUS_BLOCK_MAX_HOURS: float = 4.0
    CALENDAR_BUFFER_MINUTES: int = 15

    # Monetizasyon (Başlangıç / Pro / Takım)
    TRIAL_DAYS: int = 14
    STARTER_VOICE_MONTHLY_LIMIT: int = 50

    # Google Calendar (opsiyonel 2-way sync)
    GOOGLE_CALENDAR_ENABLED: bool = False
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None

    # Smart AI (Transformers)
    AI_SUMMARY_MODEL: str = "facebook/bart-large-cnn"
    AI_ZERO_SHOT_MODEL: str = "facebook/bart-large-mnli"
    AI_SENTIMENT_MODEL: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"

    # Weekly email report (optional)
    WEEKLY_EMAIL_REPORT_ENABLED: bool = False
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None

    # Billing / Stripe
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_PRO_MONTHLY: str | None = None
    APP_PUBLIC_URL: str = "http://localhost:8000"


settings = Settings()
