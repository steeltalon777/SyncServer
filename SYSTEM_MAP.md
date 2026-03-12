# SYSTEM_MAP

## System components
Ingress layer

nginx gateway является точкой входа системы.

Задачи nginx:

маршрутизация HTTP

будущий TLS termination

проксирование API

Routing:

/ → Warehouse_web
/api/ → SyncServer

Web client

Warehouse_web — Django SSR клиент.

Функции:

интерфейс кладовщика

управление каталогом

просмотр остатков

создание операций

резервный онлайн клиент


### Clients
- Offline-capable device clients (desktop/mobile/other) calling sync and catalog APIs.

### Backend service
- SyncServer (this repository): FastAPI app with sync + catalog modules.

### Database
- PostgreSQL storing events, catalog, sites/devices, balances.

## Data flow

### Sync flow
`Client → /push|/pull|/ping → FastAPI → services → repositories → PostgreSQL`

### Catalog flow
`Client → /catalog/* or /catalog/admin/* → FastAPI → CatalogAdminService/CatalogRepo → PostgreSQL`

## System role
- This project is a standalone backend service.
- It acts as the authoritative synchronization and catalog API for connected clients.
