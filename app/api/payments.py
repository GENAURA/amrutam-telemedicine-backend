import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.audit import AuditLog
from app.models.consultation import Consultation
from app.models.payment import Payment

router = APIRouter(
    prefix="/payments",
    tags=["Payments"],
)


# ============================================================
# REQUEST SCHEMA
# ============================================================

class PaymentCreateIn(BaseModel):
    consultation_id: uuid.UUID

    amount: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2,
    )

    currency: str = Field(
        default="INR",
        min_length=3,
        max_length=3,
    )


# ============================================================
# CREATE PAYMENT
# ============================================================

@router.post("")
async def create_payment(
    data: PaymentCreateIn,
    idempotency_key: str | None = Header(
        None,
        alias="Idempotency-Key",
    ),
    user=Depends(require_roles("PATIENT")),
    db: AsyncSession = Depends(get_db),
):
    # --------------------------------------------------------
    # Idempotency key is mandatory
    # --------------------------------------------------------

    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required",
        )

    idempotency_key = idempotency_key.strip()

    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key cannot be empty",
        )

    if len(idempotency_key) > 255:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key is too long",
        )

    # --------------------------------------------------------
    # Return existing payment for same idempotency key
    # --------------------------------------------------------

    existing = (
        await db.execute(
            select(Payment)
            .where(
                Payment.idempotency_key
                == idempotency_key
            )
        )
    ).scalar_one_or_none()

    if existing:
        return {
            "id": str(existing.id),
            "consultation_id": str(
                existing.consultation_id
            ),
            "amount": str(existing.amount),
            "currency": existing.currency,
            "status": existing.status,
            "provider": existing.provider,
            "provider_payment_id": (
                existing.provider_payment_id
            ),
            "idempotent": True,
        }

    # --------------------------------------------------------
    # Verify consultation
    # --------------------------------------------------------

    consultation = await db.get(
        Consultation,
        data.consultation_id,
    )

    if not consultation:
        raise HTTPException(
            status_code=404,
            detail="Consultation not found",
        )

    # --------------------------------------------------------
    # Patient ownership check
    # --------------------------------------------------------

    if consultation.patient_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Cannot pay for another patient's consultation",
        )

    # --------------------------------------------------------
    # Check whether consultation already has payment
    # --------------------------------------------------------

    existing_consultation_payment = (
        await db.execute(
            select(Payment)
            .where(
                Payment.consultation_id
                == consultation.id
            )
        )
    ).scalar_one_or_none()

    if existing_consultation_payment:
        raise HTTPException(
            status_code=409,
            detail="Payment already exists for this consultation",
        )

    # --------------------------------------------------------
    # Validate currency
    # --------------------------------------------------------

    currency = data.currency.upper()

    if currency != "INR":
        raise HTTPException(
            status_code=400,
            detail="Only INR payments are supported",
        )

    # --------------------------------------------------------
    # Create payment
    # --------------------------------------------------------

    payment = Payment(
        consultation_id=consultation.id,
        patient_id=user.id,
        amount=data.amount,
        currency=currency,
        status="PENDING",
        idempotency_key=idempotency_key,
        provider="MOCK",
    )

    db.add(payment)

    await db.flush()

    # --------------------------------------------------------
    # Audit
    # --------------------------------------------------------

    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="PAYMENT_CREATED",
            resource_type="payment",
            resource_id=str(payment.id),
            metadata_json=(
                '{"status":"PENDING","provider":"MOCK"}'
            ),
        )
    )

    await db.commit()

    await db.refresh(payment)

    return {
        "id": str(payment.id),
        "consultation_id": str(
            payment.consultation_id
        ),
        "amount": str(payment.amount),
        "currency": payment.currency,
        "status": payment.status,
        "provider": payment.provider,
        "idempotent": False,
    }


# ============================================================
# CONFIRM PAYMENT
# ============================================================

@router.post("/{payment_id}/confirm")
async def confirm_payment(
    payment_id: uuid.UUID,
    user=Depends(require_roles("PATIENT")),
    db: AsyncSession = Depends(get_db),
):
    payment = await db.get(
        Payment,
        payment_id,
    )

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment not found",
        )

    # --------------------------------------------------------
    # Ownership
    # --------------------------------------------------------

    if payment.patient_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify another patient's payment",
        )

    # --------------------------------------------------------
    # Idempotent confirmation
    # --------------------------------------------------------

    if payment.status == "SUCCESS":
        return {
            "id": str(payment.id),
            "status": payment.status,
            "provider_payment_id": (
                payment.provider_payment_id
            ),
            "idempotent": True,
        }

    if payment.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"Payment cannot be confirmed from {payment.status} state",
        )

    # --------------------------------------------------------
    # Mock provider confirmation
    # --------------------------------------------------------

    payment.status = "SUCCESS"

    payment.provider_payment_id = (
        f"mock_{uuid.uuid4().hex}"
    )

    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="PAYMENT_CONFIRMED",
            resource_type="payment",
            resource_id=str(payment.id),
            metadata_json=(
                '{"status":"SUCCESS","provider":"MOCK"}'
            ),
        )
    )

    await db.commit()

    await db.refresh(payment)

    return {
        "id": str(payment.id),
        "status": payment.status,
        "provider": payment.provider,
        "provider_payment_id": (
            payment.provider_payment_id
        ),
        "idempotent": False,
    }


# ============================================================
# LIST MY PAYMENTS
# ============================================================

@router.get("")
async def list_payments(
    user=Depends(require_roles("PATIENT")),
    db: AsyncSession = Depends(get_db),
):
    payments = (
        await db.execute(
            select(Payment)
            .where(
                Payment.patient_id == user.id
            )
            .order_by(
                Payment.created_at.desc()
            )
        )
    ).scalars().all()

    return {
        "data": [
            {
                "id": str(payment.id),
                "consultation_id": str(
                    payment.consultation_id
                ),
                "amount": str(payment.amount),
                "currency": payment.currency,
                "status": payment.status,
                "provider": payment.provider,
                "provider_payment_id": (
                    payment.provider_payment_id
                ),
                "created_at": payment.created_at,
            }
            for payment in payments
        ],
        "count": len(payments),
    }


# ============================================================
# GET PAYMENT
# ============================================================

@router.get("/{payment_id}")
async def get_payment(
    payment_id: uuid.UUID,
    user=Depends(require_roles("PATIENT")),
    db: AsyncSession = Depends(get_db),
):
    payment = await db.get(
        Payment,
        payment_id,
    )

    if not payment:
        raise HTTPException(
            status_code=404,
            detail="Payment not found",
        )

    if payment.patient_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Cannot access another patient's payment",
        )

    return {
        "id": str(payment.id),
        "consultation_id": str(
            payment.consultation_id
        ),
        "amount": str(payment.amount),
        "currency": payment.currency,
        "status": payment.status,
        "provider": payment.provider,
        "provider_payment_id": (
            payment.provider_payment_id
        ),
        "created_at": payment.created_at,
        "updated_at": payment.updated_at,
    }
