import pytest

from app.services.notifications import NotificationService


@pytest.mark.asyncio
async def test_gmail_notification_dry_run_without_credentials():
    result = await NotificationService().send("gmail", "subject", "body")

    assert result.channel == "gmail"
    assert result.status == "dry_run"

