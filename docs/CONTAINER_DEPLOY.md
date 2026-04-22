# Container deployment and migrations

## Why migrations are now separated from web startup

The web process no longer runs Alembic during application startup.

This separation is intentional:

- Alembic initializes logging through [`fileConfig()`](../alembic/env.py:19) inside the same process.
- When that happens during FastAPI / Uvicorn startup, it can override the normal Uvicorn logging setup.
- Running migrations in a separate container step keeps the web process focused on serving HTTP traffic and preserves normal access logs.

## Recommended order for container deployment

1. Prepare environment variables.
2. Build the application image.
3. Start or ensure availability of PostgreSQL.
4. Run Alembic migrations in a separate one-shot container.
5. Start the web container.

This order is the recommended flow both for first deployment and for updates.

## Required files

- [`Dockerfile`](../Dockerfile)
- [`docker-compose.yml`](../docker-compose.yml)
- [`.env.example`](../.env.example)

Create your runtime env file from [`.env.example`](../.env.example) and set at least `DATABASE_URL` for the target PostgreSQL instance.

## Build the image

```bash
docker compose build
```

This builds the image used by both the web service and the one-shot migration container.

## Start database / ensure database availability

The current [`docker-compose.yml`](../docker-compose.yml) expects the application to connect to PostgreSQL using the value from `DATABASE_URL`.

If your PostgreSQL instance is external, make sure it is reachable from the Docker network before continuing.

If PostgreSQL is managed in another Compose stack or on another host, the important requirement is simple: the database must already be available before the migration step.

## Run Alembic migrations separately

Recommended command:

```bash
docker compose run --rm migrate
```

What it does:

- starts a temporary container from the same image;
- loads variables from [`.env`](../.env);
- executes `python -m alembic upgrade head`;
- removes the container after completion.

This is the key operational change: migrations are no longer part of web startup.

## Start the web service

After successful migrations, start the API container:

```bash
docker compose up -d syncserver
```

To rebuild and redeploy after code changes:

```bash
docker compose build
docker compose run --rm migrate
docker compose up -d syncserver
```

## Recommended docker compose workflow

For normal deployment:

```bash
docker compose build
docker compose run --rm migrate
docker compose up -d syncserver
```

For service restart without schema changes:

```bash
docker compose up -d syncserver
```

For schema-changing release:

```bash
docker compose build
docker compose run --rm migrate
docker compose up -d syncserver
```

## Manual Alembic commands inside the image

If needed, you can also run Alembic commands directly in a one-shot container.

Upgrade to head:

```bash
docker compose run --rm migrate
```

Stamp an existing database that already matches the latest schema:

```bash
docker compose run --rm --entrypoint python migrate -m alembic stamp head
```

## Result for logging

Because the web container now starts only [`main:app`](../main.py) and does not invoke [`ensure_database_ready()`](../app/core/migrations.py:76) during startup, Alembic logging initialization no longer runs inside the Uvicorn process.

That restores the normal Uvicorn HTTP/access logging behavior while keeping Alembic available as a separate operational step.
