# План доработки API репозитория непринятого (lost assets)

## Цель
Добавить endpoint для получения деталей одной lost asset и расширить фильтрацию списка lost assets (по дате, диапазону количеств).

## Текущее состояние
- Существует endpoint `GET /lost-assets` с базовой фильтрацией (site_id, source_site_id, operation_id, item_id, search).
- Существует endpoint `POST /lost-assets/{operation_line_id}/resolve` для разрешения lost asset (found_to_destination, return_to_source, write_off).
- Метод `list_lost` в `AssetRegistersRepo` поддерживает ограниченный набор фильтров.
- Нет endpoint для получения деталей конкретной lost asset по operation_line_id.

## Задачи

### 1. Добавить endpoint для получения деталей lost asset
**Маршрут:** `GET /lost-assets/{operation_line_id}`  
**Ответ:** `LostAssetRow` (та же схема, что и в списке, но с дополнительными полями, если нужно)  
**Логика:**
- Проверка прав доступа (пользователь должен иметь доступ к site_id lost asset).
- Запрос к репозиторию для получения записи `LostAssetBalance` с join на Site, Item и источник Site.
- Если запись не найдена — 404.
- Возврат данных в формате `LostAssetRow`.

**Изменения:**
- Добавить метод `get_lost_row` в `AssetRegistersRepo` (не for update) или использовать существующий `get_lost_row_for_update` без блокировки.
- Добавить endpoint в `app/api/routes_assets.py`.
- Обновить схему ответа, если требуется больше полей (например, информация об операции).

### 2. Расширить фильтрацию списка lost assets
Добавить параметры запроса к `GET /lost-assets`:
- `updated_after` (datetime, optional) — фильтр по полю `updated_at` (дата/время последнего обновления).
- `updated_before` (datetime, optional)
- `qty_from` (decimal, optional) — минимальное количество (`qty >= qty_from`).
- `qty_to` (decimal, optional) — максимальное количество (`qty <= qty_to`).

**Логика:**
- Добавить поля в схему `LostAssetFilter` (`app/schemas/asset_register.py`).
- Обновить метод `list_lost` в `AssetRegistersRepo` для применения новых фильтров.
- Учесть, что фильтры должны комбинироваться с существующими.

### 3. Обновить документацию API
- Внести изменения в `API_REFERENCE.md` или `docs/API_REFERENCE.md` (описать новые параметры и endpoint).
- Обновить OpenAPI схему (автоматически генерируется, но нужно убедиться в корректности аннотаций).

### 4. Написать/обновить тесты
- Добавить тест для нового endpoint `GET /lost-assets/{operation_line_id}`.
- Добавить тесты для новых фильтров (updated_after, updated_before, qty_from, qty_to).
- Убедиться, что существующие тесты проходят.

## Подробные шаги

### Шаг 1: Изменение схемы фильтра
Файл: `app/schemas/asset_register.py`
- Добавить в класс `LostAssetFilter` поля:
  ```python
  updated_after: datetime | None = None
  updated_before: datetime | None = None
  qty_from: Decimal | None = Field(None, ge=0)
  qty_to: Decimal | None = Field(None, ge=0)
  ```
- Убедиться, что поля опциональные и имеют корректные валидации.

### Шаг 2: Обновление репозитория
Файл: `app/repos/asset_registers_repo.py`
- Добавить метод `get_lost_row` (без `with_for_update`), возвращающий `LostAssetBalance` с join на Site, Item и источник Site, либо адаптировать существующий `get_lost_row_for_update` для использования в read-only контексте (можно создать отдельный метод).
- Модифицировать `list_lost`:
  - Принимать новые параметры `updated_after`, `updated_before`, `qty_from`, `qty_to`.
  - Добавить условия в SQL запрос:
    ```python
    if updated_after is not None:
        stmt = stmt.where(LostAssetBalance.updated_at >= updated_after)
    if updated_before is not None:
        stmt = stmt.where(LostAssetBalance.updated_at <= updated_before)
    if qty_from is not None:
        stmt = stmt.where(LostAssetBalance.qty >= qty_from)
    if qty_to is not None:
        stmt = stmt.where(LostAssetBalance.qty <= qty_to)
    ```

### Шаг 3: Обновление endpoint списка lost assets
Файл: `app/api/routes_assets.py`
- Добавить параметры запроса в функцию `list_lost_assets`:
  ```python
  updated_after: datetime | None = Query(None),
  updated_before: datetime | None = Query(None),
  qty_from: Decimal | None = Query(None, ge=0),
  qty_to: Decimal | None = Query(None, ge=0),
  ```
- Передать эти параметры в `uow.asset_registers.list_lost`.

### Шаг 4: Добавление endpoint деталей lost asset
Файл: `app/api/routes_assets.py`
- Добавить новую функцию `get_lost_asset`:
  ```python
  @router.get("/lost-assets/{operation_line_id}", response_model=LostAssetRow)
  async def get_lost_asset(
      operation_line_id: int,
      uow: UnitOfWork = Depends(get_uow),
      identity: Identity = Depends(require_user_identity),
  ) -> LostAssetRow:
      _require_read_access(identity)
      async with uow:
          row = await uow.asset_registers.get_lost_row(operation_line_id)
          if not row:
              raise HTTPException(status_code=404, detail="Lost asset not found")
          # Проверить доступ к site_id
          visible_site_ids = await _resolve_visible_site_ids(uow, identity)
          if row.site_id not in visible_site_ids:
              raise HTTPException(status_code=403, detail="No access to this lost asset")
          return LostAssetRow.model_validate(row)
  ```
- Необходимо реализовать `get_lost_row` в репозитории, который возвращает dict с теми же полями, что и `list_lost`, или объект `LostAssetBalance` с отношениями. Проще всего расширить существующий запрос из `list_lost` с фильтрацией по `operation_line_id`.

### Шаг 5: Обновление UnitOfWork
Файл: `app/services/uow.py`
- Добавить метод `get_lost_row` в `AssetRegistersRepo` и убедиться, что он доступен через `uow.asset_registers`.

### Шаг 6: Написание тестов
Файл: `tests/test_operations_acceptance_and_issue_api.py` (или новый файл)
- Добавить тест для `GET /lost-assets/{operation_line_id}`:
  - Создать lost asset через приемку с lost_qty.
  - Запросить его детали.
  - Проверить статус 200 и корректность данных.
- Добавить тесты для новых фильтров:
  - Создать несколько lost assets с разными датами и количествами.
  - Фильтровать по `updated_after`/`updated_before` и проверять результат.
  - Фильтровать по `qty_from`/`qty_to`.

### Шаг 7: Проверка и рефакторинг
- Запустить существующие тесты (`pytest`), убедиться, что ничего не сломано.
- При необходимости отрефакторить код.

## Оценка сложности
Задача небольшая, требует изменений в ~5 файлах. Основное внимание — на корректность фильтрации и права доступа.

## Следующие шаги
После реализации этих двух задач можно рассмотреть дополнительные улучшения:
- Добавить агрегации (сумма потерянного по сайтам).
- Добавить экспорт в CSV.
- Добавить историю действий (логи) для lost assets.

## Примечания
- Все изменения должны сохранять обратную совместимость.
- Фильтрация по дате должна учитывать часовой пояс (использовать UTC).