# ADR-0002: Idempotent event ingest by event_uuid and payload_hash

## Status
Accepted

## Context
Синхронизация с офлайн/нестабильными клиентами приводит к повторным отправкам одного и того же события. Нужен deterministic механизм отличать безопасный повтор от конфликтного случая.

## Decision
- Хранить `event_uuid` как primary key события.
- Вычислять `payload_hash` из canonical JSON payload.
- Правила ingest:
  - нет события с таким UUID → принять;
  - UUID существует и hash совпадает → считать duplicate_same_payload;
  - UUID существует и hash отличается → отклонить как uuid_collision.

## Consequences
Плюсы:
- Идемпотентный push API.
- Безопасное повторение запросов клиентом.
- Явная диагностика коллизий event UUID.

Минусы:
- Дополнительные вычисления hash.
- Коллизии требуют клиентской стратегии remediation.

## Alternatives Considered
### Option 1: Accept-by-UUID only (без payload hash)
Не детектирует конфликтные данные под одним UUID.

### Option 2: Upsert on conflict
Может скрывать ошибки клиента, перезаписывая уже принятые события.
