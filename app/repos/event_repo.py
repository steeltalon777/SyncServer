from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from uuid import UUID
from datetime import datetime
import hashlib
import json
from app.models.event import Event


class EventRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _compute_payload_hash(self, payload: dict) -> str:
        """Вычисляет хеш payload для обнаружения дублей"""
        from app.core.json_encoder import CustomJSONEncoder
        payload_str = json.dumps(payload, sort_keys=True, cls=CustomJSONEncoder)
        return hashlib.sha256(payload_str.encode()).hexdigest()

    async def get_next_seq(self) -> int:
        """Получает следующий server_seq"""
        result = await self.db.execute(
            select(func.coalesce(func.max(Event.server_seq), 0) + 1)
        )
        return result.scalar()

    async def get_by_uuid(self, event_uuid: UUID) -> Event | None:
        query = select(Event).where(Event.event_uuid == event_uuid)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_event(self, event_in, site_id: UUID, device_id: UUID = None) -> Event:
        """Создаёт новое событие"""
        next_seq = await self.get_next_seq()

        # Конвертируем payload в JSON-совместимый dict
        from app.core.json_encoder import CustomJSONEncoder
        payload_dict = json.loads(
            json.dumps(event_in.payload.dict(), cls=CustomJSONEncoder)
        )

        # Хеш считаем от оригинального payload (с Decimal)
        payload_hash = self._compute_payload_hash(event_in.payload.dict())

        event = Event(
            event_uuid=event_in.event_uuid,
            site_id=site_id,
            device_id=device_id,
            event_type=event_in.event_type,
            event_datetime=event_in.event_datetime,
            payload=payload_dict,  # тут уже Decimal преобразован в float
            server_seq=next_seq,
            payload_hash=payload_hash,
            schema_version=event_in.schema_version
        )

        self.db.add(event)
        await self.db.flush()
        return event

    async def process_event(self, event_in, site_id: UUID, device_id: UUID = None) -> dict:
        """
        Обрабатывает событие с проверкой на дубли
        Возвращает статус: accepted, duplicate, или rejected
        """
        # Проверяем, есть ли уже такое событие
        existing = await self.get_by_uuid(event_in.event_uuid)

        if not existing:
            # Новое событие
            event = await self.create_event(event_in, site_id, device_id)
            return {
                "status": "accepted",
                "event_uuid": event.event_uuid,
                "server_seq": event.server_seq
            }

        # Событие уже есть - проверяем хеш
        new_hash = self._compute_payload_hash(event_in.payload.dict())

        if existing.payload_hash == new_hash:
            # Тот же payload - дубликат
            return {
                "status": "duplicate",
                "event_uuid": existing.event_uuid,
                "server_seq": existing.server_seq
            }
        else:
            # Другой payload - коллизия UUID
            return {
                "status": "rejected",
                "event_uuid": event_in.event_uuid,
                "reason_code": "UUID_COLLISION",
                "message": "Event with same UUID but different payload already exists"
            }

    async def pull_events(self, site_id: UUID, since_seq: int = 0, limit: int = 1000) -> list[Event]:
        """Получает события для синхронизации (pull)"""
        query = select(Event).where(
            and_(
                Event.site_id == site_id,
                Event.server_seq > since_seq
            )
        ).order_by(Event.server_seq).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()