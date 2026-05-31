import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


def verify_recaptcha(token: str) -> bool:
    if not settings.RECAPTCHA_ENABLED:
        return True
    if not settings.RECAPTCHA_SECRET_KEY:
        logger.warning("RECAPTCHA_SECRET_KEY not set — skipping verification")
        return True
    if not token:
        return False

    try:
        response = httpx.post(
            _VERIFY_URL,
            data={"secret": settings.RECAPTCHA_SECRET_KEY, "response": token},
            timeout=5.0,
        )
        result = response.json()
        return bool(result.get("success"))
    except Exception as exc:
        logger.error("reCAPTCHA verification error: %s", exc)
        return False
