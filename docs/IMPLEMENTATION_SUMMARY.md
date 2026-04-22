# Краткое описание реализации системы приёмки и репозитория непринятого

## Архитектурные компоненты

### 1. Модели данных (`app/models/asset_register.py`)

```python
class PendingAcceptanceBalance(Base):
    """Ожидающие приёмки активы после submit операции"""
    __tablename__ = "pending_acceptance_balances"
    operation_line_id = mapped_column(Integer, primary_key=True)
    destination_site_id = mapped_column(Integer, nullable=False)
    source_site_id = mapped_column(Integer, nullable=True)
    item_id = mapped_column(Integer, nullable=False)
    qty = mapped_column(Numeric(12, 2), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False)

class LostAssetBalance(Base):
    """Непринятые активы (lost assets)"""
    __tablename__ = "lost_asset_balances"
    operation_line_id = mapped_column(Integer, primary_key=True)
    site_id = mapped_column(Integer, nullable=False)  # текущий склад
    source_site_id = mapped_column(Integer, nullable=True)
    item_id = mapped_column(Integer, nullable=False)
    qty = mapped_column(Numeric(12, 2), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False)
```

### 2. Схемы Pydantic (`app/schemas/asset_register.py`)

```python
class LostAssetFilter(BaseModel):
    """Фильтры для списка lost assets"""
    site_id: int | None = None
    source_site_id: int | None = None
    operation_id: UUID | None = None
    item_id: int | None = None
    search: str | None = None
    updated_after: datetime | None = None  # новый фильтр
    updated_before: datetime | None = None  # новый фильтр
    qty_from: Decimal | None = Field(None, ge=0)  # новый фильтр
    qty_to: Decimal | None = Field(None, ge=0)    # новый фильтр
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)

class LostAssetRow(ORMBaseModel):
    """Строка lost asset для ответа API"""
    operation_id: UUID
    operation_line_id: int
    site_id: int
    site_name: str
    source_site_id: int | None
    source_site_name: str | None
    item_id: int
    item_name: str
    sku: str
    qty: Decimal
    updated_at: datetime
```

### 3. Репозиторий (`app/repos/asset_registers_repo.py`)

**Метод `list_lost`** – поддерживает все фильтры, включая новые:
- `updated_after`, `updated_before` – фильтрация по `LostAssetBalance.updated_at`
- `qty_from`, `qty_to` – фильтрация по количеству

**Метод `get_lost_row`** – новый метод для получения деталей одной записи:
```python
async def get_lost_row(self, operation_line_id: int) -> dict | None:
    """Возвращает одну запись lost asset с join на Site и Item"""
    # SQL запрос аналогичный list_lost, но с фильтром по operation_line_id
```

### 4. API маршруты (`app/api/routes_assets.py`)

**Новый endpoint:**
```python
@router.get("/lost-assets/{operation_line_id}", response_model=LostAssetRow)
async def get_lost_asset(
    operation_line_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> LostAssetRow:
    """Получить детали одного непринятого актива"""
    _require_read_access(identity)
    async with uow:
        row = await uow.asset_registers.get_lost_row(operation_line_id)
        if not row:
            raise HTTPException(status_code=404, detail="Lost asset not found")
        # Проверка прав доступа к сайту
        visible_site_ids = await _resolve_visible_site_ids(uow, identity)
        if row["site_id"] not in visible_site_ids:
            raise HTTPException(status_code=403, detail="No access to this lost asset")
        return LostAssetRow.model_validate(row)
```

**Обновлённый endpoint `list_lost_assets`** – принимает новые параметры фильтрации.

### 5. Сервис (`app/services/operations_service.py`)

**Ключевые методы:**
- `submit_operation()` – создаёт `PendingAcceptanceBalance`
- `accept_operation_lines()` – обрабатывает приёмку, создаёт `LostAssetBalance` при `lost_qty > 0`
- `resolve_lost_asset()` – разрешает lost asset (возврат, списание, перемещение)

## Бизнес-логика

### Создание lost asset
1. Операция RECEIVE/MOVE с `acceptance_required=true`
2. Подтверждение операции (`submit`) → создаётся `PendingAcceptanceBalance`
3. Приёмка с `lost_qty > 0` → создаётся `LostAssetBalance`, удаляется `PendingAcceptanceBalance`

### Разрешение lost asset
1. **return_to_source** – только для MOVE операций
   - Увеличивает баланс `source_site_id`
   - Удаляет `LostAssetBalance`
2. **write_off** – списание
   - Уменьшает общее количество товара в системе
   - Удаляет `LostAssetBalance`
3. **found_to_destination** – перемещение на другой склад
   - Увеличивает баланс `destination_site_id`
   - Удаляет `LostAssetBalance`

## Права доступа

### Просмотр lost assets
- Пользователь должен иметь `UserAccessScope` с `can_view=true` для сайта lost asset
- Проверка через `_resolve_visible_site_ids()` в каждом endpoint

### Разрешение lost assets
- Для `return_to_source` и `found_to_destination` нужны права на операции на целевом складе
- Для `write_off` нужны права на операции на текущем складе

## Аудит
Все действия фиксируются в `OperationAcceptanceAction`:
- `action_type`: "accept", "return_to_source", "write_off", "found_to_destination"
- `performed_by_user_id`, `performed_at`

## Тестирование

### Тесты API (`tests/test_lost_assets_api.py`)
1. `test_get_lost_asset_detail` – проверка нового endpoint
2. `test_lost_assets_filter_by_date_and_qty` – проверка фильтрации по дате и количеству

### Интеграционные тесты (`tests/test_operations_acceptance_and_issue_api.py`)
- Полный workflow приёмки и создания lost assets

## Миграции базы данных

Система использует существующие таблицы, созданные миграцией `0004_operations_acceptance_asset_registers.py`:
- `pending_acceptance_balances`
- `lost_asset_balances`
- `issued_asset_balances`
- `operation_acceptance_actions`

Новые поля фильтрации не требуют изменений схемы БД.

## Интеграционные точки для клиентов

### 1. Получение списка с фильтрацией
```python
GET /api/v1/lost-assets?updated_after=2026-04-01T00:00:00Z&qty_from=10
```

### 2. Детальный просмотр
```python
GET /api/v1/lost-assets/{operation_line_id}
```

### 3. Разрешение
```python
POST /api/v1/lost-assets/{operation_line_id}/resolve
{
  "action": "write_off",
  "comment": "Списание брака"
}
```

## Обработка ошибок

### Коды ответов
- `200` – успех
- `400` – неверные параметры запроса
- `403` – нет доступа к сайту
- `404` – lost asset не найден
- `409` – нарушение бизнес-правил (например, return_to_source для RECEIVE)

### Сообщения об ошибках
В формате:
```json
{
  "detail": "Описание ошибки"
}
```

## Мониторинг и логирование

### Ключевые метрики
1. Количество созданных lost assets
2. Время разрешения lost assets
3. Распределение по типам действий

### Логи
- Создание lost asset: `Created lost asset for operation_line_id={id}, qty={qty}`
- Разрешение: `Resolved lost asset {id} with action {action}`

## Производительность

### Индексы
- `lost_asset_balances.updated_at` – для фильтрации по дате
- `lost_asset_balances.site_id` – для фильтрации по сайту
- `lost_asset_balances.qty` – для фильтрации по количеству

### Оптимизации запросов
- Пагинация через `LIMIT/OFFSET`
- JOIN только необходимых таблиц (Site, Item)
- Кэширование списка сайтов пользователя

## Расширяемость

### Добавление новых фильтров
1. Добавить поле в `LostAssetFilter`
2. Обновить `list_lost` в репозитории
3. Обновить endpoint `list_lost_assets`

### Добавление новых действий
1. Добавить тип действия в `LostAssetResolveRequest.action`
2. Реализовать логику в `resolve_lost_asset()`
3. Добавить проверки бизнес-правил

## Рекомендации по использованию

### Для клиентов
1. Используйте пагинацию для больших списков
2. Кэшируйте список сайтов пользователя
3. Проверяйте права доступа перед разрешением

### Для разработчиков
1. Всегда используйте транзакции при изменении балансов
2. Следуйте существующему шаблону для новых фильтров
3. Пишите тесты для новых сценариев

## Ссылки на код

- Модели: [`app/models/asset_register.py`](../app/models/asset_register.py)
- Схемы: [`app/schemas/asset_register.py`](../app/schemas/asset_register.py)
- Репозиторий: [`app/repos/asset_registers_repo.py`](../app/repos/asset_registers_repo.py)
- API: [`app/api/routes_assets.py`](../app/api/routes_assets.py)
- Сервис: [`app/services/operations_service.py`](../app/services/operations_service.py)
- Тесты: [`tests/test_lost_assets_api.py`](../tests/test_lost_assets_api.py)
## Temporary items: реализованный Phase 1

- Добавлена таблица и ORM-модель [`temporary_items`](app/models/temporary_item.py:14) и миграция [`0007_temporary_items_phase1`](alembic/versions/0007_temporary_items_phase1.py).
- [`POST /operations`](app/api/routes_operations.py:103) теперь умеет атомарно создавать временную ТМЦ внутри операции прихода.
- Для совместимости с текущей архитектурой Phase 1 использует скрытый backing [`Item`](app/repos/catalog_repo.py:359), а не полный refactor на `inventory_subjects`.
- Добавлен moderation API в [`app/api/routes_temporary_items.py`](app/api/routes_temporary_items.py).
- Добавлены тесты [`tests/test_temporary_items_phase1.py`](tests/test_temporary_items_phase1.py) и расширена валидация схемы в [`tests/test_operation_schema_types.py`](tests/test_operation_schema_types.py).
- Отложено: `inventory_subjects`, перенос balances/registers/read-model на универсальную ссылку, служебные движения при approve/merge, запреты/переносы для pending/lost/issued регистров.
