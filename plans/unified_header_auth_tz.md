# ТЗ: унификация авторизации по заголовкам `X-User-Token` и `X-Device-Token`

## Цель

В системе должен остаться один способ аутентификации для всех HTTP API:

- `X-User-Token` — идентификация пользователя
- `X-Device-Token` — идентификация устройства

Аутентификация не должна зависеть от `device_id`, `site_id` или любых других значений из body/query/path. Эти поля могут использоваться только как бизнес-контекст запроса.

## Почему нужна переделка

Сейчас авторизация фрагментирована:

- часть API использует `IdentityService` через зависимости из `app/api/deps.py`
- sync-роуты `/ping`, `/push`, `/pull` используют отдельный `require_device_auth`
- `routes_admin.py`, `routes_auth.py`, `routes_catalog_admin.py`, `routes_recipients.py` содержат ручную проверку токенов внутри файлов
- в коде до сих пор присутствует `X-Device-Id` как часть auth-контракта, хотя источник истины должен быть только токен устройства

Из-за этого разные endpoint'ы проверяют заголовки по-разному.

## Целевое поведение

### Общие правила

- Источник истины для аутентификации — только заголовки `X-User-Token` и `X-Device-Token`
- `device_id` из body, `site_id` из body, `X-Device-Id` и другие поля не участвуют в аутентификации
- если передан `X-User-Token`, сервер валидирует пользователя по `users.user_token`
- если передан `X-Device-Token`, сервер валидирует устройство по `devices.device_token`
- если переданы оба токена, сервер валидирует оба и возвращает комбинированный identity-контекст
- если не передан ни один токен, сервер возвращает `401`
- невалидный токен даёт `401`
- неактивный пользователь или устройство даёт `403`
- нехватка прав даёт `403`

### Модель identity

Нужна единая модель identity для всех роутов:

- `user: User | None`
- `device: Device | None`
- `principal_kind: "user" | "device" | "user_device"`
- `is_root: bool`
- `role: str | None`
- `default_site_id: int | None`
- `scopes: list[...]`

Требование:

- убрать создание синтетического `User` для device-only auth
- user-only маршруты должны работать только с реальным `identity.user`
- device-only маршруты должны работать только с `identity.device`

## Единый auth-слой

### 1. `IdentityService`

Нужно привести `app/services/identity_service.py` к единому контракту:

- `resolve_identity(user_token, device_token, client_ip, client_version) -> Identity`
- валидация user token и device token должна происходить только здесь
- обновление `devices.last_seen_at` должно происходить здесь же при успешной валидации `X-Device-Token`
- любые ручные поиски пользователя/устройства по токенам вне этого сервиса должны быть удалены

### 2. Зависимости FastAPI

В `app/api/deps.py` должны остаться только зависимости-обёртки над единым сервисом:

- `require_identity` — нужен хотя бы один токен
- `require_user_identity` — обязателен валидный `X-User-Token`, `X-Device-Token` опционален
- `require_device_identity` — обязателен валидный `X-Device-Token`, `X-User-Token` опционален

Дополнительно:

- `require_device_auth` удалить
- `require_user_token_auth`, `require_device_token_auth`, `require_token_auth` либо заменить новыми именами, либо привести к вышеописанному контракту без дублирования логики
- `get_client_ip()` и передача `X-Client-Version` должны использоваться только внутри общего auth-пайплайна

## Правила по endpoint'ам

### Device-only

Эти endpoint'ы должны авторизоваться только через `require_device_identity`:

- `POST /api/v1/ping`
- `POST /api/v1/push`
- `POST /api/v1/pull`

Правила:

- `device_id` в body не используется для аутентификации
- `site_id` в body не используется для аутентификации
- `device_id` в body остаётся только как payload-поле на период совместимости, но сервер не должен доверять ему как auth-источнику

### User-required

Эти endpoint'ы должны авторизоваться через `require_user_identity`:

- весь `routes_admin.py`
- весь `routes_catalog_admin.py`
- весь `routes_catalog.py`
- весь `routes_operations.py`
- весь `routes_balances.py`
- весь `routes_assets.py`
- весь `routes_reports.py`
- весь `routes_recipients.py`

Правила:

- `X-User-Token` обязателен
- `X-Device-Token` может передаваться дополнительно для аудита и контекста, но не заменяет user auth

### User-required с optional device context

Эти endpoint'ы тоже должны использовать единый auth-слой, но возвращать и user, и device контекст при наличии обоих токенов:

- `POST /api/v1/auth/sync-user`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/sites`
- `GET /api/v1/auth/context`
- `POST /api/v1/bootstrap/sync`

Правила:

- `X-User-Token` обязателен
- `X-Device-Token` опционален
- `X-Device-Id` больше не участвует в аутентификации

## Что надо удалить из публичного контракта

- зависимость аутентификации от `device_id` в body
- зависимость аутентификации от `site_id` в body
- заголовок `X-Device-Id` как auth-параметр
- ручные `_resolve_current_user*` и `_resolve_current_device*` в роутерах
- прямые вызовы `uow.users.get_by_user_token(...)` и `uow.devices.get_by_device_token(...)` из endpoint'ов, если это делается именно для auth

## Ошибки и формат ответов

Нужно унифицировать HTTP-статусы:

- `401 Unauthorized`
- отсутствуют все auth-заголовки
- невалидный `X-User-Token`
- невалидный `X-Device-Token`

- `403 Forbidden`
- пользователь неактивен
- устройство неактивно
- у identity нет прав на действие или ресурс

Сообщения ошибок должны быть единообразны и использоваться одинаково во всех маршрутах.

## Логирование и аудит

После унификации каждый аутентифицированный запрос должен иметь единый набор audit-полей:

- `request_id`
- `user_id`, если есть user identity
- `device_id`, если есть device identity
- `principal_kind`
- `client_ip`
- `client_version`

## Обратная совместимость

Переход выполнять в два этапа:

### Этап 1

- внедрить единый auth-слой
- перевести все маршруты на новые зависимости
- оставить `device_id` в body и `X-Device-Id` в сигнатурах только как игнорируемые deprecated-поля
- обновить документацию и тесты

### Этап 2

- удалить `X-Device-Id` из сигнатур и OpenAPI
- удалить legacy helper-функции
- удалить код, который сверяет auth с `device_id` из body

## Объём работ по коду

### Основные файлы

- `app/core/identity.py`
- `app/services/identity_service.py`
- `app/api/deps.py`
- `app/api/routes_sync.py`
- `app/api/routes_auth.py`
- `app/api/routes_admin.py`
- `app/api/routes_catalog_admin.py`
- `app/api/routes_recipients.py`

### Маршруты, которые нужно только перевести на новые зависимости

- `app/api/routes_catalog.py`
- `app/api/routes_operations.py`
- `app/api/routes_balances.py`
- `app/api/routes_assets.py`
- `app/api/routes_reports.py`

## Тестирование

Нужно покрыть тестами минимум следующие сценарии:

- user-only endpoint с валидным `X-User-Token`
- user-only endpoint без `X-User-Token`
- user-only endpoint с неактивным пользователем
- device-only endpoint с валидным `X-Device-Token`
- device-only endpoint с `device_id=0` в body
- device-only endpoint с невалидным `X-Device-Token`
- endpoint с обоими токенами и успешной сборкой полного identity
- endpoint с валидным user token и невалидным device token
- endpoint с валидным device token и невалидным user token
- root-only endpoint с обычным пользователем
- chief_storekeeper endpoint без нужных scope

## Критерии приёмки

- во всех защищённых endpoint'ах используется один auth-сервис
- ни один endpoint не использует `device_id` или `site_id` из body для аутентификации
- `X-Device-Id` больше не влияет на авторизацию
- в роутерах отсутствует ручная проверка токенов
- все auth-ошибки возвращаются единообразно
- все существующие и новые auth-тесты проходят
- Django-клиент и sync-клиент работают по одному и тому же header-based контракту

## Вне рамок этого ТЗ

- смена схемы хранения токенов
- привязка устройства к конкретному пользователю
- переход на JWT или внешнюю IAM-систему
- изменение бизнес-ролей и матрицы прав
