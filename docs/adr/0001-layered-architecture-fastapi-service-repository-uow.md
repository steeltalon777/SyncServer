# ADR-0001: Layered architecture with FastAPI + Service + Repository + UnitOfWork

## Status
Accepted

## Context
Кодовая база содержит разные типы ответственности: HTTP-контракты, бизнес-правила синхронизации/каталога и работу с БД. Без явных слоёв появляется риск дублирования логики и сложных транзакционных ошибок.

## Decision
Использовать слоистую архитектуру:
- API слой (`app/api`) для transport concerns.
- Service слой (`app/services`) для бизнес-правил.
- Repository слой (`app/repos`) для data access.
- `UnitOfWork` как транзакционная граница запроса.

## Consequences
Плюсы:
- Предсказуемое разделение ответственности.
- Проще тестировать бизнес-логику и репозитории отдельно.
- Централизованное управление commit/rollback.

Минусы:
- Больше структурного кода (UoW + repos + services).
- Для мелких фич требуется проход через несколько слоёв.

## Alternatives Considered
### Option 1: Fat routers + direct ORM access
Быстрее старт, но приводит к смешению HTTP и доменной логики.

### Option 2: Domain service without repositories
Упрощает количество файлов, но сильнее связывает сервисы с ORM деталями.
