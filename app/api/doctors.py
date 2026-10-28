import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import invalidate_doctor_availability
from app.core.database import get_db
from app.core.redis import redis_client
from app.core.security import require_roles
from app.models.doctor import AvailabilitySlot, Doctor

router = APIRouter(
    prefix="/doctors",
    tags=["Doctors"],
)


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class DoctorIn(BaseModel):
    specialization: str = Field(
        min_length=2,
        max_length=120,
    )
    license_number: str = Field(
        min_length=2,
        max_length=100,
    )
    experience_years: int = Field(
        default=0,
        ge=0,
        le=70,
    )
    bio: str = Field(
        default="",
        max_length=1000,
    )

    @field_validator(
        "specialization",
        "license_number",
    )
    @classmethod
    def clean_text(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("Field cannot be empty")

        return value


class SlotIn(BaseModel):
    start_time: datetime
    end_time: datetime

    @field_validator("end_time")
    @classmethod
    def validate_time(cls, value, info):
        start_time = info.data.get("start_time")

        if start_time and value <= start_time:
            raise ValueError(
                "end_time must be after start_time"
            )

        return value


# ============================================================
# SEARCH / FILTER DOCTORS
# ============================================================

@router.get("")
async def search_doctors(
    specialization: str | None = Query(
        default=None,
        min_length=2,
        max_length=120,
        description="Filter by specialization",
    ),
    verified: bool | None = Query(
        default=None,
        description="Filter verified doctors",
    ),
    min_experience: int | None = Query(
        default=None,
        ge=0,
        le=70,
        description="Minimum experience in years",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of doctors per page",
    ),
    db: AsyncSession = Depends(get_db),
):
    # --------------------------------------------------------
    # Base query
    # --------------------------------------------------------

    filters = []

    if specialization:
        filters.append(
            Doctor.specialization.ilike(
                f"%{specialization.strip()}%"
            )
        )

    if verified is not None:
        filters.append(
            Doctor.is_verified == verified
        )

    if min_experience is not None:
        filters.append(
            Doctor.experience_years >= min_experience
        )

    # --------------------------------------------------------
    # Count total matching doctors
    # --------------------------------------------------------

    count_stmt = select(
        func.count(Doctor.id)
    )

    if filters:
        count_stmt = count_stmt.where(*filters)

    total = (
        await db.execute(count_stmt)
    ).scalar_one()

    # --------------------------------------------------------
    # Pagination
    # --------------------------------------------------------

    offset = (page - 1) * page_size

    stmt = (
        select(Doctor)
        .where(*filters)
        .order_by(
            Doctor.is_verified.desc(),
            Doctor.experience_years.desc(),
            Doctor.id,
        )
        .offset(offset)
        .limit(page_size)
    )

    doctors = (
        await db.execute(stmt)
    ).scalars().all()

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "data": [
            {
                "id": str(doctor.id),
                "specialization": doctor.specialization,
                "experience_years": doctor.experience_years,
                "verified": doctor.is_verified,
                "bio": doctor.bio,
            }
            for doctor in doctors
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (
                (total + page_size - 1)
                // page_size
            ),
            "has_next": (
                page * page_size < total
            ),
            "has_previous": page > 1,
        },
    }


# ============================================================
# CREATE DOCTOR
# ============================================================

@router.post("")
async def create_doctor(
    data: DoctorIn,
    user=Depends(require_roles("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    # Prevent duplicate doctor profile for same user
    existing = (
        await db.execute(
            select(Doctor)
            .where(
                Doctor.user_id == user.id
            )
        )
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Doctor profile already exists",
        )

    # Prevent duplicate license number
    existing_license = (
        await db.execute(
            select(Doctor)
            .where(
                Doctor.license_number
                == data.license_number
            )
        )
    ).scalar_one_or_none()

    if existing_license:
        raise HTTPException(
            status_code=409,
            detail="License number already registered",
        )

    doctor = Doctor(
        user_id=user.id,
        **data.model_dump(),
    )

    db.add(doctor)

    await db.commit()
    await db.refresh(doctor)

    return {
        "id": str(doctor.id),
        "specialization": doctor.specialization,
        "experience_years": doctor.experience_years,
        "verified": doctor.is_verified,
    }


# ============================================================
# CREATE AVAILABILITY SLOT
# ============================================================

@router.post("/{doctor_id}/availability")
async def create_slot(
    doctor_id: UUID,
    data: SlotIn,
    user=Depends(
        require_roles("DOCTOR", "ADMIN")
    ),
    db: AsyncSession = Depends(get_db),
):
    doctor = await db.get(
        Doctor,
        doctor_id,
    )

    if not doctor:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found",
        )

    # Doctor can only modify own availability
    if (
        user.role == "DOCTOR"
        and doctor.user_id != user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Cannot manage another doctor's availability",
        )

    # Prevent duplicate start time
    existing = (
        await db.execute(
            select(AvailabilitySlot)
            .where(
                AvailabilitySlot.doctor_id
                == doctor_id,
                AvailabilitySlot.start_time
                == data.start_time,
            )
        )
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Availability slot already exists",
        )

    slot = AvailabilitySlot(
        doctor_id=doctor_id,
        start_time=data.start_time,
        end_time=data.end_time,
        status="AVAILABLE",
    )

    db.add(slot)

    await db.commit()
    await db.refresh(slot)

    # Invalidate cached availability for this doctor
    await invalidate_doctor_availability(doctor_id)

    return {
        "id": str(slot.id),
        "doctor_id": str(slot.doctor_id),
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "status": slot.status,
    }


# ============================================================
# LIST DOCTOR AVAILABILITY
# ============================================================

@router.get("/{doctor_id}/availability")
async def list_slots(
    doctor_id: UUID,
    status: str | None = Query(
        default=None,
        description="Filter by slot status",
    ),
    db: AsyncSession = Depends(get_db),
):
    doctor = await db.get(
        Doctor,
        doctor_id,
    )

    if not doctor:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found",
        )

    filters = [
        AvailabilitySlot.doctor_id
        == doctor_id
    ]

    if status:
        status = status.upper()

        if status not in {
            "AVAILABLE",
            "BOOKED",
        }:
            raise HTTPException(
                status_code=400,
                detail="Invalid slot status",
            )

        filters.append(
            AvailabilitySlot.status
            == status
        )

    cache_status = status or "all"
    cache_key = (
        f"doctor:availability:{doctor_id}:{cache_status}"
    )

    # Try Redis cache first
    cached = await redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    rows = (
        await db.execute(
            select(AvailabilitySlot)
            .where(*filters)
            .order_by(
                AvailabilitySlot.start_time
            )
        )
    ).scalars().all()

    response = {
        "doctor_id": str(doctor_id),
        "count": len(rows),
        "data": [
            {
                "id": str(slot.id),
                "start_time": slot.start_time.isoformat(),
                "end_time": slot.end_time.isoformat(),
                "status": slot.status,
            }
            for slot in rows
        ],
    }

    # Cache for 60 seconds
    print(f"CACHE DEBUG KEY: {cache_key}")
    print(f"CACHE DEBUG BEFORE: {await redis_client.get(cache_key)}")

    await redis_client.setex(
        cache_key,
        60,
        json.dumps(response),
    )

    print(f"CACHE DEBUG AFTER: {await redis_client.get(cache_key)}")
    print(f"CACHE DEBUG TTL: {await redis_client.ttl(cache_key)}")

    return response
