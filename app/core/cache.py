from app.core.redis import redis_client


async def invalidate_doctor_availability(doctor_id):
    await redis_client.delete(
        f"doctor:availability:{doctor_id}:all",
        f"doctor:availability:{doctor_id}:AVAILABLE",
        f"doctor:availability:{doctor_id}:BOOKED",
    )
