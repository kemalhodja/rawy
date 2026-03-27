from __future__ import annotations

from collections import Counter
import re
import smtplib
from email.message import EmailMessage
from typing import Any

from app.config import settings


class SmartAIService:
    def __init__(self) -> None:
        self._summarizer = None
        self._classifier = None
        self._sentiment = None

    def _load_summarizer(self):
        if self._summarizer is not None:
            return self._summarizer
        from transformers import pipeline

        self._summarizer = pipeline("summarization", model=settings.AI_SUMMARY_MODEL)
        return self._summarizer

    def _load_classifier(self):
        if self._classifier is not None:
            return self._classifier
        from transformers import pipeline

        self._classifier = pipeline("zero-shot-classification", model=settings.AI_ZERO_SHOT_MODEL)
        return self._classifier

    def _load_sentiment(self):
        if self._sentiment is not None:
            return self._sentiment
        from transformers import pipeline

        self._sentiment = pipeline("sentiment-analysis", model=settings.AI_SENTIMENT_MODEL)
        return self._sentiment

    @staticmethod
    def _fallback_summary(text: str, max_len: int = 220) -> str:
        t = " ".join((text or "").split())
        if len(t) <= max_len:
            return t
        return t[: max_len - 3] + "..."

    def summarize(self, text: str) -> dict[str, Any]:
        clean = " ".join((text or "").split())
        if not clean:
            return {"summary": "", "model": None, "fallback": True}
        try:
            summarizer = self._load_summarizer()
            out = summarizer(clean[:5000], max_length=130, min_length=30, do_sample=False)
            return {"summary": out[0]["summary_text"], "model": settings.AI_SUMMARY_MODEL, "fallback": False}
        except Exception:
            return {"summary": self._fallback_summary(clean), "model": None, "fallback": True}

    def classify_themes(self, text: str, labels: list[str]) -> dict[str, Any]:
        clean = " ".join((text or "").split())
        if not clean:
            return {"labels": [], "scores": [], "model": None, "fallback": True}
        try:
            clf = self._load_classifier()
            out = clf(clean[:4000], candidate_labels=labels, multi_label=True)
            return {"labels": out.get("labels", []), "scores": out.get("scores", []), "model": settings.AI_ZERO_SHOT_MODEL, "fallback": False}
        except Exception:
            return {"labels": [], "scores": [], "model": None, "fallback": True}

    def sentiment(self, text: str) -> dict[str, Any]:
        clean = " ".join((text or "").split())
        if not clean:
            return {"label": "neutral", "score": 0.0, "fallback": True}
        try:
            pipe = self._load_sentiment()
            out = pipe(clean[:1500])[0]
            label = str(out.get("label", "neutral")).lower()
            # Map to requested buckets: pozitif/negatif/stresli
            if "stress" in label or "anger" in label or "fear" in label:
                mapped = "stresli"
            elif "neg" in label:
                mapped = "negatif"
            elif "pos" in label:
                mapped = "pozitif"
            else:
                mapped = "stresli" if any(k in clean.lower() for k in ("stres", "kaygi", "gergin")) else "pozitif"
            return {"label": mapped, "score": float(out.get("score", 0.0)), "fallback": False}
        except Exception:
            low = clean.lower()
            if any(k in low for k in ("stres", "kaygı", "kaygi", "gergin")):
                return {"label": "stresli", "score": 0.6, "fallback": True}
            if any(k in low for k in ("kötü", "uzgun", "zor", "yorgun")):
                return {"label": "negatif", "score": 0.55, "fallback": True}
            return {"label": "pozitif", "score": 0.55, "fallback": True}

    @staticmethod
    def top_terms(text: str, top_n: int = 10) -> list[tuple[str, int]]:
        tokens = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]{3,}", (text or "").lower())
        stop = {
            "ve", "ile", "için", "icin", "ama", "gibi", "daha", "çok", "cok", "bir", "iki", "üç", "uc",
            "this", "that", "for", "with", "from", "you", "your", "the", "and", "biraz", "sonra", "bugun", "yarin",
        }
        c = Counter(t for t in tokens if t not in stop)
        return c.most_common(top_n)

    def send_weekly_email(self, to_email: str, subject: str, body: str) -> dict[str, Any]:
        if not settings.WEEKLY_EMAIL_REPORT_ENABLED:
            return {"sent": False, "reason": "weekly_email_disabled"}
        if not (settings.SMTP_HOST and settings.SMTP_USERNAME and settings.SMTP_PASSWORD and settings.SMTP_FROM):
            return {"sent": False, "reason": "smtp_not_configured"}
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = settings.SMTP_FROM
            msg["To"] = to_email
            msg.set_content(body)
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
            return {"sent": True}
        except Exception as exc:
            return {"sent": False, "reason": f"smtp_error:{exc.__class__.__name__}"}


smart_ai_service = SmartAIService()
