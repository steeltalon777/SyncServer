# Отчет тестирования API SyncServer

**Дата тестирования:** 2026-04-21 09:19:33
**Базовый URL:** http://127.0.0.1:8000/api/v1

## Статистика

- Всего тестов: 34
- Успешных: 23
- Проваленных: 11
- Успешность: 67.6%

## Детали тестов

| Endpoint | Method | Status | Expected | Success | Response Time |
|----------|--------|--------|----------|---------|---------------|
| /health | GET | 200 | 200 | ✓ | 3ms |
| /ready | GET | 200 | 200 | ✓ | 209ms |
| /health/detailed | GET | 200 | 200 | ✓ | 51ms |
| /auth/me | GET | 200 | 200 | ✓ | 194ms |
| /auth/sites | GET | 200 | 200 | ✓ | 116ms |
| /auth/context | GET | 200 | 200 | ✓ | 85ms |
| /auth/sync-user | POST | 200 | 200,201 | ✓ | 79ms |
| /admin/sites | GET | 200 | 200 | ✓ | 64ms |
| /admin/sites | POST | 200 | 201 | ✗ | 64ms |
| /admin/users | GET | 200 | 200 | ✓ | 60ms |
| /admin/users | POST | 200 | 201 | ✗ | 62ms |
| /admin/access/scopes | GET | 200 | 200 | ✓ | 55ms |
| /admin/access/scopes | POST | 422 | 201 | ✗ | 41ms |
| /admin/devices | GET | 200 | 200 | ✓ | 66ms |
| /admin/devices | POST | 422 | 201 | ✗ | 41ms |
| /catalog/admin/units | GET | 200 | 200 | ✓ | 82ms |
| /catalog/admin/units | POST | 200 | 201 | ✗ | 80ms |
| /catalog/admin/categories | GET | 200 | 200 | ✓ | 83ms |
| /catalog/admin/categories | POST | 200 | 201 | ✗ | 80ms |
| /catalog/admin/items | GET | 200 | 200 | ✓ | 94ms |
| /catalog/admin/items | POST | 422 | 201 | ✗ | 64ms |
| /recipients | GET | 200 | 200 | ✓ | 82ms |
| /recipients | POST | 422 | 201 | ✗ | 42ms |
| /operations | GET | 200 | 200 | ✓ | 94ms |
| /balances | GET | 200 | 200 | ✓ | 127ms |
| /balances/summary | GET | 200 | 200 | ✓ | 109ms |
| /pending-acceptance | GET | 200 | 200 | ✓ | 76ms |
| /lost-assets | GET | 200 | 200 | ✓ | 87ms |
| /issued-assets | GET | 200 | 200 | ✓ | 67ms |
| /documents | GET | 500 | 200 | ✗ | 53ms |
| /reports/item-movement | GET | 200 | 200 | ✓ | 120ms |
| /reports/stock-summary | GET | 200 | 200 | ✓ | 95ms |
| /ping | POST | 422 | 200 | ✗ | 50ms |
| /pull | POST | 422 | 200 | ✗ | 45ms |

## Созданные тестовые данные


## Логи

Полные логи доступны в файле `api_crud_test.log`