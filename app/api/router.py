from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.consultations import router as consultations_router
from app.api.doctors import router as doctors_router
from app.api.payments import router as payments_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(doctors_router)
api_router.include_router(consultations_router)
api_router.include_router(admin_router)
api_router.include_router(payments_router)
