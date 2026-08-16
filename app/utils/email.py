import smtplib
from decimal import Decimal
from html import escape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.config import settings


def _public_asset_url(path: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/{path.lstrip('/')}"


def _email_logo_html(max_width: int = 240) -> str:
    logo_url = escape(_public_asset_url("/elmshelf-logo.png"), quote=True)
    return f"""
  <div style="text-align:center;margin:0 0 22px;">
    <img src="{logo_url}" alt="Elmshelf" width="{max_width}" style="display:inline-block;width:100%;max-width:{max_width}px;height:auto;border:0;">
  </div>"""


def _send_html_email(to_email: str, subject: str, html: str) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.GMAIL_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
        server.sendmail(settings.GMAIL_USER, to_email, msg.as_string())


def send_verification_email(to_email: str, full_name: str, token: str) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return

    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1e293b;">
  {_email_logo_html()}
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


def send_order_confirmation_email(
    to_email: str,
    full_name: str,
    order_id: int,
    total_amount,
    delivery_mode: str,
    delivery_note: str | None,
    address: dict | None,
    items: list[dict],
) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return

    mode_label = "Pickup from store" if delivery_mode == "pickup" else "Ship to address"
    order_url = f"{settings.FRONTEND_URL}/customer-portal"
    total = Decimal(str(total_amount or 0))
    item_rows = "".join(
        f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #e2e8f0;">{escape(str(item.get("name") or "Product"))}</td>
          <td style="padding:10px;border-bottom:1px solid #e2e8f0;text-align:center;">{int(item.get("quantity") or 0)}</td>
          <td style="padding:10px;border-bottom:1px solid #e2e8f0;text-align:right;">£{Decimal(str(item.get("line_total") or 0)):.2f}</td>
        </tr>
        """
        for item in items
    )
    address_lines = []
    if address:
        address_lines = [
            address.get("address_line1"),
            address.get("address_line2"),
            address.get("city"),
            address.get("state"),
            address.get("postal_code"),
            address.get("country"),
        ]
    address_html = "<br>".join(escape(str(line)) for line in address_lines if line)
    if not address_html:
        address_html = "Pickup from store"

    note_html = ""
    if delivery_note:
        note_html = f"""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px;margin-top:16px;">
          <p style="margin:0 0 6px;font-size:13px;color:#64748b;font-weight:700;text-transform:uppercase;">Delivery note</p>
          <p style="margin:0;">{escape(delivery_note)}</p>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:620px;margin:0 auto;padding:24px;color:#1e293b;">
  {_email_logo_html()}
  <h2 style="margin-bottom:8px;">Order confirmed</h2>
  <p>Hi {escape(full_name or "Customer")},</p>
  <p>Thanks for your order at <strong>{escape(settings.EMAIL_FROM_NAME)}</strong>. We have received your order and will process it shortly.</p>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:24px 0;">
    <p style="margin:0 0 8px;"><strong>Order ID:</strong> #{order_id}</p>
    <p style="margin:0 0 8px;"><strong>Delivery:</strong> {mode_label}</p>
    <p style="margin:0;"><strong>Total:</strong> £{total:.2f}</p>
  </div>

  <h3 style="margin-bottom:10px;">Items</h3>
  <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
    <thead>
      <tr style="background:#f1f5f9;">
        <th style="padding:10px;text-align:left;">Product</th>
        <th style="padding:10px;text-align:center;">Qty</th>
        <th style="padding:10px;text-align:right;">Total</th>
      </tr>
    </thead>
    <tbody>{item_rows}</tbody>
  </table>

  <h3 style="margin-bottom:8px;">Delivery details</h3>
  <p style="margin-top:0;">{address_html}</p>
  {note_html}

  <p style="text-align:center;margin:28px 0;">
    <a href="{order_url}"
       style="background:#dc2626;color:#fff;padding:13px 24px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px;">
      View My Orders
    </a>
  </p>
  <p style="font-size:13px;color:#64748b;">
    If you have any questions, reply to this email or contact our support team.
  </p>
</body>
</html>"""

    _send_html_email(to_email, f"Order #{order_id} confirmed", html)


def send_order_status_update_email(
    to_email: str,
    full_name: str,
    order_id: int,
    status: str,
    total_amount,
    delivery_mode: str,
    delivery_note: str | None,
    address: dict | None,
    items: list[dict],
) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return

    status_key = (status or "").strip().lower()
    status_label = status_key.replace("_", " ").title()
    status_messages = {
        "confirmed": "Your order has been confirmed and is being prepared.",
        "shipped": "Your order has been shipped and is on its way.",
        "delivered": "Your order has been marked as delivered. Thank you for shopping with us.",
        "cancelled": "Your order has been cancelled. If you have any questions, please contact our team.",
    }
    message = status_messages.get(status_key, f"Your order status is now {status_label}.")
    order_url = f"{settings.FRONTEND_URL}/customer-portal"
    mode_label = "Pickup from store" if delivery_mode == "pickup" else "Ship to address"
    total = Decimal(str(total_amount or 0))
    item_rows = "".join(
        f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #e2e8f0;">{escape(str(item.get("name") or "Product"))}</td>
          <td style="padding:10px;border-bottom:1px solid #e2e8f0;text-align:center;">{int(item.get("quantity") or 0)}</td>
          <td style="padding:10px;border-bottom:1px solid #e2e8f0;text-align:right;">Â£{Decimal(str(item.get("line_total") or 0)):.2f}</td>
        </tr>
        """
        for item in items
    )

    address_lines = []
    if address:
        address_lines = [
            address.get("address_line1"),
            address.get("address_line2"),
            address.get("city"),
            address.get("state"),
            address.get("postal_code"),
            address.get("country"),
        ]
    address_html = "<br>".join(escape(str(line)) for line in address_lines if line) or "Pickup from store"

    note_html = ""
    if delivery_note:
        note_html = f"""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px;margin-top:16px;">
          <p style="margin:0 0 6px;font-size:13px;color:#64748b;font-weight:700;text-transform:uppercase;">Delivery note</p>
          <p style="margin:0;">{escape(delivery_note)}</p>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:620px;margin:0 auto;padding:24px;color:#1e293b;">
  {_email_logo_html()}
  <p style="margin:0 0 8px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:#dc2626;">Order Update</p>
  <h2 style="margin:0 0 8px;">Order #{order_id}: {escape(status_label)}</h2>
  <p>Hi {escape(full_name or "Customer")},</p>
  <p>{escape(message)}</p>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:24px 0;">
    <p style="margin:0 0 8px;"><strong>Order ID:</strong> #{order_id}</p>
    <p style="margin:0 0 8px;"><strong>Status:</strong> {escape(status_label)}</p>
    <p style="margin:0 0 8px;"><strong>Delivery:</strong> {mode_label}</p>
    <p style="margin:0;"><strong>Total:</strong> Â£{total:.2f}</p>
  </div>

  <h3 style="margin-bottom:10px;">Items</h3>
  <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
    <thead>
      <tr style="background:#f1f5f9;">
        <th style="padding:10px;text-align:left;">Product</th>
        <th style="padding:10px;text-align:center;">Qty</th>
        <th style="padding:10px;text-align:right;">Total</th>
      </tr>
    </thead>
    <tbody>{item_rows}</tbody>
  </table>

  <h3 style="margin-bottom:8px;">Delivery details</h3>
  <p style="margin-top:0;">{address_html}</p>
  {note_html}

  <p style="text-align:center;margin:28px 0;">
    <a href="{order_url}"
       style="background:#dc2626;color:#fff;padding:13px 24px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px;">
      View My Orders
    </a>
  </p>
  <p style="font-size:13px;color:#64748b;">
    If you have any questions, reply to this email or contact our support team.
  </p>
</body>
</html>"""

    _send_html_email(to_email, f"Order #{order_id} {status_label}", html)


def send_cart_reminder_email(
    to_email: str,
    full_name: str,
    items: list[dict],
    total_amount,
) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return

    cart_url = f"{settings.FRONTEND_URL}/cart"
    total = Decimal(str(total_amount or 0))
    item_rows = "".join(
        f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #e2e8f0;">{escape(str(item.get("name") or "Product"))}</td>
          <td style="padding:10px;border-bottom:1px solid #e2e8f0;text-align:center;">{int(item.get("quantity") or 0)}</td>
          <td style="padding:10px;border-bottom:1px solid #e2e8f0;text-align:right;">£{Decimal(str(item.get("line_total") or 0)):.2f}</td>
        </tr>
        """
        for item in items
    )

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:620px;margin:0 auto;padding:24px;color:#1e293b;">
  {_email_logo_html()}
  <h2 style="margin-bottom:8px;">You still have items in your cart</h2>
  <p>Hi {escape(full_name or "Customer")},</p>
  <p>You left some products in your <strong>{escape(settings.EMAIL_FROM_NAME)}</strong> cart. If you still need them, you can return to your cart and complete checkout.</p>

  <table style="width:100%;border-collapse:collapse;margin:22px 0;">
    <thead>
      <tr style="background:#f1f5f9;">
        <th style="padding:10px;text-align:left;">Product</th>
        <th style="padding:10px;text-align:center;">Qty</th>
        <th style="padding:10px;text-align:right;">Total</th>
      </tr>
    </thead>
    <tbody>{item_rows}</tbody>
  </table>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:20px 0;text-align:right;">
    <strong>Cart total: £{total:.2f}</strong>
  </div>

  <p style="text-align:center;margin:28px 0;">
    <a href="{cart_url}"
       style="background:#dc2626;color:#fff;padding:13px 24px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px;">
      Return to Cart
    </a>
  </p>
  <p style="font-size:13px;color:#64748b;">
    This reminder is sent monthly while products remain in your cart.
  </p>
</body>
</html>"""

    _send_html_email(to_email, "Reminder: items are waiting in your cart", html)


def send_marketing_campaign_email(
    to_email: str,
    full_name: str,
    campaign_type: str,
    subject: str,
    message_html: str,
    image_urls: list[str],
    unsubscribe_url: str,
) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return

    website_url = settings.FRONTEND_URL

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;background:#f8fafc;font-family:Arial,sans-serif;color:#1e293b;">
  <div style="max-width:640px;margin:0 auto;padding:24px;">
    <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;">
      <div style="background:#111827;padding:22px 24px;color:#ffffff;">
        {_email_logo_html(260)}
        <p style="margin:0;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:#93c5fd;">{escape(settings.EMAIL_FROM_NAME)}</p>
        <h1 style="margin:8px 0 0;font-size:24px;line-height:1.25;">{escape(subject)}</h1>
      </div>

      <div style="padding:24px;">
        <p style="display:inline-block;margin:0 0 16px;padding:6px 10px;border-radius:999px;background:#fee2e2;color:#991b1b;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;">
          {escape(campaign_type)}
        </p>
        <p style="margin:0 0 16px;">Hi {escape(full_name or "Customer")},</p>
        <div style="font-size:15px;line-height:1.7;color:#334155;">
          {message_html}
        </div>

        <p style="text-align:center;margin:28px 0;">
          <a href="{website_url}"
             style="display:inline-block;background:#dc2626;color:#fff;padding:13px 24px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px;">
            Visit Elmshelf
          </a>
        </p>
      </div>

      <div style="border-top:1px solid #e2e8f0;padding:18px 24px;background:#f8fafc;font-size:12px;line-height:1.6;color:#64748b;">
        <p style="margin:0 0 8px;">You received this because you subscribed to promotions, offers, and event updates from {escape(settings.EMAIL_FROM_NAME)}.</p>
        <p style="margin:0;">
          <a href="{unsubscribe_url}" style="color:#64748b;text-decoration:underline;">Unsubscribe</a>
        </p>
      </div>
    </div>
  </div>
</body>
</html>"""

    _send_html_email(to_email, subject, html)


def send_password_reset_email(to_email: str, full_name: str, token: str) -> None:
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1e293b;">
  {_email_logo_html()}
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
  {_email_logo_html()}
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
