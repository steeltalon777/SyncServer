# Руководство по запуску stand-тестов SyncServer

## Обзор

Stand-тесты — это интеграционные и e2e тесты, которые работают **только против поднятого тестового стенда**. Они не создают приложение локально, не запускают миграции и не создают схемы БД. Вместо этого они используют уже поднятый сервер и БД через реальный HTTP.

## Основные принципы

1. **По умолчанию stand-тесты не запускаются** — обычный `pytest` запускает только локальные unit-тесты.
2. **Явный opt-in** — для запуска stand-тестов нужно явно указать маркер `stand`.
3. **Guard-цепочка** — перед запуском проверяются обязательные переменные окружения и доступность стенда.
4. **Fail-fast** — при отсутствии необходимых условий тесты не запускаются с понятным сообщением об ошибке.

## Быстрый старт

### 1. Подготовка тестового стенда

Перед запуском stand-тестов необходимо поднять тестовый стенд:

```bash
# Используйте docker-compose или разверните сервер вручную
docker-compose up -d

# Убедитесь, что сервер доступен
curl http://localhost:8000/api/health
```

### 2. Настройка переменных окружения

Создайте `.env` файл в корне проекта или экспортируйте переменные:

```bash
# Обязательные переменные
export SYNC_TEST_MODE=stand
export SYNC_TEST_ALLOW_STAND=1
export SYNC_TEST_BASE_URL=http://localhost:8000
export SYNC_TEST_ROOT_TOKEN=your_root_token_here

# Опциональные переменные
export SYNC_TEST_RUN_ID=my_test_run_$(date +%s)  # для namespacing
export SYNC_TEST_DB_URL=postgresql://user:pass@localhost:5432/test_db
export SYNC_TEST_ALLOW_DIRECT_DB=0
```

### 3. Запуск stand-тестов

```bash
# Запустить все stand-тесты
pytest -m stand

# Запустить только smoke-тесты
pytest -m smoke

# Запустить с подробным выводом
pytest -m stand -v

# Запустить конкретный тестовый файл
pytest tests/stand/smoke/test_stand_smoke.py -v
```

## Guard-цепочка

### Уровень 1: Явный selection gate
Stand-тесты запускаются только если пользователь явно выбрал их через:
- `-m stand`, `-m integration`, `-m e2e`, `-m smoke`
- `-k` с ключевым словом "stand"

**Без явного выбора stand-тесты автоматически исключаются из запуска.**

### Уровень 2: Явный env arm gate
Перед запуском проверяются обязательные переменные окружения:
- `SYNC_TEST_MODE=stand`
- `SYNC_TEST_ALLOW_STAND=1`
- `SYNC_TEST_BASE_URL` (должен начинаться с http:// или https://)
- `SYNC_TEST_ROOT_TOKEN` (не пустой)

### Уровень 3: Stand identity probe
После проверки env выполняется preflight probe стенда:
1. Проверяется доступность health endpoint (`/api/health`)
2. Проверяется доступность readiness endpoint (`/api/health/ready`)
3. Проверяется, что аутентификация через root token работает

Если probe не проходит, pytest завершается с ошибкой до запуска тестов.

### Уровень 4: Direct DB guard (опционально)
Если тест использует маркер `stand_db`, дополнительно проверяется:
- `SYNC_TEST_DB_URL` задан
- `SYNC_TEST_ALLOW_DIRECT_DB=1`

## Структура тестов

```
tests/
├── stand/                    # Все stand-тесты
│   ├── smoke/               # Минимальная проверка стенда
│   │   └── test_stand_smoke.py
│   ├── integration/         # API и бизнес-потоки
│   ├── e2e/                 # Длинные workflow
│   └── support/             # Вспомогательные утилиты
├── unit/                    # Локальные unit-тесты (будущее)
└── conftest.py              # Общая конфигурация
```

## Маркеры

| Маркер | Назначение |
|--------|------------|
| `@pytest.mark.unit` | Быстрые локальные тесты без реального HTTP и БД |
| `@pytest.mark.stand` | Любой тест, требующий внешнего поднятого стенда |
| `@pytest.mark.integration` | Stand-based API and repository integration |
| `@pytest.mark.e2e` | Длинные пользовательские workflow |
| `@pytest.mark.smoke` | Минимальная проверка доступности стенда |
| `@pytest.mark.serial` | Нельзя параллелить |
| `@pytest.mark.destructive` | Агрессивно изменяет состояние стенда |
| `@pytest.mark.requires_reset` | Требует заранее сброшенного known baseline |
| `@pytest.mark.stand_db` | Прямое обращение к stand database |

## Фикстуры

### Основные фикстуры для stand-тестов

- `stand_settings` → `StandSettings`: Настройки стенда из переменных окружения
- `stand_run_id` → `str`: Уникальный идентификатор запуска для namespacing
- `stand_client` → `httpx.Client`: Синхронный HTTP клиент для работы со стендом
- `stand_async_client` → `httpx.AsyncClient`: Асинхронный HTTP клиент

### Пример использования

```python
import pytest

@pytest.mark.stand
def test_something(stand_client, stand_run_id):
    # Используем stand_client для HTTP запросов
    response = stand_client.get("/api/health")
    assert response.status_code == 200
    
    # Используем stand_run_id для изоляции данных
    print(f"Test run ID: {stand_run_id}")
```

## Миграция существующих тестов

### Тесты-кандидаты для миграции на stand

Следующие тесты являются кандидатами для миграции на stand-слой:

- `test_auth_smoke.py` → `tests/stand/smoke/`
- `test_auth_routes.py` → `tests/stand/integration/`
- `test_balances_endpoints.py` → `tests/stand/integration/`
- `test_lost_assets_api.py` → `tests/stand/integration/`
- `test_recipients_create_regression.py` → `tests/stand/e2e/`

### Шаги миграции

1. Переместить файл в соответствующую поддиректорию `tests/stand/`
2. Добавить маркер `@pytest.mark.stand` (и при необходимости `integration`, `e2e`, `smoke`)
3. Заменить фикстуры:
   - `client` (ASGITransport) → `stand_client`
   - `session_factory`, `db_session` → использовать API стенда или `stand_db` фикстуры
4. Убрать создание приложения через `create_app(enable_startup_migrations=False)`
5. Убрать dependency overrides для `get_db`
6. Обновить создание тестовых данных через API стенда

## Устранение неполадок

### Ошибка: "Stand guard validation failed"

Проверьте, что все обязательные переменные окружения заданы корректно:

```bash
echo "SYNC_TEST_MODE=$SYNC_TEST_MODE"
echo "SYNC_TEST_ALLOW_STAND=$SYNC_TEST_ALLOW_STAND"
echo "SYNC_TEST_BASE_URL=$SYNC_TEST_BASE_URL"
echo "SYNC_TEST_ROOT_TOKEN=${SYNC_TEST_ROOT_TOKEN:0:10}..."
```

### Ошибка: "Stand preflight probe failed"

1. Убедитесь, что стенд запущен и доступен:
   ```bash
   curl $SYNC_TEST_BASE_URL/api/health
   ```

2. Проверьте, что root token корректен:
   ```bash
   curl -H "Authorization: Bearer $SYNC_TEST_ROOT_TOKEN" $SYNC_TEST_BASE_URL/api/health
   ```

3. Проверьте, что health и readiness endpoints возвращают 200.

### Stand-тесты не запускаются при обычном `pytest`

Это ожидаемое поведение. Для запуска stand-тестов используйте явный маркер:

```bash
pytest -m stand
```

### Хочу запустить и unit, и stand тесты

```bash
# Запустить все тесты (unit + stand)
pytest -m "unit or stand"

# Или временно отключить guard
pytest --tb=short
```

## Безопасность

### Защита от случайного запуска

Guard-цепочка защищает от:
- Случайного запуска stand-тестов в production среде
- Запуска без подтверждённого тестового стенда
- Использования неправильных credentials

### Изоляция данных

Каждый запуск получает уникальный `stand_run_id` для namespacing тестовых данных. Рекомендуется:
- Использовать префиксы в создаваемых сущностях
- Реализовать cleanup по `stand_run_id` после тестов
- Для destructive тестов использовать отдельный стенд

## Дальнейшие шаги

1. **Миграция API-тестов** — перенести тесты, использующие ASGITransport, на stand-слой
2. **Создание unit-слоя** — выделить pure unit тесты в `tests/unit/`
3. **Улучшение preflight probe** — добавить проверку test stand identity
4. **Реализация cleanup** — автоматический cleanup тестовых данных по run_id
5. **Параллельный запуск** — настройка параллельного выполнения stand-тестов с изоляцией