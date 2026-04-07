# Руководство по интеграции Django с SyncServer

## Введение

Данное руководство предназначено для разработчиков, работающих с Warehouse_web - Django веб-клиентом для SyncServer. Оно описывает архитектурные принципы, лучшие практики и технические детали интеграции.

## Архитектурный обзор

### Роли в системе
- **SyncServer**: Источник истины для всех доменных данных (склады, товары, операции, остатки)
- **Warehouse_web**: Django SSR веб-клиент, предоставляющий пользовательский интерфейс
- **Браузеры пользователей**: Конечные потребители веб-интерфейса

### Ключевые принципы
1. **Все доменные данные в SyncServer** - Django хранит только техническое состояние
2. **Централизованный клиентский слой** - Все API вызовы через `apps/sync_client/`
3. **Двухуровневая аутентификация** - Django сессии + SyncServer токены
4. **Минимальная локальная персистентность** - Только то, что необходимо для работы UI

## Клиентский слой (`apps/sync_client/`)

### Основные компоненты

#### 1. `SyncServerClient` - Базовый транспортный клиент
```python
# Пример использования
from apps.sync_client.client import SyncServerClient

client = SyncServerClient(
    base_url=settings.SYNCSERVER_URL,
    user_id=request.user.id,
    site_id=active_site_id,
    request=request  # Для автоматического добавления заголовков
)
```

#### 2. Доменные API клиенты
```python
from apps.sync_client.api.catalog import CatalogAPI
from apps.sync_client.api.operations import OperationsAPI
from apps.sync_client.api.balances import BalancesAPI

# Инициализация
catalog_api = CatalogAPI(client)
operations_api = OperationsAPI(client)
balances_api = BalancesAPI(client)

# Использование
items = await catalog_api.get_items(page=1, per_page=50)
operation = await operations_api.get_operation(operation_id="...")
```

#### 3. `SyncServerRootAdminClient` - Для root операций
```python
from apps.sync_client.client_root import SyncServerRootAdminClient

root_client = SyncServerRootAdminClient(
    base_url=settings.SYNCSERVER_URL,
    request=request
)
```

### Конфигурация

#### Настройки Django (`settings.py`)
```python
# Обязательные настройки
SYNCSERVER_URL = env("SYNCSERVER_URL", default="http://localhost:8000")
SYNCSERVER_TIMEOUT = env.int("SYNCSERVER_TIMEOUT", default=30)
SYNCSERVER_MAX_RETRIES = env.int("SYNCSERVER_MAX_RETRIES", default=3)

# Опциональные настройки
SYNCSERVER_ENABLE_CACHE = env.bool("SYNCSERVER_ENABLE_CACHE", default=True)
SYNCSERVER_CACHE_TTL = env.int("SYNCSERVER_CACHE_TTL", default=300)
```

## Аутентификация и авторизация

### Двухуровневая система

#### Уровень 1: Django Authentication
```python
# Стандартная Django аутентификация
from django.contrib.auth import authenticate, login

user = authenticate(request, username=username, password=password)
if user is not None:
    login(request, user)
    # Запуск синхронизации с SyncServer
    await sync_auth_login(request, user)
```

#### Уровень 2: SyncServer Authentication
```python
# Функции синхронизации
from apps.sync_client.auth import sync_auth_login, sync_auth_logout

# Логин - получение токена от SyncServer
async def sync_auth_login(request, django_user):
    identity = await get_syncserver_identity(django_user)
    request.session['sync_identity'] = identity
    # Сохранение в SyncUserBinding
    await SyncUserBinding.objects.update_or_create(
        user=django_user,
        defaults={
            'syncserver_user_id': identity.user_id,
            'sync_user_token': identity.token,
            'sync_role': identity.role,
            'default_site_id': identity.default_site_id,
            'site_ids': identity.site_ids,
        }
    )
```

### Identity в сессии
```python
# Получение identity
from apps.sync_client.auth import get_sync_identity

def some_view(request):
    identity = get_sync_identity(request)
    if not identity:
        return redirect('login')

    # Использование identity в API вызовах
    client = SyncServerClient(
        user_id=identity.user_id,
        site_id=identity.site_id,
        token=identity.token
    )
```

### Middleware
```python
# apps/sync_client/middleware.py
class SyncAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Валидация SyncServer identity
        identity = get_sync_identity(request)
        if identity and identity.is_expired():
            # Обновление токена
            identity.refresh()

        response = self.get_response(request)
        return response
```

## Модели данных в Django

### Локальные модели (хранятся в Django БД)

#### 1. `SyncUserBinding` - Связь Django пользователя с SyncServer
```python
class SyncUserBinding(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    syncserver_user_id = models.UUIDField()
    sync_user_token = models.CharField(max_length=255)
    sync_role = models.CharField(max_length=50)
    default_site_id = models.CharField(max_length=50, null=True, blank=True)
    site_ids = models.JSONField(default=list)
    sync_status = models.CharField(max_length=20, default='active')
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sync_user_bindings'
```

#### 2. Сессионные данные (не сохраняются в БД)
- Активный сайт (`active_site_id`)
- Identity объект
- Временные данные формы

### Чего НЕ следует хранить в Django
- **Товары и категории** - Используйте кэш, но не БД
- **Операции** - Всегда запрашивайте из SyncServer
- **Остатки** - Рассчитывайте на лету или кэшируйте
- **Пользовательские права** - Хранятся в SyncServer как `UserAccessScope`

## Паттерны интеграции

### Паттерн 1: Тонкий контроллер, толстый сервис
```python
# views.py (тонкий)
from apps.catalog.services import CatalogService

def catalog_items(request):
    service = CatalogService(request)
    items = service.get_items(page=request.GET.get('page', 1))
    return render(request, 'catalog/items.html', {'items': items})

# services.py (толстый)
class CatalogService:
    def __init__(self, request):
        self.request = request
        self.client = SyncServerClient.from_request(request)
        self.catalog_api = CatalogAPI(self.client)

    def get_items(self, page=1):
        # Проверка кэша
        cache_key = f"catalog_items_{page}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # API вызов
        try:
            items = self.catalog_api.get_items(page=page, per_page=50)
            # Трансформация данных для шаблона
            transformed = self._transform_items(items)
            # Кэширование
            cache.set(cache_key, transformed, timeout=300)
            return transformed
        except SyncServerError as e:
            # Обработка ошибок
            logger.error(f"Failed to fetch catalog items: {e}")
            return []
```

### Паттерн 2: Единый клиент на запрос
```python
# deps.py (dependency injection)
def get_sync_client(request):
    """Возвращает настроенный клиент для текущего запроса"""
    identity = get_sync_identity(request)
    if not identity:
        raise AuthenticationError("No sync identity")

    return SyncServerClient(
        user_id=identity.user_id,
        site_id=identity.site_id or identity.default_site_id,
        token=identity.token,
        request=request
    )

# views.py
def some_view(request):
    client = get_sync_client(request)
    catalog_api = CatalogAPI(client)
    # ...
```

### Паттерн 3: Оптимистичные обновления
```python
class OperationCreateView(View):
    def post(self, request):
        # Валидация формы
        form = OperationForm(request.POST)
        if not form.is_valid():
            return render(request, 'error.html', {'errors': form.errors})

        # Оптимистичное создание в UI
        operation_data = form.cleaned_data

        # Асинхронное создание в SyncServer
        try:
            client = get_sync_client(request)
            operations_api = OperationsAPI(client)
            operation = await operations_api.create_operation(operation_data)

            # Успех - redirect к новой операции
            return redirect('operation_detail', operation_id=operation.id)
        except SyncServerError as e:
            # Ошибка - откат UI состояния
            messages.error(request, f"Failed to create operation: {e}")
            return render(request, 'operation_create.html', {'form': form})
```

## Обработка ошибок

### Иерархия исключений
```python
# apps/sync_client/exceptions.py
class SyncServerError(Exception):
    """Базовое исключение для ошибок SyncServer"""
    pass

class SyncServerAuthenticationError(SyncServerError):
    """Ошибка аутентификации (401, 403)"""
    pass

class SyncServerValidationError(SyncServerError):
    """Ошибка валидации (422)"""
    pass

class SyncServerNotFoundError(SyncServerError):
    """Ресурс не найден (404)"""
    pass

class SyncServerTimeoutError(SyncServerError):
    """Таймаут соединения"""
    pass

class SyncServerUnavailableError(SyncServerError):
    """Сервис недоступен (503)"""
    pass
```

### Обработка в views
```python
from apps.sync_client.exceptions import (
    SyncServerAuthenticationError,
    SyncServerUnavailableError
)

def catalog_view(request):
    try:
        service = CatalogService(request)
        items = service.get_items()
        return render(request, 'catalog.html', {'items': items})

    except SyncServerAuthenticationError:
        # Перенаправление на логин
        messages.error(request, "Session expired. Please login again.")
        return redirect('login')

    except SyncServerUnavailableError:
        # Показать страницу обслуживания
        return render(request, 'maintenance.html', status=503)

    except SyncServerError as e:
        # Общая ошибка
        logger.error(f"SyncServer error: {e}")
        return render(request, 'error.html',
                     {'error': 'Service temporarily unavailable'},
                     status=500)
```

## Кэширование

### Стратегии кэширования

#### 1. Кэш ответов API
```python
from django.core.cache import cache
from functools import wraps

def cache_api_response(prefix, ttl=300):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Генерация ключа кэша
            cache_key = f"{prefix}_{hash(frozenset(kwargs.items()))}"

            # Попытка получить из кэша
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

            # Вызов API
            result = await func(*args, **kwargs)

            # Сохранение в кэш
            cache.set(cache_key, result, timeout=ttl)
            return result
        return wrapper
    return decorator

# Использование
class CatalogAPI:
    @cache_api_response("catalog_items", ttl=300)
    async def get_items(self, page=1, per_page=50):
        response = await self.client.get(
            f"/api/v1/catalog/items",
            params={"page": page, "per_page": per_page}
        )
        return response.json()
```

#### 2. Инвалидация кэша
```python
# Сигналы для инвалидации кэша
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=SyncUserBinding)
def invalidate_user_cache(sender, instance, **kwargs):
    # Инвалидация кэша, связанного с пользователем
    cache.delete_pattern(f"user_{instance.user_id}_*")
```

#### 3. Многоуровневое кэширование
```python
class MultiLevelCache:
    def __init__(self):
        self.memory_cache = {}
        self.redis_cache = cache
        self.db_cache = {}  # Для часто запрашиваемых данных

    async def get(self, key):
        # Уровень 1: Memory
        if key in self.memory_cache:
            return self.memory_cache[key]

        # Уровень 2: Redis
        redis_value = self.redis_cache.get(key)
        if redis_value is not None:
            # Заполняем memory cache
            self.memory_cache[key] = redis_value
            return redis_value

        # Уровень 3: Database/API
        api_value = await self._fetch_from_api(key)
        if api_value:
            # Заполняем оба кэша
            self.memory_cache[key] = api_value
            self.redis_cache.set(key, api_value, timeout=300)

        return api_value
```

## Тестирование

### Моки для SyncServer API
```python
# tests/mocks/sync_server.py
from unittest.mock import Mock, AsyncMock

class MockSyncServerClient:
    def __init__(self):
        self.catalog_api = Mock()
        self.operations_api = Mock()
        self.balances_api = Mock()

        # Настройка моков
        self.catalog_api.get_items = AsyncMock(return_value=[
            {"id": 1, "name": "Item 1"},
            {"id": 2, "name": "Item 2"},
        ])

        self.operations_api.create_operation = AsyncMock(
            return_value={"id": "op-123", "status": "draft"}
        )

# Использование в тестах
@pytest.fixture
def mock_sync_client():
    return MockSyncServerClient()

@pytest.mark.django_db
async def test_catalog_view(client, mock_sync_client, monkeypatch):
    # Монкипатч реального клиента
    monkeypatch.setattr(
        'apps.sync_client.client.SyncServerClient',
        lambda *args, **kwargs: mock_sync_client
    )

    response = client.get('/catalog/')
    assert response.status_code == 200
    assert b'Item 1' in response.content
```

### Интеграционные тесты
```python
# tests/integration/test_syncserver_integration.py
@pytest.mark.integration
class TestSyncServerIntegration:
    @pytest.fixture(autouse=True)
    def setup(self, settings):
        settings.SYNCSERVER_URL = "http://test-syncserver:8000"

    @pytest.mark.asyncio
    async def test_catalog_api_integration(self):
        """Реальный тест интеграции с SyncServer"""
        client = SyncServerClient(
            base_url=settings.SYNCSERVER_URL,
            user_id=test_user_id,
            site_id=test_site_id
        )

        catalog_api = CatalogAPI(client)
        items = await catalog_api.get_items()

        assert isinstance(items, list)
        # Проверка структуры ответа
        if items:
            assert 'id' in items[0]
            assert 'name' in items[0]
```

## Производительность и оптимизация

### Best practices

#### 1. Параллельные запросы
```python
import asyncio

async def fetch_dashboard_data(request):
    client = get_sync_client(request)

    # Параллельное выполнение независимых запросов
    catalog_api = CatalogAPI(client)
    balances_api = BalancesAPI(client)
    operations_api = OperationsAPI(client)

    # Gather для параллельного выполнения
    catalog_task = catalog_api.get_items(per_page=10)
    balances_task = balances_api.get_summary()
    operations_task = operations_api.get_recent_operations(limit=5)

    catalog_items, balances, recent_operations = await asyncio.gather(
        catalog_task, balances_task, operations_task,
        return_exceptions=True  # Не падать при ошибке одного из запросов
    )

    return {
        'catalog_items': catalog_items,
        'balances': balances,
        'recent_operations': recent_operations
    }
```

#### 2. Пагинация и lazy loading
```python
# Infinite scroll или пагинация
class CatalogListView(View):
    async def get(self, request):
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 50))

        client = get_sync_client(request)
        catalog_api = CatalogAPI(client)

        # Запрос только нужной страницы
        items = await catalog_api.get_items(page=page, per_page=per_page)

        # Возврат JSON для AJAX или HTML для полной страницы
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'items': items, 'page': page})

        return render(request, 'catalog/list.html', {
            'items': items,
            'page': page,
            'has_next': len(items) == per_page
        })
```

#### 3. Сжатие и минификация
```python
# settings.py
MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',
    # ...
]

# Для статических файлов
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
```

## Мониторинг и логирование

### Настройка логирования
```python
# settings.py
LOGGING = {
    'version': 1,
    'handlers': {
        'syncserver': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/syncserver.log',
            'maxBytes': 1024 * 1024 * 10,  # 10 MB
            'backupCount': 5,
            'formatter': 'detailed',
        },
    },
    'loggers': {
        'apps.sync_client': {
            'handlers': ['syncserver'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

### Метрики Prometheus
```python
# metrics.py
from prometheus_client import Counter, Histogram

SYNCSERVER_REQUESTS = Counter(
    'django_syncserver_requests_total',
    'Total SyncServer API requests',
    ['method', 'endpoint', 'status']
)

SYNCSERVER_REQUEST_DURATION = Histogram(
    'django_syncserver_request_duration_seconds',
    'SyncServer API request duration',
    ['method', 'endpoint']
)

# Декоратор для сбора метрик
def track_syncserver_metrics(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        endpoint = kwargs.get('endpoint', 'unknown')
        method = kwargs.get('method', 'GET')

        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time

            # Запись метрик
            SYNCSERVER_REQUESTS.labels(
                method=method,
                endpoint=endpoint,
                status='success'
            ).inc()

            SYNCSERVER_REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)

            return result
        except Exception as e:
            SYNCSERVER_REQUESTS.labels(
                method=method,
                endpoint=endpoint,
                status='error'
            ).inc()
            raise e
    return wrapper
```

## Развертывание и эксплуатация

### Health checks
```python
# health_checks.py
from health_check.backends import BaseHealthCheckBackend
from health_check.exceptions import ServiceUnavailable

class SyncServerHealthCheck(BaseHealthCheckBackend):
    def check_status(self):
        try:
            client = SyncServerClient(
                base_url=settings.SYNCSERVER_URL,
                timeout=5  # Короткий таймаут для health check
            )

            # Проверка readiness эндпоинта
            response = client.get("/health/readiness")
            if response.status_code != 200:
                raise ServiceUnavailable("SyncServer not ready")

            # Проверка детального health check
            detailed = client.get("/health/detailed")
            data = detailed.json()

            if data['status'] != 'healthy':
                unhealthy = [c['name'] for c in data['checks']
                           if c['status'] != 'healthy']
                raise ServiceUnavailable(
                    f"SyncServer components unhealthy: {unhealthy}"
                )

        except Exception as e:
            raise ServiceUnavailable(f"SyncServer health check failed: {e}")
```

### Миграции данных
```python
# management/commands/migrate_from_legacy.py
from django.core.management.base import BaseCommand
from apps.legacy.models import UserProfile
from apps.sync_client.models import SyncUserBinding

class Command(BaseCommand):
    help = 'Migrate from legacy UserProfile to SyncUserBinding'

    def handle(self, *args, **options):
        for profile in UserProfile.objects.all():
            # Создание SyncUserBinding на основе UserProfile
            binding, created = SyncUserBinding.objects.get_or_create(
                user=profile.user,
                defaults={
                    'syncserver_user_id': profile.external_id,
                    'sync_user_token': profile.api_token,
                    'sync_role': profile.role,
                    'default_site_id': profile.default_site,
                    'site_ids': profile.sites or [],
                }
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Migrated user {profile.user.username}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'User {profile.user.username} already migrated')
                )
```

## Заключение

Данное руководство охватывает ключевые аспекты интеграции Django с SyncServer. Помните основные принципы:

1. **SyncServer - источник истины**, Django - клиент
2. **Централизуйте логику интеграции** в `apps/sync_client/`
3. **Используйте кэширование** для улучшения производительности
4. **Обрабатывайте ошибки** грациозно
5. **Мониторьте производительность** и доступность

Для дополнительной информации обратитесь к:
- [SyncServer API документация](docs/API_REFERENCE.md)
- [Архитектурные решения (ADR)](docs/adr/)
- [План реализации улучшений](plans/django_client_implementation_plan.md)

---

*Документ создан: 2026-04-07*
*Версия: 1.0*
*Статус: Актуально для Warehouse_web*
