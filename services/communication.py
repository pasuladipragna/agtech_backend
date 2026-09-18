"""
Smart AgriTech Rover — Communication Service
Handles email and SMS delivery for farmer account activation and notifications.
Providers are replaceable via the CommunicationService abstraction.
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


# ── Abstract Providers ─────────────────────────────────────────

class EmailProvider(ABC):
    @abstractmethod
    def send(self, to_email: str, subject: str, body_text: str, body_html: str = "") -> bool:
        pass


class SMSProvider(ABC):
    @abstractmethod
    def send(self, to_phone: str, message: str) -> bool:
        pass


# ── SMTP Email Provider ────────────────────────────────────────

class SMTPEmailProvider(EmailProvider):
    def __init__(self):
        import smtplib
        self.smtp_host = os.getenv("EMAIL_SMTP_HOST", "")
        self.smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.smtp_user = os.getenv("EMAIL_SMTP_USER", "")
        self.smtp_password = os.getenv("EMAIL_SMTP_PASSWORD", "")
        self.from_email = os.getenv("EMAIL_FROM", "noreply@smartagritech.com")
        self.from_name = os.getenv("EMAIL_FROM_NAME", "Smart AgriTech Rover")

    def send(self, to_email: str, subject: str, body_text: str, body_html: str = "") -> bool:
        if not self.smtp_host or not self.smtp_user:
            logger.warning("[Email] SMTP not configured — email not sent to %s", to_email)
            return False

        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email

            msg.attach(MIMEText(body_text, "plain"))
            if body_html:
                msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())

            logger.info("[Email] Sent to %s: %s", to_email, subject)
            return True

        except Exception as e:
            logger.error("[Email] Failed to send to %s: %s", to_email, str(e))
            return False


# ── Twilio SMS Provider ────────────────────────────────────────

class TwilioSMSProvider(SMSProvider):
    def __init__(self):
        self.account_sid = os.getenv("SMS_TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("SMS_TWILIO_AUTH_TOKEN", "")
        self.from_phone = os.getenv("SMS_FROM_PHONE", "")

    def send(self, to_phone: str, message: str) -> bool:
        if not self.account_sid or not self.auth_token or not self.from_phone:
            logger.warning("[SMS] Twilio not configured — SMS not sent to %s", to_phone)
            return False

        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)
            client.messages.create(body=message, from_=self.from_phone, to=to_phone)
            logger.info("[SMS] Sent to %s", to_phone)
            return True
        except Exception as e:
            logger.error("[SMS] Failed to send to %s: %s", to_phone, str(e))
            return False


# ── Fallback Console Providers (Dev Only) ─────────────────────

class ConsoleEmailProvider(EmailProvider):
    """Development only — prints emails to console instead of sending."""
    def send(self, to_email: str, subject: str, body_text: str, body_html: str = "") -> bool:
        logger.info(
            "[DEV EMAIL - NOT SENT]\n"
            "  To: %s\n  Subject: %s\n  Body:\n%s",
            to_email, subject, body_text
        )
        return False  # Returns False so admin sees it as "not sent" in prod-like mode


class ConsoleSMSProvider(SMSProvider):
    """Development only — prints SMS to console."""
    def send(self, to_phone: str, message: str) -> bool:
        logger.info("[DEV SMS - NOT SENT]\n  To: %s\n  Message: %s", to_phone, message)
        return False


# ── Communication Service ──────────────────────────────────────

class CommunicationService:
    """
    High-level communication service.
    Uses injected providers so email/SMS can be swapped without changing business logic.
    """

    def __init__(self, email_provider: EmailProvider, sms_provider: SMSProvider):
        self.email = email_provider
        self.sms = sms_provider

    def send_activation_email(
        self,
        to_email: str,
        full_name: str,
        temp_password: str,
        activation_token: str,
    ) -> bool:
        """Send farmer account activation email with temporary password."""
        app_url = os.getenv("NEXT_PUBLIC_APP_URL", "http://localhost:3000")
        login_url = f"{app_url}/login"

        subject = "Your Smart AgriTech Rover Account is Ready"
        body_text = f"""
Hello {full_name},

Your registration has been approved! Your Smart AgriTech Rover account is now active.

Login Details:
  Website: {login_url}
  Email: {to_email}
  Temporary Password: {temp_password}

IMPORTANT: You will be asked to create a new password when you log in for the first time.

If you have any questions, please contact our support team.

Smart AgriTech Rover Platform
        """.strip()

        body_html = f"""
<html><body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
  <div style="background: #3d8c42; padding: 20px; border-radius: 8px 8px 0 0;">
    <h1 style="color: white; margin: 0; font-size: 22px;">Smart AgriTech Rover</h1>
  </div>
  <div style="background: #fff; padding: 30px; border: 1px solid #e8e0d0; border-top: none; border-radius: 0 0 8px 8px;">
    <p>Hello <strong>{full_name}</strong>,</p>
    <p>Your registration has been approved! Your Smart AgriTech Rover account is now active.</p>
    <div style="background: #f0f7f0; border: 1px solid #b9dcbb; border-radius: 6px; padding: 16px; margin: 20px 0;">
      <p style="margin: 0 0 8px 0; font-weight: bold; color: #2f7035;">Your Login Details:</p>
      <p style="margin: 4px 0;">📧 Email: <strong>{to_email}</strong></p>
      <p style="margin: 4px 0;">🔑 Temporary Password: <strong style="font-family: monospace; font-size: 16px;">{temp_password}</strong></p>
    </div>
    <p style="color: #c4521f;"><strong>⚠️ Important:</strong> You will be asked to create a new password when you log in for the first time.</p>
    <div style="text-align: center; margin: 28px 0;">
      <a href="{login_url}" style="background: #3d8c42; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 15px;">Go to Login Page</a>
    </div>
    <p style="color: #888; font-size: 13px;">If you did not request this account, please ignore this email.</p>
  </div>
</body></html>
        """
        return self.email.send(to_email, subject, body_text, body_html)

    def send_activation_sms(
        self,
        to_phone: str,
        full_name: str,
        temp_password: str,
    ) -> bool:
        """Send farmer account activation SMS."""
        app_url = os.getenv("NEXT_PUBLIC_APP_URL", "http://localhost:3000")
        message = (
            f"Smart AgriTech: Hello {full_name}! Your account is approved. "
            f"Login at {app_url}/login — Email: your registered email, "
            f"Temp Password: {temp_password}. Change your password after first login."
        )
        return self.sms.send(to_phone, message)

    def send_notification_email(
        self, to_email: str, subject: str, body: str
    ) -> bool:
        return self.email.send(to_email, subject, body)

    def send_notification_sms(self, to_phone: str, message: str) -> bool:
        return self.sms.send(to_phone, message)


# ── Factory ────────────────────────────────────────────────────

def create_communication_service() -> CommunicationService:
    """
    Create the communication service with appropriate providers.
    In development (no SMTP config), uses console providers that log but don't send.
    In production, uses real SMTP + Twilio.
    """
    env = os.getenv("ENV", "development")

    smtp_configured = bool(os.getenv("EMAIL_SMTP_HOST"))
    sms_configured = bool(os.getenv("SMS_TWILIO_ACCOUNT_SID"))

    email_provider = SMTPEmailProvider() if smtp_configured else ConsoleEmailProvider()
    sms_provider = TwilioSMSProvider() if sms_configured else ConsoleSMSProvider()

    if env == "development":
        if not smtp_configured:
            logger.info("[Communication] No SMTP config — using console email (dev mode)")
        if not sms_configured:
            logger.info("[Communication] No SMS config — using console SMS (dev mode)")

    return CommunicationService(email_provider, sms_provider)


# Singleton
communication_service = create_communication_service()
