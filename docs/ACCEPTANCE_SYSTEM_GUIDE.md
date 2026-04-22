# Система приёмки и репозиторий непринятых активов

## Обзор

Система приёмки предназначена для операций **RECEIVE** (приход) и **MOVE** (перемещение). После создания и подтверждения операции кладовщик целевого склада (или главный кладовщик) выполняет приёмку товара, указывая принятое количество и количество непринятого (lost). Непринятые активы попадают в репозиторий непринятого (lost assets), где могут быть разрешены тремя способами: возврат на исходный склад, списание или перемещение на другой склад.

## Основные понятия

### 1. Операции с приёмкой
- **RECEIVE** – приход товара на склад из внешнего источника
- **MOVE** – перемещение товара между складами внутри системы

Обе операции имеют поле `acceptance_required = true` и проходят этапы:
1. Создание операции (статус `draft`)
2. Подтверждение операции (`submit`) – создаются записи в регистре ожидающих приёмки
3. Приёмка строк операции (`accept-lines`) – указывается `accepted_qty` и `lost_qty`
4. После приёмки:
   - Принятое количество добавляется в баланс целевого склада
   - Непринятое количество попадает в репозиторий непринятого (lost assets)

### 2. Регистры активов (Asset Registers)

Система использует три регистра для отслеживания промежуточных состояний:

#### PendingAcceptanceBalance
Ожидающие приёмки активы. Создаются при подтверждении операции (`submit`).
- `operation_line_id` – ссылка на строку операции
- `destination_site_id` – склад назначения (куда должен поступить товар)
- `source_site_id` – исходный склад (только для MOVE)
- `item_id`, `qty` – товар и количество
- `updated_at` – время последнего обновления

#### LostAssetBalance
Непринятые активы. Создаются при приёмке, если указан `lost_qty > 0`.
- `operation_line_id` – ссылка на строку операции
- `site_id` – склад, на котором находится непринятый товар (целевой склад операции)
- `source_site_id` – исходный склад (для MOVE)
- `item_id`, `qty` – товар и количество непринятого
- `updated_at` – время создания/обновления

#### IssuedAssetBalance
Выданные активы (для операций ISSUE и ISSUE_RETURN). Не относится к приёмке.

### 3. Разрешение непринятых активов (Lost Asset Resolution)

Непринятые активы могут быть разрешены тремя способами:

1. **return_to_source** – возврат на исходный склад (только для MOVE)
   - Увеличивает баланс исходного склада
   - Удаляет запись из lost assets

2. **write_off** – списание (уничтожение, порча)
   - Уменьшает общее количество товара в системе
   - Удаляет запись из lost assets

3. **found_to_destination** – перемещение на другой склад (не исходный)
   - Увеличивает баланс указанного склада
   - Удаляет запись из lost assets

## API для работы с репозиторием непринятого

### Получение списка непринятых активов

```
GET /api/v1/lost-assets
```

**Параметры фильтрации:**
- `site_id` – фильтр по складу
- `source_site_id` – фильтр по исходному складу
- `operation_id` – фильтр по операции
- `item_id` – фильтр по товару
- `search` – поиск по названию товара, SKU или названию склада
- `updated_after`, `updated_before` – фильтр по дате обновления (ISO 8601)
- `qty_from`, `qty_to` – фильтр по диапазону количества
- `page`, `page_size` – пагинация

**Пример ответа:**
```json
{
  "items": [
    {
      "operation_id": "6f3f6d8a-2a6e-4cf2-9a2a-a0a2a2f89f4b",
      "operation_line_id": 123,
      "site_id": 1,
      "site_name": "Склад А",
      "source_site_id": null,
      "source_site_name": null,
      "item_id": 456,
      "item_name": "Товар",
      "sku": "SKU123",
      "qty": "5.00",
      "updated_at": "2026-04-16T05:30:00Z"
    }
  ],
  "total_count": 42,
  "page": 1,
  "page_size": 50
}
```

### Получение деталей одного непринятого актива

```
GET /api/v1/lost-assets/{operation_line_id}
```

Возвращает полную информацию о конкретном непринятом активе. Используется для просмотра перед разрешением.

### Разрешение непринятого актива

```
POST /api/v1/lost-assets/{operation_line_id}/resolve
```

**Тело запроса:**
```json
{
  "action": "return_to_source",  // или "write_off", "found_to_destination"
  "destination_site_id": 2,      // обязателен для found_to_destination
  "comment": "Потерянный товар найден"
}
```

**Бизнес-правила:**
- Для `return_to_source` операция должна быть типа MOVE (иметь source_site_id)
- Для `found_to_destination` должен быть указан `destination_site_id` ≠ site_id и ≠ source_site_id
- Пользователь должен иметь права на операции на целевом складе

## Поток данных

### 1. Создание и подтверждение операции RECEIVE

```
POST /api/v1/operations
{
  "operation_type": "RECEIVE",
  "site_id": 1,
  "lines": [{"line_number": 1, "item_id": 456, "qty": 10}]
}

POST /api/v1/operations/{operation_id}/submit
```

После подтверждения создаётся запись в `PendingAcceptanceBalance`:
- `destination_site_id` = 1
- `qty` = 10

### 2. Приёмка с частичным непринятием

```
POST /api/v1/operations/{operation_id}/accept-lines
{
  "lines": [
    {
      "line_id": 123,
      "accepted_qty": 7,
      "lost_qty": 3
    }
  ]
}
```

Результат:
- Баланс склада 1 увеличивается на 7
- Создаётся запись в `LostAssetBalance`:
  - `site_id` = 1
  - `qty` = 3
- Запись из `PendingAcceptanceBalance` удаляется

### 3. Работа с репозиторием непринятого

Кладовщик может:
1. Просмотреть список непринятых активов с фильтрацией
2. Получить детали конкретного актива
3. Выполнить разрешение (например, списание)

## Реализация в коде

### Модели данных

```python
# app/models/asset_register.py
class PendingAcceptanceBalance(Base):
    __tablename__ = "pending_acceptance_balances"
    operation_line_id = mapped_column(Integer, primary_key=True)
    destination_site_id = mapped_column(Integer, nullable=False)
    source_site_id = mapped_column(Integer, nullable=True)
    item_id = mapped_column(Integer, nullable=False)
    qty = mapped_column(Numeric(12, 2), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False)

class LostAssetBalance(Base):
    __tablename__ = "lost_asset_balances"
    operation_line_id = mapped_column(Integer, primary_key=True)
    site_id = mapped_column(Integer, nullable=False)  # склад, где находится непринятый товар
    source_site_id = mapped_column(Integer, nullable=True)
    item_id = mapped_column(Integer, nullable=False)
    qty = mapped_column(Numeric(12, 2), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False)
```

### Сервис приёмки

Основная логика находится в `app/services/operations_service.py`:

- `submit_operation()` – создаёт записи в PendingAcceptanceBalance
- `accept_operation_lines()` – обрабатывает приёмку, обновляет балансы, создаёт LostAssetBalance
- `resolve_lost_asset()` – разрешает непринятые активы

### Репозиторий

`app/repos/asset_registers_repo.py` содержит методы:
- `list_lost()` – список с фильтрацией
- `get_lost_row()` – детали одной записи
- `upsert_lost()`, `upsert_pending()` – создание/обновление записей

### API маршруты

`app/api/routes_assets.py`:
- `GET /lost-assets` – список
- `GET /lost-assets/{operation_line_id}` – детали
- `POST /lost-assets/{operation_line_id}/resolve` – разрешение

## Интеграция с клиентами

### Django-клиент

Для интеграции с Django-клиентом необходимо:

1. **Отображение списка непринятых активов**
   - Использовать endpoint `GET /lost-assets` с пагинацией
   - Добавить фильтры по дате и количеству
   - Отображать кнопки действий для каждой записи

2. **Детальный просмотр**
   - При клике на запись открывать детали через `GET /lost-assets/{operation_line_id}`
   - Показывать информацию об операции, товаре, складах

3. **Разрешение**
   - Предоставить три варианта действий с соответствующими формами
   - Для `found_to_destination` – выбор склада из доступных пользователю

### Мобильное приложение

Для мобильных клиентов рекомендуется:
- Загружать список непринятых активов при старте
- Поддерживать офлайн-просмотр (кеширование)
- Синхронизировать разрешения при наличии соединения

## Тестирование

Тесты системы приёмки находятся в:
- `tests/test_operations_acceptance_and_issue_api.py` – основные сценарии
- `tests/test_lost_assets_api.py` – API репозитория непринятого

Пример теста:
```python
async def test_lost_assets_filter_by_date_and_qty():
    # Создание операции с потерями
    # Фильтрация по количеству и дате
    # Проверка результатов
```

## Частые сценарии использования

### Сценарий 1: Приход с частичным браком
1. Приходит партия 100 единиц
2. При приёмке обнаружен брак – 5 единиц
3. Кладовщик указывает `accepted_qty=95`, `lost_qty=5`
4. 5 единиц попадают в lost assets
5. После инвентаризации брак списывается (`write_off`)

### Сценарий 2: Перемещение с расхождением
1. Товар перемещается со склада А на склад Б (50 единиц)
2. При приёмке на складе Б недосдача – 3 единицы
3. Создаётся lost asset на складе Б
4. Принимается решение вернуть на склад А (`return_to_source`)

### Сценарий 3: Найден потерянный товар
1. Товар был потерян при приёмке (lost_qty=2)
2. Через неделю товар найден на складе
3. Кладовщик перемещает его на правильный склад В (`found_to_destination`)

## Ограничения и особенности

1. **Доступность операций**
   - Только операции с `acceptance_required=true` (RECEIVE, MOVE)
   - ISSUE/ISSUE_RETURN не используют эту систему

2. **Права доступа**
   - Просмотр lost assets: доступ к сайту через UserAccessScope с can_view=true
   - Разрешение: нужны права на операции на целевом складе

3. **Аудит**
   - Все действия фиксируются в `OperationAcceptanceAction`
   - Сохраняется пользователь, время, тип действия

4. **Согласованность данных**
   - Все изменения балансов выполняются в транзакциях
   - Проверяются бизнес-правила перед применением

## Дальнейшее развитие

1. **Уведомления** – оповещения о новых lost assets
2. **Отчёты** – статистика по непринятым активам
3. **Массовые операции** – разрешение нескольких записей одновременно
4. **Интеграция с инвентаризацией** – автоматическое списание после инвентаризации