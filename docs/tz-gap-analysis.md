# Сопоставление текущего проекта с ТЗ v1

Ниже — краткий gap-analysis между текущей реализацией и вашим ТЗ.

## Выполнено частично/полностью

- Async SQLAlchemy используется (`AsyncSession`, async dependency) ✅
- Базовые модели `sites/devices/events` есть ✅
- Базовые DTO для `push` есть ✅
- Логика duplicate/uuid_collision по `event_uuid + payload_hash` есть ✅
- Репозиторий pull по `site_id + since_seq` есть ✅

## Не выполнено (из ТЗ)

1. **Модели**
   - Нет `categories`, `items`, `balances`, `user_site_roles`.

2. **Слои и структура**
   - Нет выделенного Unit of Work.
   - Нет разделения схем на `common.py`, `sync.py`, `catalog.py`.

3. **Правила работы с БД по ТЗ**
   - Сейчас создаются таблицы через `create_all` при старте.
   - В ТЗ: таблицы/миграции ведёт Django, FastAPI не создаёт схему.

4. **`server_seq`**
   - Сейчас `max + 1` в приложении.
   - В ТЗ: `BIGSERIAL`/генерация на стороне БД.

5. **Тесты**
   - Нет автоматических тестов на smoke/duplicate/collision/pull.

## Рекомендуемый порядок доработок

1. Убрать `create_all` из `startup` для prod-сценария.
2. Перевести `server_seq` на генерацию БД.
3. Добавить недостающие ORM-модели.
4. Разнести DTO по модулям (`sync`, `catalog`, `common`).
5. Ввести Unit of Work и сервисный слой.
6. Добавить асинхронные интеграционные тесты на события и pull.
