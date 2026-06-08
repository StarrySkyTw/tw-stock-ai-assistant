from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.core.config import get_settings


@dataclass
class NotificationResult:
    channel: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"channel": self.channel, "status": self.status, "detail": self.detail}


class NotificationService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def send(self, channel: str, subject: str, message: str) -> NotificationResult:
        if channel == "gmail":
            return self._send_email(subject, message)
        if channel == "telegram":
            return await self._send_telegram(message)
        if channel == "line":
            return await self._send_line(message)
        return NotificationResult(channel, "error", "Unsupported notification channel.")

    def _send_email(self, subject: str, body: str) -> NotificationResult:
        missing = [
            name
            for name, value in {
                "SMTP_HOST": self.settings.smtp_host,
                "SMTP_USERNAME": self.settings.smtp_username,
                "SMTP_PASSWORD": self.settings.smtp_password,
                "SMTP_FROM": self.settings.smtp_from,
                "ALERT_EMAIL_TO": self.settings.alert_email_to,
            }.items()
            if not value
        ]
        if missing:
            return NotificationResult("gmail", "dry_run", f"Missing {', '.join(missing)}; email not sent.")

        email = EmailMessage()
        email["Subject"] = subject
        email["From"] = self.settings.smtp_from
        email["To"] = self.settings.alert_email_to
        email.set_content(body)
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as smtp:
                smtp.starttls()
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                smtp.send_message(email)
            return NotificationResult("gmail", "sent", "Email sent.")
        except Exception as exc:
            return NotificationResult("gmail", "error", str(exc))

    async def _send_telegram(self, message: str) -> NotificationResult:
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            return NotificationResult("telegram", "dry_run", "Missing Telegram token or chat id.")
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    url, json={"chat_id": self.settings.telegram_chat_id, "text": message}
                )
                response.raise_for_status()
            return NotificationResult("telegram", "sent", "Telegram message sent.")
        except Exception as exc:
            return NotificationResult("telegram", "error", str(exc))

    async def _send_line(self, message: str) -> NotificationResult:
        if not self.settings.line_channel_access_token or not self.settings.line_to_id:
            return NotificationResult("line", "dry_run", "Missing LINE Messaging API token or recipient id.")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers={"Authorization": f"Bearer {self.settings.line_channel_access_token}"},
                    json={"to": self.settings.line_to_id, "messages": [{"type": "text", "text": message}]},
                )
                response.raise_for_status()
            return NotificationResult("line", "sent", "LINE push message sent.")
        except Exception as exc:
            return NotificationResult("line", "error", str(exc))

