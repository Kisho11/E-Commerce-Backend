import json
from urllib import parse, request

from fastapi import HTTPException

from app.config import settings


RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


def verify_recaptcha_token(token: str | None, remote_ip: str | None = None) -> None:
    if not settings.RECAPTCHA_SECRET_KEY:
        return

    if not token:
        raise HTTPException(status_code=400, detail="reCAPTCHA verification required")

    payload = {
        "secret": settings.RECAPTCHA_SECRET_KEY,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    encoded = parse.urlencode(payload).encode("utf-8")
    req = request.Request(RECAPTCHA_VERIFY_URL, data=encoded, method="POST")

    try:
        with request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=502, detail="Unable to verify reCAPTCHA")

    if not result.get("success"):
        raise HTTPException(status_code=400, detail="reCAPTCHA verification failed")
