# SyncServer

SyncServer is the backend domain system and single source of truth for the distributed warehouse management platform.

## Overview
- Provides REST APIs for Django web, mobile warehouse, and offline device clients.
- Centralizes domain logic for users, sites, catalog, operations, and balances.
- Computes inventory state from operations, not from client-side calculations.

## Architecture (high level)
Clients -> FastAPI API layer -> Service layer -> Repository layer -> PostgreSQL

See `ARCHITECTURE.md` for the detailed model.

## Tech stack
- Python
- FastAPI
- SQLAlchemy Async
- PostgreSQL
- Pydantic

## Setup
1. Copy env template: `cp .env.example .env`
2. Start dependencies/app: `docker compose up --build`
3. Run tests: `pytest`

## Running the server
- Local: `uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- Docker: `docker compose up`

## API overview
Base path: `/api/v1`

- Admin API
  - `/admin/users`
  - `/admin/sites`
  - `/admin/access`
- Catalog admin API
  - `/catalog/admin/units`
  - `/catalog/admin/categories`
  - `/catalog/admin/items`
- Operations API
  - `POST /operations`
  - `GET /operations`
  - `GET /operations/{id}`
  - `POST /operations/{id}/submit`
  - `POST /operations/{id}/cancel`
- Balances API
  - `GET /balances`
  - `GET /balances?site_id=...`
  - `GET /balances/{item_id}`
