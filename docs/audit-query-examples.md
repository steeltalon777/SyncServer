# Audit Query Examples

CLI-скрипт `scripts/query_audit.py` для просмотра аудит-логов пользователя в SyncServer.  
Запускается из контейнера: `docker compose exec syncserver python scripts/query_audit.py <args>`.

Аутентификация не требуется — `docker compose exec` уже подразумевает полный доступ к БД.  
Для идентификации пользователя используйте `--username` (рекомендуется) или `--token`.

## Базовое использование

```bash
# Последние 15 записей для пользователя ivanov
docker compose exec syncserver python scripts/query_audit.py --username ivanov

# По точному токену (когда username неизвестен)
docker compose exec syncserver python scripts/query_audit.py --token <UUID>
```

## Фильтры

```bash
# По типу события (operation.create, operation.submit и т.д.)
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --event-type operation.submit --console

# По типу сущности
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --entity-type operation --console

# По диапазону дат
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --date-from 2026-06-01 --date-to 2026-06-18 --console

# По ID сущности (UUID операции)
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --entity-id <operation-uuid> --console

# Лимит записей
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --limit 50 --console
```

## Форматы вывода

### Markdown (по умолчанию)
```bash
# Markdown в stdout
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --console

# В файл (авто-имя)
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov

# В указанный файл
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --output /tmp/audit_report.md
```

### Таблица (plain text)
```bash
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --format table --console
```

### JSON (JSON Lines)
```bash
# JSON в stdout
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --format json --console | jq '.'

# Фильтрация через jq
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --format json --console | jq 'select(.event_type | startswith("operation"))'
```

## Сценарии

### Сценарий 1: Просмотр всех действий пользователя за день
```bash
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --date-from 2026-06-18 --limit 100 --console
```

### Сценарий 2: Экспорт в файл для отчёта
```bash
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --date-from 2026-06-01 --date-to 2026-06-18 \
  --format markdown --output /tmp/audit_june.md

# Скопировать из контейнера:
docker cp warehouse_syncserver:/tmp/audit_june.md .
```

### Сценарий 3: JSON-экспорт для обработки
```bash
docker compose exec syncserver python scripts/query_audit.py \
  --username ivanov --event-type operation.submit \
  --format json --console | jq -s '.'
```

## Структура JSON-события

```json
{
  "timestamp": "2026-06-18T10:30:00+00:00",
  "event_type": "operation.submit",
  "actor_username": "ivanov",
  "entity_type": "operation",
  "entity_id": "operation-uuid-1234",
  "summary": "Операция подтверждена (RECEIVE)",
  "changes": {
    "status": "submitted"
  }
}
```

## Примечания

- Подключается к БД SyncServer напрямую через SQLAlchemy (не через HTTP API).
- `--username` — человеко-читаемый идентификатор (рекомендуется).
- `--token` — точный lookup по UUID токену (когда username неизвестен).
- По умолчанию выборка за последние 30 дней.
- Нет событий → пустой отчёт без ошибки.
