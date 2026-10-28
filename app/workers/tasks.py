from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "amrutam",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

@celery_app.task
def send_booking_notification(consultation_id: str):
    # Replace with an email/SMS provider in production.
    return {"consultation_id": consultation_id, "sent": True}
