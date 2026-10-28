import json
from app.workers.tasks import send_booking_notification
from uuid import UUID
from app.core.cache import invalidate_doctor_availability

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles, get_current_user
from app.models.doctor import AvailabilitySlot, Doctor
from app.models.consultation import Consultation
from app.models.prescription import Prescription
from app.models.audit import AuditLog


router = APIRouter(
    prefix="/consultations",
    tags=["Consultations"],
)


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class BookingIn(BaseModel):
    doctor_id: UUID
    slot_id: UUID
    reason: str


class MedicineIn(BaseModel):
    name: str
    dose: str
    frequency: str
    duration: str

    @field_validator("name", "dose", "frequency", "duration")
    @classmethod
    def validate_text(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("Field cannot be empty")

        if len(value) > 200:
            raise ValueError("Field is too long")

        return value


class PrescriptionIn(BaseModel):
    medicines: list[MedicineIn]
    instructions: str = ""

    @field_validator("medicines")
    @classmethod
    def validate_medicines(cls, value):
        if not value:
            raise ValueError("At least one medicine is required")

        if len(value) > 50:
            raise ValueError("Maximum 50 medicines allowed")

        return value

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value):
        value = value.strip()

        if len(value) > 2000:
            raise ValueError("Instructions are too long")

        return value


# ============================================================
# BOOK CONSULTATION
# ============================================================

@router.post("")
async def book(
    data: BookingIn,
    idempotency_key: str | None = Header(
        None,
        alias="Idempotency-Key",
    ),
    user=Depends(require_roles("PATIENT")),
    db: AsyncSession = Depends(get_db),
):
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required",
        )

    existing = (
        await db.execute(
            select(Consultation)
            .where(
                Consultation.patient_id == user.id,
                Consultation.slot_id == data.slot_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        return {
            "id": str(existing.id),
            "status": existing.status,
            "idempotent": True,
        }

    slot = (
        await db.execute(
            select(AvailabilitySlot)
            .where(AvailabilitySlot.id == data.slot_id)
            .with_for_update()
        )
    ).scalar_one_or_none()

    if not slot or slot.doctor_id != data.doctor_id:
        raise HTTPException(
            status_code=404,
            detail="Slot not found",
        )

    if slot.status != "AVAILABLE":
        raise HTTPException(
            status_code=409,
            detail="Slot is no longer available",
        )

    consultation = Consultation(
        patient_id=user.id,
        doctor_id=data.doctor_id,
        slot_id=data.slot_id,
        reason=data.reason,
        status="BOOKED",
    )

    slot.status = "BOOKED"

    db.add(consultation)

    await db.flush()

    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="BOOKING_CREATED",
            resource_type="consultation",
            resource_id=str(consultation.id),
            metadata_json=json.dumps(
                {
                    "idempotency_key": idempotency_key,
                }
            ),
        )
    )

    await db.commit()

    await invalidate_doctor_availability(data.doctor_id)

    send_booking_notification.delay(str(consultation.id))

    return {
        "id": str(consultation.id),
        "status": consultation.status,
    }


# ============================================================
# LIST CONSULTATIONS
# ============================================================

@router.get("")
async def my_consultations(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role == "PATIENT":
        rows = (
            await db.execute(
                select(Consultation)
                .where(
                    Consultation.patient_id == user.id
                )
            )
        ).scalars().all()

    elif user.role == "DOCTOR":
        doctor = (
            await db.execute(
                select(Doctor)
                .where(
                    Doctor.user_id == user.id
                )
            )
        ).scalar_one_or_none()

        if not doctor:
            return []

        rows = (
            await db.execute(
                select(Consultation)
                .where(
                    Consultation.doctor_id == doctor.id
                )
            )
        ).scalars().all()

    else:
        rows = (
            await db.execute(
                select(Consultation)
            )
        ).scalars().all()

    return [
        {
            "id": str(x.id),
            "status": x.status,
            "reason": x.reason,
            "doctor_id": str(x.doctor_id),
            "patient_id": str(x.patient_id),
        }
        for x in rows
    ]


# ============================================================
# START CONSULTATION
# ============================================================

@router.post("/{consultation_id}/start")
async def start(
    consultation_id: UUID,
    user=Depends(require_roles("DOCTOR")),
    db: AsyncSession = Depends(get_db),
):
    consultation = await db.get(
        Consultation,
        consultation_id,
    )

    if not consultation:
        raise HTTPException(
            status_code=404,
            detail="Consultation not found",
        )

    if consultation.status != "CONFIRMED":
        raise HTTPException(
            status_code=409,
            detail="Consultation cannot be started",
        )

    doctor = await db.get(
        Doctor,
        consultation.doctor_id,
    )

    if not doctor or doctor.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Not assigned to this consultation",
        )

    consultation.status = "IN_PROGRESS"

    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="CONSULTATION_STARTED",
            resource_type="consultation",
            resource_id=str(consultation.id),
            metadata_json=json.dumps({}),
        )
    )

    await db.commit()

    return {
        "id": str(consultation.id),
        "status": consultation.status,
    }


# ============================================================
# COMPLETE CONSULTATION
# ============================================================

@router.post("/{consultation_id}/complete")
async def complete(
    consultation_id: UUID,
    user=Depends(require_roles("DOCTOR")),
    db: AsyncSession = Depends(get_db),
):
    consultation = await db.get(
        Consultation,
        consultation_id,
    )

    if not consultation:
        raise HTTPException(
            status_code=404,
            detail="Consultation not found",
        )

    if consultation.status != "IN_PROGRESS":
        raise HTTPException(
            status_code=409,
            detail="Consultation cannot be completed",
        )

    doctor = await db.get(
        Doctor,
        consultation.doctor_id,
    )

    if not doctor or doctor.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Not assigned to this consultation",
        )

    consultation.status = "COMPLETED"

    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="CONSULTATION_COMPLETED",
            resource_type="consultation",
            resource_id=str(consultation.id),
            metadata_json=json.dumps({}),
        )
    )

    await db.commit()

    return {
        "id": str(consultation.id),
        "status": consultation.status,
    }


# ============================================================
# CREATE PRESCRIPTION
# ============================================================

@router.post("/{consultation_id}/prescription")
async def prescription(
    consultation_id: UUID,
    data: PrescriptionIn,
    user=Depends(require_roles("DOCTOR")),
    db: AsyncSession = Depends(get_db),
):
    # --------------------------------------------------------
    # 1. Find consultation
    # --------------------------------------------------------

    consultation = await db.get(
        Consultation,
        consultation_id,
    )

    if not consultation:
        raise HTTPException(
            status_code=404,
            detail="Consultation not found",
        )

    # --------------------------------------------------------
    # 2. Find assigned doctor
    # --------------------------------------------------------

    doctor = await db.get(
        Doctor,
        consultation.doctor_id,
    )

    if not doctor:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found",
        )

    # --------------------------------------------------------
    # 3. Ownership check
    # --------------------------------------------------------

    if doctor.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You are not assigned to this consultation",
        )

    # --------------------------------------------------------
    # 4. Consultation state validation
    # --------------------------------------------------------

    if consultation.status not in {
        "COMPLETED",
        "CLOSED",
    }:
        raise HTTPException(
            status_code=409,
            detail="Complete consultation before creating prescription",
        )

    # --------------------------------------------------------
    # 5. Prevent duplicate prescription
    # --------------------------------------------------------

    existing = (
        await db.execute(
            select(Prescription)
            .where(
                Prescription.consultation_id
                == consultation.id
            )
        )
    ).scalar_one_or_none()

    if existing:
        return {
            "id": str(existing.id),
            "consultation_id": str(
                consultation.id
            ),
            "status": "CLOSED",
            "existing": True,
        }

    # --------------------------------------------------------
    # 6. Create prescription
    # --------------------------------------------------------

    prescription_record = Prescription(
        consultation_id=consultation.id,
        medicines=json.dumps(
            [
                medicine.model_dump()
                for medicine in data.medicines
            ]
        ),
        instructions=data.instructions,
    )

    # --------------------------------------------------------
    # 7. Close consultation
    # --------------------------------------------------------

    consultation.status = "CLOSED"

    db.add(prescription_record)

    # --------------------------------------------------------
    # 8. Audit log
    # --------------------------------------------------------

    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="PRESCRIPTION_CREATED",
            resource_type="prescription",
            resource_id=str(
                prescription_record.id
            ),
            metadata_json=json.dumps(
                {
                    "consultation_id": str(
                        consultation.id
                    ),
                    "medicine_count": len(
                        data.medicines
                    ),
                }
            ),
        )
    )

    # --------------------------------------------------------
    # 9. Commit
    # --------------------------------------------------------

    await db.commit()

    await db.refresh(
        prescription_record
    )

    return {
        "id": str(
            prescription_record.id
        ),
        "consultation_id": str(
            consultation.id
        ),
        "status": consultation.status,
        "existing": False,
    }
