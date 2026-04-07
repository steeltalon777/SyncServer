# Health Checks

SyncServer предоставляет расширенную систему health checks для мониторинга состояния системы и её зависимостей.

## Обзор

Система health checks включает несколько endpoints для разных целей мониторинга:

1. **Базовые проверки** - для обратной совместимости
2. **Детализированные проверки** - для комплексного мониторинга
3. **Readiness проверки** - для load balancers и orchestration
4. **Liveness проверки** - для container orchestration

## Endpoints

### 1. Базовый Health Check
```
GET /api/v1/health
```

**Назначение**: Простая проверка что приложение запущено.

**Ответ**:
```json
{
  "status": "ok"
}
```

### 2. Readiness Check (базовый)
```
GET /api/v1/ready
```

**Назначение**: Проверка готовности приложения к работе (включает проверку БД).

**Ответ**:
```json
{
  "status": "ready",
  "db": 1
}
```

### 3. Детализированный Health Check
```
GET /api/v1/health/detailed
```

**Назначение**: Комплексная проверка всех зависимостей системы.

**Ответ**:
```json
{
  "status": "healthy",
  "timestamp": "2026-04-06T06:42:52Z",
  "version": "1.0.0",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 8.2,
      "details": "Database connection successful",
      "error": null
    },
    "config": {
      "status": "healthy",
      "latency_ms": null,
      "details": "All required configurations are present and valid",
      "error": null
    },
    "cache": {
      "status": "not_configured",
      "latency_ms": null,
      "details": "Redis health check is disabled",
      "error": null
    }
  }
}
```

### 4. Readiness Check (расширенный)
```
GET /api/v1/health/readiness
```

**Назначение**: Проверка готовности критических зависимостей для load balancers.

**Ответ**:
```json
{
  "ready": true,
  "timestamp": "2026-04-06T06:42:52Z",
  "details": {
    "database": true,
    "config": true
  }
}
```

### 5. Liveness Check
```
GET /api/v1/health/liveness
```

**Назначение**: Проверка живучести приложения для container orchestration.

**Ответ**:
```json
{
  "alive": true,
  "timestamp": "2026-04-06T06:42:52Z"
}
```

## Статусы

### Общие статусы системы:
- **`healthy`** - все компоненты работают нормально
- **`degraded`** - некоторые не критичные компоненты не работают
- **`unhealthy`** - критические компоненты не работают

### Статусы отдельных проверок:
- **`healthy`** - проверка пройдена успешно
- **`unhealthy`** - проверка не пройдена (ошибка)
- **`not_configured`** - компонент не настроен (не критично)
- **`degraded`** - компонент работает с ограничениями

## Проверяемые компоненты

### 1. Database (PostgreSQL)
- **Критичность**: Высокая
- **Проверка**: Подключение к базе данных и выполнение простого запроса
- **Конфигурация**: `DATABASE_URL`

### 2. Configuration
- **Критичность**: Высокая
- **Проверка**: Наличие и валидность обязательных конфигурационных параметров
- **Конфигурация**: Все обязательные параметры из `app/core/config.py`

### 3. Cache (Redis) - опционально
- **Критичность**: Низкая
- **Проверка**: Подключение к Redis (если настроено)
- **Конфигурация**:
  - `HEALTH_CHECK_ENABLE_REDIS` (по умолчанию `false`)
  - `HEALTH_CHECK_REDIS_URL`

## Конфигурация

### Environment Variables

```env
# Таймаут для health checks (секунды)
HEALTH_CHECK_TIMEOUT=5.0

# Включить проверку Redis
HEALTH_CHECK_ENABLE_REDIS=false

# URL для подключения к Redis
HEALTH_CHECK_REDIS_URL=redis://localhost:6379

# Включить проверку внешних сервисов
HEALTH_CHECK_ENABLE_EXTERNAL_SERVICES=false

# Список URL внешних сервисов для проверки
HEALTH_CHECK_EXTERNAL_SERVICES=["https://api.example.com/health"]
```

### Значения по умолчанию
- `HEALTH_CHECK_TIMEOUT`: 5.0 секунд
- `HEALTH_CHECK_ENABLE_REDIS`: false
- `HEALTH_CHECK_ENABLE_EXTERNAL_SERVICES`: false

## Использование в Production

### Kubernetes
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: syncserver
spec:
  containers:
  - name: syncserver
    image: syncserver:latest
    ports:
    - containerPort: 8000
    livenessProbe:
      httpGet:
        path: /api/v1/health/liveness
        port: 8000
      initialDelaySeconds: 30
      periodSeconds: 10
    readinessProbe:
      httpGet:
        path: /api/v1/health/readiness
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 5
```

### Load Balancers
- Используйте `/api/v1/health/readiness` для health checks load balancer
- Endpoint возвращает HTTP 200 когда `ready: true`
- Endpoint возвращает HTTP 503 когда `ready: false`

### Мониторинг
- Используйте `/api/v1/health/detailed` для комплексного мониторинга
- Интегрируйте с системами мониторинга (Prometheus, Datadog, etc.)
- Настройте алерты на статусы `unhealthy` и `degraded`

## Расширение системы

### Добавление новой проверки

1. Создайте класс унаследованный от `HealthChecker`:
```python
from app.services.health_service import HealthChecker, HealthStatus
from app.schemas.health import HealthCheckDetail

class NewComponentHealthChecker(HealthChecker):
    def __init__(self):
        super().__init__("new_component", critical=False)

    async def check(self) -> HealthCheckDetail:
        # Реализация проверки
        pass
```

2. Добавьте checker в `HealthService`:
```python
class HealthService:
    def __init__(self, session: AsyncSession):
        # ...
        self.checkers: list[HealthChecker] = [
            # ...
            NewComponentHealthChecker(),
        ]
```

### Кастомные проверки
- **Критические проверки**: `critical=True` в конструкторе
- **Не критические проверки**: `critical=False` (влияют только на статус `degraded`)
- **Таймауты**: Настраиваются через `HEALTH_CHECK_TIMEOUT`

## Отладка

### Проблемы с подключением к БД
1. Проверьте `DATABASE_URL` в `.env` файле
2. Убедитесь что PostgreSQL запущен и доступен
3. Проверьте логи приложения

### Проблемы с конфигурацией
1. Проверьте наличие всех обязательных переменных окружения
2. Убедитесь что `.env` файл загружается правильно
3. Проверьте формат URL базы данных

### Тестирование
```bash
# Запуск тестов health checks
pytest tests/test_health_service.py -v
pytest tests/test_health_endpoints.py -v

# Ручное тестирование endpoints
curl http://localhost:8000/api/v1/health/detailed
curl http://localhost:8000/api/v1/health/readiness
curl http://localhost:8000/api/v1/health/liveness
```

## Миграция с старых endpoints

Старые endpoints (`/api/v1/health` и `/api/v1/ready`) сохраняются для обратной совместимости. Рекомендуется перейти на новые endpoints для более комплексного мониторинга.
