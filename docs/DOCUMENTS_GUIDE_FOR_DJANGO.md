# Руководство по работе с документами (накладными) для Django клиента

## Обзор архитектуры документов SyncServer

SyncServer предоставляет полный цикл работы с документами (накладными, актами, счетами-фактурами):
1. **Генерация документа** на основе операции (создание снапшота данных)
2. **Хранение документа** с неизменяемым payload (исторические слепки)
3. **Рендеринг документа** в HTML/PDF (серверный или клиентский)
4. **Управление жизненным циклом** (черновик → финализация → аннулирование)

## 1. Основные понятия

### Типы документов
- `waybill` - Товарная накладная (ТОРГ-12)
- `acceptance_certificate` - Акт приёмки
- `act` - Акт выполненных работ
- `invoice` - Счёт-фактура

### Статусы документа
- `draft` - Черновик (можно изменять)
- `finalized` - Финализирован (неизменяемый, готов к печати)
- `void` - Аннулирован
- `superseded` - Заменён новой версией

### Payload (полезная нагрузка)
- JSON-объект со всеми данными документа на момент генерации
- Включает снапшоты: названия товаров, единиц измерения, получателей, площадок
- Гарантирует неизменность документа при изменении исходных данных

## 2. API endpoints для работы с документами

### Базовые endpoints
```
POST   /api/v1/documents/generate          # Создать документ из операции
GET    /api/v1/documents/{document_id}     # Получить документ (с payload)
GET    /api/v1/documents/{document_id}/render?format=html|pdf  # Готовый рендер
GET    /api/v1/documents                   # Список документов с фильтрацией
PATCH  /api/v1/documents/{document_id}/status  # Изменить статус
```

### Operation-scoped endpoints
```
GET    /api/v1/documents/operations/{operation_id}/documents    # Документы операции
POST   /api/v1/documents/operations/{operation_id}/documents    # Создать документ для операции
```

## 3. Практические сценарии для Django клиента

### Сценарий 1: Генерация накладной для операции

```python
# apps/documents/services.py
import httpx
from django.conf import settings
from apps.sync_client.auth import get_sync_identity

class DocumentService:
    def __init__(self, request):
        self.request = request
        self.identity = get_sync_identity(request)
        self.base_url = settings.SYNCSERVER_URL
        self.headers = {
            "X-User-Token": self.identity.token,
            "Content-Type": "application/json"
        }
    
    async def generate_waybill(self, operation_id, auto_finalize=True):
        """Сгенерировать накладную для операции"""
        url = f"{self.base_url}/api/v1/documents/generate"
        
        payload = {
            "operation_id": str(operation_id),
            "document_type": "waybill",
            "template_name": "waybill_v1",  # опционально
            "auto_finalize": auto_finalize,
            "language": "ru",
            "basis_type": "contract",  # опционально
            "basis_number": "42/2026",  # опционально
            "basis_date": "2026-04-15T00:00:00Z"  # опционально
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
    
    async def get_document(self, document_id):
        """Получить документ по ID"""
        url = f"{self.base_url}/api/v1/documents/{document_id}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
```

### Сценарий 2: Отображение накладной в Django View

```python
# apps/documents/views.py
from django.shortcuts import render
from django.http import HttpResponse
from apps.documents.services import DocumentService

async def document_detail(request, document_id):
    """Страница просмотра документа"""
    service = DocumentService(request)
    document = await service.get_document(document_id)
    
    context = {
        'document': document,
        'payload': document['payload'],  # сырые данные для клиентского рендеринга
    }
    return render(request, 'documents/detail.html', context)

async def document_print(request, document_id):
    """Печать документа (серверный рендеринг HTML)"""
    service = DocumentService(request)
    
    # Вариант 1: Использовать готовый HTML от SyncServer
    url = f"{settings.SYNCSERVER_URL}/api/v1/documents/{document_id}/render?format=html"
    headers = {"X-User-Token": get_sync_identity(request).token}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return HttpResponse(response.content, content_type='text/html')
    
    # Вариант 2: Клиентский рендеринг (см. раздел 4)
```

### Сценарий 3: Скачивание PDF

```python
async def document_download_pdf(request, document_id):
    """Скачать документ в PDF"""
    service = DocumentService(request)
    
    url = f"{settings.SYNCSERVER_URL}/api/v1/documents/{document_id}/render?format=pdf"
    headers = {"X-User-Token": get_sync_identity(request).token}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        
        # Создаем HTTP ответ с PDF
        http_response = HttpResponse(
            response.content,
            content_type='application/pdf'
        )
        http_response['Content-Disposition'] = f'attachment; filename="document_{document_id}.pdf"'
        return http_response
```

### Сценарий 4: Список документов с фильтрацией

```python
async def document_list(request):
    """Список документов с пагинацией"""
    service = DocumentService(request)
    
    params = {
        'site_id': request.GET.get('site_id'),
        'document_type': request.GET.get('type'),
        'status': request.GET.get('status'),
        'date_from': request.GET.get('date_from'),
        'date_to': request.GET.get('date_to'),
        'offset': request.GET.get('offset', 0),
        'limit': request.GET.get('limit', 50),
    }
    
    url = f"{settings.SYNCSERVER_URL}/api/v1/documents"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=service.headers, params=params)
        response.raise_for_status()
        documents = response.json()
    
    return render(request, 'documents/list.html', {'documents': documents})
```

## 4. Клиентский рендеринг документов в Django

### Зачем нужен клиентский рендеринг?
- Кастомизация оформления под бренд компании
- Интеграция с корпоративными шаблонами
- Локальная обработка без запросов к SyncServer
- Офлайн-генерация документов

### Структура payload документа

```python
# Пример payload накладной
payload = {
    "document": {
        "id": "uuid",
        "document_number": "WB-1-20260415-001",
        "document_type": "waybill",
        "status": "finalized",
        "created_at": "2026-04-15T10:30:00Z",
        "finalized_at": "2026-04-15T10:30:00Z",
    },
    "operation": {
        "id": "uuid",
        "operation_type": "RECEIVE",
        "status": "submitted",
        "effective_at": "2026-04-15T00:00:00Z",
        "notes": "Поступление товара",
    },
    "site": {
        "id": 1,
        "name": "Основной склад",
        "code": "MAIN",
        "address": "г. Москва, ул. Примерная, д. 1",
    },
    "destination_site": {  # для MOVE операций
        "id": 2,
        "name": "Филиал",
        "code": "BRANCH",
    },
    "created_by_user": {
        "id": "uuid",
        "username": "ivanov",
        "full_name": "Иван Иванов",
        "role": "storekeeper",
    },
    "submitted_by_user": {
        "id": "uuid",
        "username": "petrov",
        "full_name": "Петр Петров",
        "role": "chief_storekeeper",
    },
    "lines": [
        {
            "line_number": 1,
            "item_id": 10,
            "item_name_snapshot": "Ноутбук Dell XPS 15",
            "sku_snapshot": "NB-DELL-XPS15",
            "unit_id": 1,
            "unit_symbol_snapshot": "шт.",
            "qty": 5,
            "price": 150000.00,  # если есть
            "total": 750000.00,  # если есть
            "recipient_id": 1,
            "recipient_name_snapshot": "ООО 'ТехноПарк'",
        }
    ],
    "basis": {  # основание документа
        "type": "contract",
        "number": "42/2026",
        "date": "2026-04-01T00:00:00Z",
    },
    "metadata": {
        "payload_schema_version": "1.0.0",
        "language": "ru",
        "template_name": "waybill_v1",
    }
}
```

### Django шаблон для рендеринга накладной

```html
<!-- templates/documents/render_waybill.html -->
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Товарная накладная {{ document.document_number }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { text-align: center; margin-bottom: 30px; }
        .document-title { font-size: 18px; font-weight: bold; }
        .document-number { font-size: 16px; margin-top: 10px; }
        .section { margin-bottom: 20px; }
        .section-title { font-weight: bold; border-bottom: 1px solid #000; margin-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        th, td { border: 1px solid #000; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .totals { text-align: right; font-weight: bold; }
        .signatures { display: flex; justify-content: space-between; margin-top: 50px; }
        .signature-block { width: 45%; }
    </style>
</head>
<body>
    <div class="header">
        <div class="document-title">ТОВАРНАЯ НАКЛАДНАЯ № {{ document.document_number }}</div>
        <div class="document-number">от {{ document.created_at|date:"d.m.Y" }}</div>
    </div>

    <div class="section">
        <div class="section-title">Отправитель</div>
        <div>{{ site.name }} ({{ site.code }})</div>
        <div>{{ site.address }}</div>
    </div>

    <div class="section">
        <div class="section-title">Получатель</div>
        {% if destination_site %}
            <div>{{ destination_site.name }} ({{ destination_site.code }})</div>
        {% else %}
            <div>Согласно операции</div>
        {% endif %}
    </div>

    <div class="section">
        <div class="section-title">Основание</div>
        <div>{{ basis.type }} № {{ basis.number }} от {{ basis.date|date:"d.m.Y" }}</div>
    </div>

    <table>
        <thead>
            <tr>
                <th>№</th>
                <th>Наименование товара</th>
                <th>Код</th>
                <th>Ед. изм.</th>
                <th>Количество</th>
                <th>Цена</th>
                <th>Сумма</th>
            </tr>
        </thead>
        <tbody>
            {% for line in lines %}
            <tr>
                <td>{{ line.line_number }}</td>
                <td>{{ line.item_name_snapshot }}</td>
                <td>{{ line.sku_snapshot }}</td>
                <td>{{ line.unit_symbol_snapshot }}</td>
                <td>{{ line.qty|floatformat:2 }}</td>
                <td>{{ line.price|floatformat:2 }}</td>
                <td>{{ line.total|floatformat:2 }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <div class="section">
        <div class="section-title">Всего наименований: {{ lines|length }}</div>
        <div class="totals">
            Итого: {{ total_amount|floatformat:2 }} руб.
        </div>
    </div>

    <div class="signatures">
        <div class="signature-block">
            <div>Отправитель:</div>
            <div style="margin-top: 50px;">_________________ / {{ created_by_user.full_name }} /</div>
            <div>должность, подпись, расшифровка</div>
        </div>
        <div class="signature-block">
            <div>Получатель:</div>
            <div style="margin-top: 50px;">_________________ / _________________ /</div>
            <div>должность, подпись, расшифровка</div>
        </div>
    </div>
</body>
</html>
```

### View для клиентского рендеринга

```python
# apps/documents/views.py
from django.template.loader import render_to_string
from django.http import HttpResponse

async def render_document_client(request, document_id):
    """Клиентский рендеринг документа"""
    service = DocumentService(request)
    document_data = await service.get_document(document_id)
    
    # Извлекаем данные из payload
    payload = document_data['payload']
    
    context = {
        'document': payload.get('document', {}),
        'site': payload.get('site', {}),
        'destination_site': payload.get('destination_site', {}),
        'operation': payload.get('operation', {}),
        'created_by_user': payload.get('created_by_user', {}),
        'submitted_by_user': payload.get('submitted_by_user', {}),
        'lines': payload.get('lines', []),
        'basis': payload.get('basis', {}),
        'total_amount': sum(line.get('total', 0) for line in payload.get('lines', [])),
    }
    
    # Рендерим HTML
    html_content = render_to_string('documents/render_waybill.html', context)
    
    return HttpResponse(html_content, content_type='text/html')
```

## 5. Интеграция с Django Admin

### Модель для кэширования документов (опционально)

```python
# apps/documents/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class CachedDocument(models.Model):
    """Локальная копия документа для быстрого доступа"""
    id = models.UUIDField(primary_key=True)  # SyncServer document_id
    document_number = models.CharField(max_length=100)
    document_type = models.CharField(max_length=50)
    status = models.CharField(max_length=20)
    site_id = models.IntegerField()
    created_at = models.DateTimeField()
    finalized_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField()  # Полный payload
    syncserver_updated_at = models.DateTimeField()
    local_cached_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'cached_documents'
        indexes = [
            models.Index(fields=['document_number']),
            models.Index(fields=['site_id', 'created_at']),
            models.Index(fields=['status']),
        ]
    
    @classmethod
    async def sync_from_syncserver(cls, request, document_id):
        """Синхронизировать документ из SyncServer"""
        service = DocumentService(request)
        document_data = await service.get_document(document_id)
        
        # Сохраняем в локальную БД
        await cls.objects.aupdate_or_create(
            id=document_id,
            defaults={
                'document_number': document_data.get('document_number'),
                'document_type': document_data.get('document_type'),
                'status': document_data.get('status'),
                'site_id': document_data.get('site_id