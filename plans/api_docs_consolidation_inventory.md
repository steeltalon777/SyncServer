# API docs consolidation inventory

## Goal

Подготовить свёртку API-документации в единый файл [`docs/API_map.md`](../docs/API_map.md) и заранее определить, какие текущие файлы можно удалить без потери полезного содержания.

## Источники проверки

- Смонтированные роутеры в [`create_app()`](../main.py:31)
- Список route decorators в [`app/api/routes_*.py`](../app/api)
- Текущие канонические API-доки [`docs/API_REFERENCE.md`](../docs/API_REFERENCE.md) и [`docs/ENDPOINT_INVENTORY.md`](../docs/ENDPOINT_INVENTORY.md)
- Смежные API-ориентированные документы [`API_CONTRACT.md`](../API_CONTRACT.md), [`docs/HEALTH_CHECKS.md`](../docs/HEALTH_CHECKS.md), [`docs/LOST_ASSETS_CLIENT_GUIDE.md`](../docs/LOST_ASSETS_CLIENT_GUIDE.md), [`docs/ACCEPTANCE_SYSTEM_GUIDE.md`](../docs/ACCEPTANCE_SYSTEM_GUIDE.md), [`docs/DOCUMENTS_GUIDE_FOR_DJANGO.md`](../docs/DOCUMENTS_GUIDE_FOR_DJANGO.md), [`docs/DJANGO_INTEGRATION_GUIDE.md`](../docs/DJANGO_INTEGRATION_GUIDE.md)

## Inventory by file

### 1. Canonical API docs today

#### [`docs/ENDPOINT_INVENTORY.md`](../docs/ENDPOINT_INVENTORY.md)
- Тип: компактный endpoint inventory
- Ценность: высокая
- Что содержит: почти полный перечень маршрутов `/api/v1`
- Проблемы: дублирует большую часть структуры из [`docs/API_REFERENCE.md`](../docs/API_REFERENCE.md)
- Вердикт: хороший кандидат на поглощение в единый [`docs/API_map.md`](../docs/API_map.md) и последующее удаление

#### [`docs/API_REFERENCE.md`](../docs/API_REFERENCE.md)
- Тип: расширенная reference-документация
- Ценность: высокая
- Что содержит: auth model, endpoint groups, заметки по поведению, примеры запросов
- Проблемы: пересекается с [`docs/ENDPOINT_INVENTORY.md`](../docs/ENDPOINT_INVENTORY.md), при этом местами уже дрейфует от кода
- Вердикт: основной источник содержания для будущего [`docs/API_map.md`](../docs/API_map.md), после переноса кандидат на удаление

#### [`API_CONTRACT.md`](../API_CONTRACT.md)
- Тип: короткий контракт-указатель
- Ценность: низкая
- Что содержит: по сути только указание, что канон находится в [`docs/API_REFERENCE.md`](../docs/API_REFERENCE.md) и [`docs/ENDPOINT_INVENTORY.md`](../docs/ENDPOINT_INVENTORY.md)
- Проблемы: после свёртки станет лишним
- Вердикт: явный кандидат на удаление

### 2. Узкоспециализированные API-гайды

#### [`docs/HEALTH_CHECKS.md`](../docs/HEALTH_CHECKS.md)
- Тип: специализированный operational guide
- Ценность: средняя
- Что содержит: не только список endpoints, но и operational semantics для liveness/readiness, примеры k8s probes, рекомендации для мониторинга
- Проблемы: endpoints дублируют канонический API map
- Вердикт: **не удалять автоматически**; либо сократить до operational guide без повторного полного списка API, либо оставить как тематический runbook

#### [`docs/LOST_ASSETS_CLIENT_GUIDE.md`](../docs/LOST_ASSETS_CLIENT_GUIDE.md)
- Тип: клиентский integration guide
- Ценность: средняя
- Что содержит: примеры client-side вызовов, UI рекомендации, интеграционные примеры для lost assets
- Проблемы: частично дублирует endpoint описание из общих API-доков
- Вердикт: **не удалять как API map файл**, если нужны клиентские сценарии; можно чистить отдельно после свёртки

#### [`docs/ACCEPTANCE_SYSTEM_GUIDE.md`](../docs/ACCEPTANCE_SYSTEM_GUIDE.md)
- Тип: бизнес-процесс + API guide
- Ценность: высокая
- Что содержит: описание потока приёмки, доменной логики и связанных endpoints
- Проблемы: есть дубли endpoint-списков
- Вердикт: **не удалять**; это не просто API map, а доменный guide

#### [`docs/DOCUMENTS_GUIDE_FOR_DJANGO.md`](../docs/DOCUMENTS_GUIDE_FOR_DJANGO.md)
- Тип: интеграционный guide
- Ценность: средняя
- Что содержит: usage patterns для Django-клиента вокруг documents API
- Проблемы: дублирует endpoints documents API
- Вердикт: **не удалять автоматически**; при желании сократить до integration-only текста без повторения полного API списка

#### [`docs/DJANGO_INTEGRATION_GUIDE.md`](../docs/DJANGO_INTEGRATION_GUIDE.md)
- Тип: общий integration guide
- Ценность: высокая
- Что содержит: архитектурные и клиентские рекомендации, не только API reference
- Проблемы: местами ссылается на старые канонические API docs
- Вердикт: **не удалять**; позже обновить ссылки на [`docs/API_map.md`](../docs/API_map.md)

### 3. Непрямые упоминания API, не кандидаты на удаление сейчас

- [`README.md`](../README.md) — проектный overview и ссылки на каноническую доку
- [`INDEX.md`](../INDEX.md) — индекс документации
- [`docs/IMPLEMENTATION_SUMMARY.md`](../docs/IMPLEMENTATION_SUMMARY.md) — отчёт по одной функции
- [`plans/api_map_refresh_plan.md`](./api_map_refresh_plan.md) — исторический план
- [`plans/lost_assets_api_enhancements_plan.md`](./lost_assets_api_enhancements_plan.md) — план доработок
- [`plans/preprod_full_test_plan.md`](./preprod_full_test_plan.md) — план тестирования

## Recommended deletion set

Если цель — убрать именно дублирующуюся каноническую API-документацию и оставить тематические гайды, то рекомендую удалить после создания [`docs/API_map.md`](../docs/API_map.md) только:

1. [`docs/API_REFERENCE.md`](../docs/API_REFERENCE.md)
2. [`docs/ENDPOINT_INVENTORY.md`](../docs/ENDPOINT_INVENTORY.md)
3. [`API_CONTRACT.md`](../API_CONTRACT.md)

## Recommended keep set

Пока оставить:

1. [`docs/HEALTH_CHECKS.md`](../docs/HEALTH_CHECKS.md)
2. [`docs/LOST_ASSETS_CLIENT_GUIDE.md`](../docs/LOST_ASSETS_CLIENT_GUIDE.md)
3. [`docs/ACCEPTANCE_SYSTEM_GUIDE.md`](../docs/ACCEPTANCE_SYSTEM_GUIDE.md)
4. [`docs/DOCUMENTS_GUIDE_FOR_DJANGO.md`](../docs/DOCUMENTS_GUIDE_FOR_DJANGO.md)
5. [`docs/DJANGO_INTEGRATION_GUIDE.md`](../docs/DJANGO_INTEGRATION_GUIDE.md)

## Why this split

- Первая тройка существует именно как слой канонического API contract/reference и почти полностью может быть схлопнута в один файл.
- Остальные документы описывают не только HTTP surface, но и operational, UI, integration или domain workflow контекст.
- Если удалить тематические гайды сразу, есть риск потерять полезные интеграционные сценарии, которые не должны жить в общем [`docs/API_map.md`](../docs/API_map.md).

## Proposed execution todo

- [ ] Собрать единый канонический файл [`docs/API_map.md`](../docs/API_map.md) на основе [`docs/API_REFERENCE.md`](../docs/API_REFERENCE.md) и [`docs/ENDPOINT_INVENTORY.md`](../docs/ENDPOINT_INVENTORY.md)
- [ ] Перенести из [`API_CONTRACT.md`](../API_CONTRACT.md) краткие contract principles в начало [`docs/API_map.md`](../docs/API_map.md)
- [ ] Обновить ссылки в [`README.md`](../README.md), [`INDEX.md`](../INDEX.md), [`docs/DJANGO_INTEGRATION_GUIDE.md`](../docs/DJANGO_INTEGRATION_GUIDE.md) и других документах на [`docs/API_map.md`](../docs/API_map.md)
- [ ] Удалить [`docs/API_REFERENCE.md`](../docs/API_REFERENCE.md), [`docs/ENDPOINT_INVENTORY.md`](../docs/ENDPOINT_INVENTORY.md) и [`API_CONTRACT.md`](../API_CONTRACT.md)
- [ ] Отдельным проходом решить, сокращать ли специализированные гайды до integration-only формата
