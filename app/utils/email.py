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


def send_password_reset_email(to_email: str, full_name: str, token: str) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1e293b;">
  <h2 style="margin-bottom:8px;">Reset your password</h2>
  <p>Hi {full_name},</p>
  <p>We received a request to reset the password for your <strong>{settings.EMAIL_FROM_NAME}</strong> account.
     Click the button below to choose a new password:</p>
  <p style="text-align:center;margin:32px 0;">
    <a href="{reset_url}"
       style="background:#dc2626;color:#fff;padding:14px 28px;border-radius:10px;text-decoration:none;font-weight:600;font-size:15px;">
      Reset Password
    </a>
  </p>
  <p style="font-size:13px;color:#64748b;">
    Or copy and paste this link into your browser:<br>
    <a href="{reset_url}" style="color:#2563eb;">{reset_url}</a>
  </p>
  <p style="font-size:13px;color:#64748b;">
    This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.
    If you did not request a password reset, you can safely ignore this email — your password will not change.
  </p>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Reset your {settings.EMAIL_FROM_NAME} password"
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.GMAIL_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
        server.sendmail(settings.GMAIL_USER, to_email, msg.as_string())


def send_manager_invite_email(to_email: str, full_name: str, temp_password: str, token: str) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return

    activate_url = f"{settings.FRONTEND_URL}/manager-activate?token={token}"

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#1e293b;">
  <h2 style="margin-bottom:8px;">You've been added as a Manager</h2>
  <p>Hi {full_name},</p>
  <p>An admin has set up a manager account for you at <strong>{settings.EMAIL_FROM_NAME}</strong>.
     Click the button below to activate your account and set a new password.</p>
  <p style="text-align:center;margin:32px 0;">
    <a href="{activate_url}"
       style="background:#0f172a;color:#fff;padding:14px 28px;border-radius:10px;text-decoration:none;font-weight:600;font-size:15px;">
      Activate My Account
    </a>
  </p>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-bottom:24px;">
    <p style="margin:0 0 6px;font-size:13px;color:#64748b;">Your temporary credentials:</p>
    <p style="margin:0;font-size:14px;"><strong>Email:</strong> {to_email}</p>
    <p style="margin:4px 0 0;font-size:14px;"><strong>Temporary password:</strong> <code style="background:#e2e8f0;padding:2px 6px;border-radius:4px;">{temp_password}</code></p>
  </div>
  <p style="font-size:13px;color:#64748b;">
    Or copy and paste this link into your browser:<br>
    <a href="{activate_url}" style="color:#2563eb;">{activate_url}</a>
  </p>
  <p style="font-size:13px;color:#64748b;">
    This invitation link expires in {settings.MANAGER_INVITE_TOKEN_EXPIRE_HOURS} hours.
    You will be required to set a new password after activating your account.
  </p>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your {settings.EMAIL_FROM_NAME} manager account is ready"
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.GMAIL_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
        server.sendmail(settings.GMAIL_USER, to_email, msg.as_string())
