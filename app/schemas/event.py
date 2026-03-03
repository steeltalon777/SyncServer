from pydantic import BaseModel, Field, validator
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from typing import List, Optional


# Вложенная схема для строки события (товар + количество)
class EventLine(BaseModel):
    item_id: UUID
    qty: Decimal = Field(max_digits=18, decimal_places=3)
    batch: Optional[str] = None


# Схема для payload события
class EventPayload(BaseModel):
    doc_id: Optional[str] = None
    doc_type: Optional[str] = None
    comment: Optional[str] = None
    lines: List[EventLine]

    @validator('lines')
    def lines_not_empty(cls, v):
        if not v:
            raise ValueError('lines must not be empty')
        return v


# Схема для входящего события (от клиента)
class EventIn(BaseModel):
    event_uuid: UUID
    event_type: str = Field(..., pattern="^(sale|purchase|move|inventory|adjustment)$")
    event_datetime: datetime
    schema_version: int = 1
    payload: EventPayload


# Схема для запроса push (пачка событий)
class PushRequest(BaseModel):
    site_id: UUID
    device_id: UUID
    batch_id: UUID
    events: List[EventIn]


# Схема для ответа на push
class PushResponse(BaseModel):
    accepted: List[dict] = []  # [{event_uuid, server_seq}]
    duplicates: List[dict] = []  # [{event_uuid, server_seq}]
    rejected: List[dict] = []  # [{event_uuid, reason_code, message}]
    server_time: datetime
    server_seq_upto: int