# Руководство по работе с репозиторием непринятых активов для клиентов

## Введение

Это руководство описывает, как клиентские приложения (Django-админка, мобильные приложения, веб-интерфейсы) могут взаимодействовать с API репозитория непринятых активов (lost assets) в SyncServer.

## Базовые понятия

**Lost asset (непринятый актив)** – товар, который не был принят при приёмке операции RECEIVE или MOVE. Например:
- Бракованные единицы при приходе
- Недостача при перемещении между складами
- Товар с повреждённой упаковкой

**Репозиторий непринятого** – специальный регистр, где хранятся такие активы до их разрешения (возврат, списание, перемещение).

## Авторизация

Все запросы требуют заголовка `X-User-Token` с токеном пользователя. Пользователь должен иметь доступ к сайту, на котором находится lost asset (через `UserAccessScope` с `can_view=true`).

## Основные сценарии

### 1. Просмотр списка непринятых активов

**Цель:** Отобразить таблицу с фильтрами и пагинацией.

**Endpoint:** `GET /api/v1/lost-assets`

**Пример запроса (Python):**
```python
import httpx

async def list_lost_assets(token: str, site_id: int = None, page: int = 1):
    async with httpx.AsyncClient() as client:
        params = {
            "page": page,
            "page_size": 50,
        }
        if site_id:
            params["site_id"] = site_id
        
        response = await client.get(
            "http://localhost:8000/api/v1/lost-assets",
            headers={"X-User-Token": token},
            params=params
        )
        response.raise_for_status()
        return response.json()
```

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

**Рекомендации по UI:**
- Отображать колонки: Товар (название, SKU), Склад, Количество, Дата обновления, Операция
- Добавить фильтры: по складу, товару, дате, количеству
- Реализовать пагинацию с информацией о total_count

### 2. Фильтрация по дате и количеству

**Цель:** Позволить пользователю искать активы, созданные в определённый период или с определённым количеством.

**Параметры:**
- `updated_after` – дата в формате ISO 8601 (например, `2026-04-01T00:00:00Z`)
- `updated_before` – дата в формате ISO 8601
- `qty_from` – минимальное количество (десятичное число)
- `qty_to` – максимальное количество

**Пример запроса:**
```
GET /api/v1/lost-assets?updated_after=2026-04-01T00:00:00Z&qty_from=10
```

**Пример на Django:**
```python
from datetime import datetime, timezone

def get_lost_assets(request):
    token = request.user.syncserver_token  # предположим, что токен сохранён
    updated_after = request.GET.get('updated_after')
    qty_from = request.GET.get('qty_from')
    
    # Формируем параметры
    params = {}
    if updated_after:
        params['updated_after'] = updated_after
    if qty_from:
        params['qty_from'] = qty_from
    
    # Выполняем запрос к SyncServer
    # ...
```

### 3. Просмотр деталей одного актива

**Цель:** Показать полную информацию о выбранном непринятом активе перед разрешением.

**Endpoint:** `GET /api/v1/lost-assets/{operation_line_id}`

**Пример запроса:**
```python
async def get_lost_asset_detail(token: str, operation_line_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8000/api/v1/lost-assets/{operation_line_id}",
            headers={"X-User-Token": token}
        )
        response.raise_for_status()
        return response.json()
```

**Ответ:** Те же поля, что и в элементе списка, но для одной записи.

**Использование в UI:**
- Открывать детальную страницу при клике на запись в таблице
- Показывать кнопки действий (Разрешить...)
- Отображать связанную информацию: операцию, склад-источник (если есть)

### 4. Разрешение непринятого актива

**Цель:** Выполнить одно из трёх действий: возврат, списание или перемещение.

**Endpoint:** `POST /api/v1/lost-assets/{operation_line_id}/resolve`

**Доступные действия:**

| Действие | Описание | Условия |
|----------|----------|---------|
| `return_to_source` | Возврат на исходный склад | Только для операций MOVE (есть source_site_id) |
| `write_off` | Списание (уничтожение) | Всегда доступно |
| `found_to_destination` | Перемещение на другой склад | Должен быть указан `destination_site_id` |

**Пример запроса на возврат:**
```python
async def resolve_return_to_source(token: str, operation_line_id: int, comment: str = ""):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://localhost:8000/api/v1/lost-assets/{operation_line_id}/resolve",
            headers={"X-User-Token": token},
            json={
                "action": "return_to_source",
                "comment": comment
            }
        )
        response.raise_for_status()
        return response.json()
```

**Пример запроса на перемещение:**
```json
{
  "action": "found_to_destination",
  "destination_site_id": 3,
  "comment": "Найден на складе Б, перемещён на склад В"
}
```

**UI-рекомендации:**
- Предоставить выпадающий список действий с пояснениями
- Для `found_to_destination` – показать список доступных складов (из `/api/v1/auth/sites`)
- Добавить поле для комментария (опционально)
- После успешного разрешения обновить список активов

### 5. Интеграция с операциями приёмки

**Цель:** Связать интерфейс приёмки операции с репозиторием непринятого.

**Поток:**
1. Пользователь выполняет приёмку операции RECEIVE/MOVE
2. Если указан `lost_qty > 0`, показать уведомление: "Создано X непринятых активов"
3. Предоставить ссылку на репозиторий непринятого с фильтром по operation_id

**Пример кода (после приёмки):**
```python
# После успешного accept_operation_lines
if lost_qty > 0:
    messages.info(
        request,
        f"Создано {lost_qty} непринятых активов. "
        f"<a href='/lost-assets/?operation_id={operation_id}'>Перейти к управлению</a>"
    )
```

## Обработка ошибок

### Общие ошибки

| Код | Причина | Действие |
|-----|---------|----------|
| 401 | Неверный или отсутствующий X-User-Token | Перенаправить на страницу входа |
| 403 | Нет доступа к сайту lost asset | Показать сообщение "У вас нет доступа к этому сайту" |
| 404 | Lost asset не найден | Показать "Запись не найдена", вернуться к списку |

### Ошибки при разрешении

- `400 Bad Request` – неверные параметры (например, нет destination_site_id для found_to_destination)
- `409 Conflict` – нарушение бизнес-правил (например, попытка return_to_source для RECEIVE)

**Пример обработки:**
```python
try:
    await resolve_lost_asset(token, operation_line_id, data)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 409:
        error_detail = e.response.json().get("detail", "Конфликт правил")
        show_error(f"Невозможно выполнить действие: {error_detail}")
    else:
        raise
```

## Пример полного workflow

### Сценарий: Приход с браком

1. **Создание операции прихода:**
   - Пользователь создаёт операцию RECEIVE на 100 единиц
   - Подтверждает операцию (submit)

2. **Приёмка с браком:**
   - Кладовщик принимает 95 единиц, указывает lost_qty=5
   - Система создаёт lost asset с 5 единицами

3. **Просмотр репозитория:**
   - Кладовщик открывает раздел "Непринятые активы"
   - Видит запись с 5 единицами товара

4. **Списание брака:**
   - Выбирает действие "write_off"
   - Вводит комментарий "Бракованная партия"
   - Подтверждает

5. **Результат:**
   - Lost asset удаляется из репозитория
   - Баланс склада не меняется (брак списан)
   - В аудит-логе фиксируется действие

## Интеграция с Django-админкой

### Модель для отображения

Создайте модель-прокси для отображения lost assets в Django-админке:

```python
# models.py
from django.db import models

class LostAssetProxy(models.Model):
    """Прокси-модель для отображения lost assets из SyncServer"""
    operation_line_id = models.IntegerField(primary_key=True)
    item_name = models.CharField(max_length=255)
    site_name = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    updated_at = models.DateTimeField()
    
    class Meta:
        managed = False
        verbose_name = "Непринятый актив"
        verbose_name_plural = "Непринятые активы"
```

### Admin-класс

```python
# admin.py
from django.contrib import admin
from .models import LostAssetProxy
import httpx

@admin.register(LostAssetProxy)
class LostAssetAdmin(admin.ModelAdmin):
    list_display = ['item_name', 'site_name', 'qty', 'updated_at']
    list_filter = ['site_name']
    actions = ['resolve_write_off']
    
    def get_queryset(self, request):
        # Загружаем данные из SyncServer
        token = request.user.syncserver_token
        response = httpx.get(
            "http://localhost:8000/api/v1/lost-assets",
            headers={"X-User-Token": token},
            params={"page_size": 100}
        )
        data = response.json()
        
        # Преобразуем в список объектов
        assets = []
        for item in data['items']:
            assets.append(LostAssetProxy(
                operation_line_id=item['operation_line_id'],
                item_name=item['item_name'],
                site_name=item['site_name'],
                qty=item['qty'],
                updated_at=item['updated_at']
            ))
        return assets
    
    def resolve_write_off(self, request, queryset):
        token = request.user.syncserver_token
        for asset in queryset:
            httpx.post(
                f"http://localhost:8000/api/v1/lost-assets/{asset.operation_line_id}/resolve",
                headers={"X-User-Token": token},
                json={"action": "write_off", "comment": "Списание из админки"}
            )
        self.message_user(request, f"Списано {queryset.count()} активов")
    
    resolve_write_off.short_description = "Списать выбранные активы"
```

## Тестирование клиентской интеграции

### Моки для разработки

Для разработки без реального SyncServer можно использовать моки:

```python
# mocks.py
from unittest.mock import Mock, AsyncMock

def mock_lost_assets_api():
    mock_response = Mock()
    mock_response.json.return_value = {
        "items": [
            {
                "operation_line_id": 1,
                "item_name": "Тестовый товар",
                "site_name": "Тестовый склад",
                "qty": "10.00",
                "updated_at": "2026-04-16T10:00:00Z"
            }
        ],
        "total_count": 1,
        "page": 1,
        "page_size": 50
    }
    mock_response.status_code = 200
    return mock_response
```

### Интеграционные тесты

```python
# tests.py
import pytest
from django.test import TestCase
from .services import LostAssetService

class LostAssetIntegrationTest(TestCase):
    @pytest.mark.integration
    def test_list_lost_assets(self):
        service = LostAssetService()
        result = service.list_lost_assets(token="test-token")
        self.assertIn('items', result)
        self.assertIsInstance(result['items'], list)
```

## Производительность и кэширование

### Рекомендации

1. **Кэширование списка:** Lost assets меняются нечасто, можно кэшировать на 5-10 минут
2. **Инкрементальная загрузка:** Для больших списков использовать пагинацию
3. **Фоновая синхронизация:** Мобильные приложения могут синхронизировать данные в фоне

### Пример кэширования в Django

```python
from django.core.cache import cache

def get_cached_lost_assets(token: str, force_refresh: bool = False):
    cache_key = f"lost_assets_{token}"
    
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached:
            return cached
    
    # Загрузка из API
    assets = fetch_lost_assets_from_api(token)
    
    # Кэшируем на 5 минут
    cache.set(cache_key, assets, timeout=300)
    
    return assets
```

## Безопасность

### Проверки на клиенте

1. **Валидация прав:** Перед разрешением проверять, что пользователь имеет доступ к сайту
2. **Подтверждение действий:** Для write_off запрашивать подтверждение
3. **Логирование:** Логировать все действия с lost assets

### Пример проверки прав

```python
def can_resolve_lost_asset(user, lost_asset_site_id):
    # Проверяем через UserAccessScope
    return user.access_scopes.filter(
        site_id=lost_asset_site_id,
        can_operate=True,
        is_active=True
    ).exists()
```

## Дополнительные ресурсы

- [Полная документация API](API_REFERENCE.md#asset-register-api-read-only)
- [Система приёмки](ACCEPTANCE_SYSTEM_GUIDE.md)
- [Примеры кода](https://github.com/your-repo/examples)

## Поддержка

При возникновении вопросов:
1. Проверьте логи SyncServer
2. Убедитесь в правильности токена и прав доступа
3. Обратитесь к разработчикам с примером запроса и ответа