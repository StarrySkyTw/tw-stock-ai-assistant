from fastapi import APIRouter

from app.schemas import NotificationTestRequest, NotificationTestResponse
from app.services.notifications import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/test", response_model=NotificationTestResponse)
async def test_notification(payload: NotificationTestRequest) -> dict:
    result = await NotificationService().send(payload.channel, payload.subject, payload.message)
    return result.to_dict()

