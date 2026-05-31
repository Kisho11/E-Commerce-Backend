import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.config import settings


def send_verification_email(to_email: str, full_name: str, token: str) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return

    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1e293b;">
  <h2 style="margin-bottom:8px;">Verify your email</h2>
  <p>Hi {full_name},</p>
  <p>Thanks for signing up at <strong>{settings.EMAIL_FROM_NAME}</strong>. Click below to verify your email address:</p>
  <p style="text-align:center;margin:32px 0;">
    <a href="{verify_url}"
       style="background:#2563eb;color:#fff;padding:14px 28px;border-radius:10px;text-decoration:none;font-weight:600;font-size:15px;">
      Verify Email Address
    </a>
  </p>
  <p style="font-size:13px;color:#64748b;">
    Or copy and paste this link into your browser:<br>
    <a href="{verify_url}" style="color:#2563eb;">{verify_url}</a>
  </p>
  <p style="font-size:13px;color:#64748b;">
    This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.
    If you did not create an account, you can safely ignore this email.
  </p>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Verify your {settings.EMAIL_FROM_NAME} account"
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.GMAIL_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
        server.sendmail(settings.GMAIL_USER, to_email, msg.as_string())
