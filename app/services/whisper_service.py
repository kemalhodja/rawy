from pathlib import Path

from faster_whisper import WhisperModel

from app.config import settings


class WhisperService:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def _load_model(cls) -> None:
        if cls._model is None:
            cls._model = WhisperModel(
                settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
            )

    def transcribe(self, audio_path: str, language: str | None = None) -> dict:
        self._load_model()
        kw: dict = dict(
            beam_size=5,
            best_of=5,
            condition_on_previous_text=True,
        )
        if language and language.strip().lower() not in ("", "auto", "detect"):
            # faster-whisper: ISO 639-1 (örn. tr, en); 100+ dil Whisper ile uyumlu
            kw["language"] = language.strip().lower()[:16]
        segments, info = self._model.transcribe(audio_path, **kw)

        full_text: list[str] = []
        avg_confidence: list[float] = []

        for segment in segments:
            full_text.append(segment.text.strip())
            lp = getattr(segment, "avg_logprob", None)
            if lp is not None:
                avg_confidence.append(lp)

        text = " ".join(full_text)

        if avg_confidence:
            confidence = sum(avg_confidence) / len(avg_confidence)
            confidence = max(0.0, min(1.0, (confidence + 1) / 2))
        else:
            confidence = 0.0

        return {
            "text": text,
            "language": info.language,
            "confidence": round(confidence, 3),
            "duration": info.duration,
            "segments": len(full_text),
        }


whisper_service = WhisperService()
