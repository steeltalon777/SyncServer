from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db, engine
from app.core.config import get_settings
from app.models import Base, Device, Event
from app.repos.site_repo import SiteRepo
from app.repos.device_repo import DeviceRepo
from uuid import UUID
from app.repos.event_repo import EventRepo
from app.schemas.event import PushRequest, PushResponse, EventIn
from datetime import datetime
from typing import List

settings = get_settings()
app = FastAPI(title="Server Sync API")

@app.on_event("startup")
async def startup():
    # Создаём таблицы (только для разработки!)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tables created/verified")
@app.get("/")
async def root():
    return {
        "message": "Server Sync API is running",
        "status": "ok",
        "env": settings.APP_ENV
    }

@app.get("/db_check")
async def db_check(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(text("SELECT 1"))
        return {"db_status":"connected","result":result.scalar()}
    except Exception as e:
        return {"db_status":"error","error":str(e)}
@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.post("/sites/")
async def create_site(code: str, name: str, db: AsyncSession = Depends(get_db)):
    repo = SiteRepo(db)

    # Проверяем, нет ли уже такого кода
    existing = await repo.get_by_code(code)
    if existing:
        return {"error": "Site with this code already exists"}

    site = await repo.create(code, name)
    await db.commit()
    return {
        "id": str(site.id),
        "code": site.code,
        "name": site.name,
        "created_at": site.created_at.isoformat()
    }


@app.get("/sites/")
async def list_sites(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from app.models.site import Site

    result = await db.execute(select(Site))
    sites = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "code": s.code,
            "name": s.name,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat()
        }
        for s in sites
    ]


@app.post("/devices/")
async def create_device(site_id: UUID, name: str = None, db: AsyncSession = Depends(get_db)):
    # Проверяем, существует ли сайт
    from app.models.site import Site
    site = await db.get(Site, site_id)
    if not site:
        return {"error": "Site not found"}

    repo = DeviceRepo(db)
    device = await repo.create(site_id, name)
    await db.commit()

    return {
        "id": str(device.id),
        "site_id": str(device.site_id),
        "name": device.name,
        "registration_token": str(device.registration_token),
        "created_at": device.created_at.isoformat()
    }


@app.get("/devices/")
async def list_devices(site_id: UUID = None, db: AsyncSession = Depends(get_db)):
    repo = DeviceRepo(db)

    if site_id:
        devices = await repo.get_by_site(site_id)
    else:
        from sqlalchemy import select
        result = await db.execute(select(Device))
        devices = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "site_id": str(d.site_id),
            "name": d.name,
            "is_active": d.is_active,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "created_at": d.created_at.isoformat()
        }
        for d in devices
    ]


@app.get("/devices/{device_id}")
async def get_device(device_id: UUID, db: AsyncSession = Depends(get_db)):
    repo = DeviceRepo(db)
    device = await repo.get_by_id(device_id)

    if not device:
        return {"error": "Device not found"}

    return {
        "id": str(device.id),
        "site_id": str(device.site_id),
        "name": device.name,
        "registration_token": str(device.registration_token),
        "is_active": device.is_active,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "last_ip": device.last_ip,
        "client_version": device.client_version,
        "created_at": device.created_at.isoformat()
    }


@app.patch("/devices/{device_id}/heartbeat")
async def device_heartbeat(device_id: UUID, ip: str = None, db: AsyncSession = Depends(get_db)):
    repo = DeviceRepo(db)
    await repo.update_last_seen(device_id, ip)
    await db.commit()

    return {"status": "ok", "message": "Heartbeat received"}


@app.post("/push", response_model=PushResponse)
async def push_events(request: PushRequest, db: AsyncSession = Depends(get_db)):
    """
    Принимает пачку событий от устройства
    - Проверяет дубликаты по event_uuid
    - Возвращает список принятых, дублей и отклонённых
    """
    repo = EventRepo(db)

    # Проверяем существование сайта и устройства (можно добавить позже)

    result = PushResponse(
        accepted=[],
        duplicates=[],
        rejected=[],
        server_time=datetime.now(),
        server_seq_upto=0
    )

    # Обрабатываем каждое событие
    for event_in in request.events:
        try:
            status = await repo.process_event(
                event_in,
                site_id=request.site_id,
                device_id=request.device_id
            )

            if status["status"] == "accepted":
                result.accepted.append({
                    "event_uuid": str(status["event_uuid"]),
                    "server_seq": status["server_seq"]
                })
                result.server_seq_upto = max(result.server_seq_upto, status["server_seq"])

            elif status["status"] == "duplicate":
                result.duplicates.append({
                    "event_uuid": str(status["event_uuid"]),
                    "server_seq": status["server_seq"]
                })
                result.server_seq_upto = max(result.server_seq_upto, status["server_seq"])

            else:  # rejected
                result.rejected.append({
                    "event_uuid": str(status["event_uuid"]),
                    "reason_code": status["reason_code"],
                    "message": status["message"]
                })

        except Exception as e:
            result.rejected.append({
                "event_uuid": str(event_in.event_uuid),
                "reason_code": "PROCESSING_ERROR",
                "message": str(e)
            })

    await db.commit()
    return result


@app.get("/pull")
async def pull_events(
        site_id: UUID,
        since_seq: int = 0,
        limit: int = 100,
        db: AsyncSession = Depends(get_db)
):
    """
    Получает события для синхронизации (pull)
    - site_id: ID сайта
    - since_seq: минимальный server_seq (включительно)
    - limit: максимум событий
    """
    repo = EventRepo(db)
    events = await repo.pull_events(site_id, since_seq, limit)

    return [
        {
            "event_uuid": str(e.event_uuid),
            "event_type": e.event_type,
            "event_datetime": e.event_datetime.isoformat(),
            "payload": e.payload,
            "server_seq": e.server_seq,
            "created_at": e.received_at.isoformat()
        }
        for e in events
    ]


@app.get("/events/status")
async def events_status(site_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Возвращает статус синхронизации для сайта
    """
    from sqlalchemy import select, func

    # Максимальный server_seq для сайта
    max_seq = await db.execute(
        select(func.max(Event.server_seq)).where(Event.site_id == site_id)
    )
    max_seq = max_seq.scalar() or 0

    # Количество событий
    count = await db.execute(
        select(func.count()).where(Event.site_id == site_id)
    )
    count = count.scalar() or 0

    return {
        "site_id": str(site_id),
        "total_events": count,
        "max_server_seq": max_seq,
        "server_time": datetime.now().isoformat()
    }