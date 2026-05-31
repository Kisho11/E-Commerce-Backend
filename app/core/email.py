import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.config import settings

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, html_body: str) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        logger.warning("Email not configured — skipping send to %s | Subject: %s", to, subject)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.GMAIL_USER}>"
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
            server.sendmail(settings.GMAIL_USER, to, msg.as_string())
        logger.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)
        raise


def send_email_verification(to: str, full_name: str, token: str) -> None:
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:32px;background:#f9f9f9;border-radius:8px">
      <h2 style="color:#c0392b">Verify your email</h2>
      <p>Hi {full_name},</p>
      <p>Thanks for signing up! Click the button below to verify your email address. This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.</p>
      <a href="{verify_url}" style="display:inline-block;margin:20px 0;padding:12px 28px;background:#c0392b;color:#fff;text-decoration:none;border-radius:6px;font-weight:bold">
        Verify Email
      </a>
      <p style="color:#888;font-size:12px">If you did not create an account, you can safely ignore this email.</p>
    </div>
    """
    _send(to, "Verify your Elamshelf account", html)


def send_password_reset(to: str, full_name: str, token: str) -> None:
    reset_url = f"{settings.FRONTEND_URL}/login?mode=customer-signin&resetToken={token}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:32px;background:#f9f9f9;border-radius:8px">
      <h2 style="color:#c0392b">Reset your password</h2>
      <p>Hi {full_name},</p>
      <p>We received a request to reset your password. Click the button below. This link expires in 15 minutes.</p>
      <a href="{reset_url}" style="display:inline-block;margin:20px 0;padding:12px 28px;background:#c0392b;color:#fff;text-decoration:none;border-radius:6px;font-weight:bold">
        Reset Password
      </a>
      <p style="color:#888;font-size:12px">If you did not request a password reset, you can safely ignore this email.</p>
    </div>
    """
    _send(to, "Reset your Elamshelf password", html)


def send_manager_welcome(to: str, full_name: str, temp_password: str) -> None:
    login_url = f"{settings.FRONTEND_URL}/login?mode=staff-signin"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:32px;background:#f9f9f9;border-radius:8px">
      <h2 style="color:#c0392b">Welcome to Elamshelf — Manager Account</h2>
      <p>Hi {full_name},</p>
      <p>An administrator has created a manager account for you. Use the credentials below to sign in.</p>
      <table style="margin:16px 0;border-collapse:collapse">
        <tr><td style="padding:6px 12px;font-weight:bold;background:#eee">Email</td><td style="padding:6px 12px">{to}</td></tr>
        <tr><td style="padding:6px 12px;font-weight:bold;background:#eee">Temporary Password</td><td style="padding:6px 12px;font-family:monospace">{temp_password}</td></tr>
      </table>
      <a href="{login_url}" style="display:inline-block;margin:20px 0;padding:12px 28px;background:#c0392b;color:#fff;text-decoration:none;border-radius:6px;font-weight:bold">
        Sign In
      </a>
      <p style="color:#888;font-size:12px">Please change your password after your first login.</p>
    </div>
    """
    _send(to, "Your Elamshelf manager account is ready", html)
