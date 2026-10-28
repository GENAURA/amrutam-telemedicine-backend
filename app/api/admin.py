from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User
from app.models.consultation import Consultation
from app.models.audit import AuditLog

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/analytics")
async def analytics(user=Depends(require_roles("ADMIN")), db: AsyncSession = Depends(get_db)):
    users = await db.scalar(select(func.count(User.id)))
    consultations = await db.scalar(select(func.count(Consultation.id)))
    completed = await db.scalar(select(func.count(Consultation.id)).where(Consultation.status.in_(["COMPLETED", "CLOSED"])))
    return {"users": users, "consultations": consultations, "completed_consultations": completed}

@router.get("/audit-logs")
async def audit_logs(user=Depends(require_roles("ADMIN")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100))).scalars().all()
    return [{"id": str(x.id), "action": x.action, "resource_type": x.resource_type, "resource_id": x.resource_id, "created_at": x.created_at} for x in rows]
