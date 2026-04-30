from __future__ import annotations

import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import and_, func, or_, select
from sqlalchemy.engine import make_url

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

ENV_PATH = ROOT_DIR / ".env"


def _load_env_file(path: Path) -> dict[str, str]:
    """Load simple KEY=VALUE pairs before importing app settings."""
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
        if not os.environ.get(key):
            os.environ[key] = value

    return values


ENV_FILE_VALUES = _load_env_file(ENV_PATH)

from app.core.catalog_defaults import (  # noqa: E402
    DEFAULT_UNIT_CODE,
    DEFAULT_UNIT_NAME,
    DEFAULT_UNIT_SYMBOL,
    UNCATEGORIZED_CATEGORY_CODE,
    UNCATEGORIZED_CATEGORY_NAME,
)
from app.core.db import SessionFactory, engine  # noqa: E402
from app.core.migrations import ensure_database_ready  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.unit import Unit  # noqa: E402
from app.models.user import User  # noqa: E402

ROOT_USERNAME = "root"
ROOT_EMAIL = "root@local"
ROOT_FULL_NAME = "System Root"
DJANGO_DEVICE_CODE = "DJANGO_WEB"
DJANGO_DEVICE_NAME = "Django Web Client"

ROOT_TOKEN_ENV_NAMES = (
    "SYNC_ROOT_USER_TOKEN",
    "SYNC_TEST_ROOT_TOKEN",
    "ROOT_USER_TOKEN",
)
DEVICE_TOKEN_ENV_NAMES = (
    "SYNC_DEVICE_TOKEN",
    "DJANGO_DEVICE_TOKEN",
    "SYNC_BOOTSTRAP_DEVICE_TOKEN",
)
DEFAULT_SITE_CODE_ENV_NAMES = (
    "SYNC_DEFAULT_SITE_CODE",
    "DEFAULT_SITE_CODE",
    "SYNC_BOOTSTRAP_SITE_CODE",
)
DEFAULT_SITE_NAME_ENV_NAMES = (
    "SYNC_DEFAULT_SITE_NAME",
    "DEFAULT_SITE_NAME",
    "SYNC_BOOTSTRAP_SITE_NAME",
)
DEFAULT_SITE_DESCRIPTION_ENV_NAMES = (
    "SYNC_DEFAULT_SITE_DESCRIPTION",
    "DEFAULT_SITE_DESCRIPTION",
    "SYNC_BOOTSTRAP_SITE_DESCRIPTION",
)

DEFAULT_SITE_CODE = "MAIN"
DEFAULT_SITE_NAME = "Main Site"
DEFAULT_SITE_DESCRIPTION = "Bootstrap default site"


@dataclass(frozen=True)
class ConfiguredToken:
    value: uuid.UUID | None
    source: str
    generated: bool = False


def _read_config_value(names: tuple[str, ...], default: str | None = None) -> tuple[str | None, str]:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip(), name

        value = ENV_FILE_VALUES.get(name)
        if value is not None and value.strip():
            return value.strip(), f"{ENV_PATH.name}:{name}"

    return default, "default" if default is not None else "not configured"


def _read_config_text(names: tuple[str, ...], default: str) -> tuple[str, str]:
    value, source = _read_config_value(names, default)
    if value is None:
        return default, "default"
    return value, source


def _read_configured_uuid(names: tuple[str, ...], label: str) -> ConfiguredToken:
    raw_value, source = _read_config_value(names)
    if raw_value is None:
        return ConfiguredToken(value=None, source="generated or existing database token")

    try:
        return ConfiguredToken(value=uuid.UUID(raw_value), source=source)
    except ValueError as exc:
        joined_names = ", ".join(names)
        raise ValueError(f"Invalid {label} UUID in {source}; expected one of: {joined_names}") from exc


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().lower().split())


def _is_postgresql_url(database_url: str) -> bool:
    if not database_url:
        return False

    try:
        drivername = make_url(database_url).drivername
    except Exception:
        lower_url = database_url.lower()
        return lower_url.startswith("postgresql://") or lower_url.startswith("postgresql+")

    return drivername == "postgresql" or drivername.startswith("postgresql+")


async def _ensure_schema() -> None:
    """Prepare schema through Alembic for PostgreSQL before idempotent seed data.

    Bootstrap is not a migration replacement: PostgreSQL schema changes must be
    represented by Alembic revisions. ``Base.metadata.create_all`` is kept only
    as an explicit non-Alembic fallback for lightweight SQLite/test databases.
    """

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured; cannot bootstrap database")

    alembic_ini = ROOT_DIR / "alembic.ini"
    if _is_postgresql_url(database_url):
        if not alembic_ini.exists():
            raise RuntimeError(
                f"PostgreSQL bootstrap requires Alembic configuration at {alembic_ini}; "
                "refusing to create tables with Base.metadata.create_all."
            )

        print("Applying Alembic migrations for PostgreSQL before bootstrap seed data...")
        await ensure_database_ready(database_url)
        return

    print(
        "Using non-Alembic schema fallback for this database URL; "
        "Base.metadata.create_all is intended only for SQLite/test bootstrap."
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _ensure_base_site(session) -> tuple[Site, str, str]:
    site_code, code_source = _read_config_text(DEFAULT_SITE_CODE_ENV_NAMES, DEFAULT_SITE_CODE)
    site_name, _ = _read_config_text(DEFAULT_SITE_NAME_ENV_NAMES, DEFAULT_SITE_NAME)
    site_description, _ = _read_config_text(
        DEFAULT_SITE_DESCRIPTION_ENV_NAMES,
        DEFAULT_SITE_DESCRIPTION,
    )

    result = await session.execute(select(Site).where(Site.code == site_code))
    site = result.scalar_one_or_none()
    if site is not None:
        site.name = site_name
        site.description = site_description
        site.is_active = True
        await session.flush()
        return site, "updated", code_source

    columns_allow_null_site = (
        User.__table__.c.default_site_id.nullable
        and Device.__table__.c.site_id.nullable
    )
    if columns_allow_null_site:
        result = await session.execute(
            select(Site).where(Site.is_active.is_(True)).order_by(Site.id)
        )
        existing_site = result.scalars().first()
        if existing_site is not None:
            return existing_site, "reused existing active site", "database"

    site = Site(
        code=site_code,
        name=site_name,
        description=site_description,
        is_active=True,
    )
    session.add(site)
    await session.flush()
    return site, "created", code_source


async def _ensure_root_user(
    session,
    *,
    desired_token: ConfiguredToken,
    base_site: Site,
) -> tuple[User, str, ConfiguredToken]:
    result = await session.execute(select(User).where(User.username == ROOT_USERNAME))
    root_by_username = result.scalar_one_or_none()

    root_by_token: User | None = None
    if desired_token.value is not None:
        result = await session.execute(select(User).where(User.user_token == desired_token.value))
        root_by_token = result.scalar_one_or_none()

    root_candidates: list[User] = []
    if root_by_username is None and root_by_token is None:
        result = await session.execute(
            select(User).where(or_(User.is_root.is_(True), User.role == "root"))
        )
        root_candidates = list(result.scalars().all())
        if len(root_candidates) > 1:
            details = ", ".join(f"username={user.username!r}, id={user.id}" for user in root_candidates)
            raise RuntimeError(f"multiple root users configured: {details}")

    if root_by_username is not None and root_by_token is not None and root_by_username.id != root_by_token.id:
        raise RuntimeError(
            f"Configured root token from {desired_token.source} already belongs to "
            f"user {root_by_token.username!r} ({root_by_token.id}), not {ROOT_USERNAME!r}."
        )

    root_user = root_by_username or root_by_token or (root_candidates[0] if root_candidates else None)
    action = "updated"
    token_resolution = desired_token

    if root_user is None:
        if desired_token.value is None:
            token_resolution = ConfiguredToken(value=uuid.uuid4(), source="generated", generated=True)
        root_user = User(
            id=uuid.uuid4(),
            username=ROOT_USERNAME,
            email=ROOT_EMAIL,
            full_name=ROOT_FULL_NAME,
            user_token=token_resolution.value,
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=base_site.id,
        )
        session.add(root_user)
        action = "created"
    else:
        root_user.username = ROOT_USERNAME
        root_user.email = ROOT_EMAIL
        root_user.full_name = ROOT_FULL_NAME
        root_user.is_active = True
        root_user.is_root = True
        root_user.role = "root"
        if root_user.default_site_id is None:
            root_user.default_site_id = base_site.id
        if desired_token.value is not None:
            root_user.user_token = desired_token.value
        elif root_user.user_token is None:
            token_resolution = ConfiguredToken(value=uuid.uuid4(), source="generated", generated=True)
            root_user.user_token = token_resolution.value
        else:
            token_resolution = ConfiguredToken(value=root_user.user_token, source="existing database token")

    await session.flush()
    return root_user, action, token_resolution


async def _ensure_django_device(
    session,
    *,
    desired_token: ConfiguredToken,
    base_site: Site,
) -> tuple[Device, str, ConfiguredToken]:
    result = await session.execute(select(Device).where(Device.device_code == DJANGO_DEVICE_CODE))
    device_by_code = result.scalar_one_or_none()

    device_by_token: Device | None = None
    if desired_token.value is not None:
        result = await session.execute(select(Device).where(Device.device_token == desired_token.value))
        device_by_token = result.scalar_one_or_none()

    if device_by_code is not None and device_by_token is not None and device_by_code.id != device_by_token.id:
        raise RuntimeError(
            f"Configured device token from {desired_token.source} already belongs to "
            f"device {device_by_token.device_code!r} ({device_by_token.id}), not {DJANGO_DEVICE_CODE!r}."
        )

    django_device = device_by_code or device_by_token
    action = "updated"
    token_resolution = desired_token

    if django_device is None:
        if desired_token.value is None:
            token_resolution = ConfiguredToken(value=uuid.uuid4(), source="generated", generated=True)
        django_device = Device(
            device_code=DJANGO_DEVICE_CODE,
            device_name=DJANGO_DEVICE_NAME,
            device_token=token_resolution.value,
            site_id=base_site.id,
            is_active=True,
        )
        session.add(django_device)
        action = "created"
    else:
        django_device.device_code = DJANGO_DEVICE_CODE
        django_device.device_name = DJANGO_DEVICE_NAME
        django_device.is_active = True
        if django_device.site_id is None:
            django_device.site_id = base_site.id
        if desired_token.value is not None:
            django_device.device_token = desired_token.value
        elif django_device.device_token is None:
            token_resolution = ConfiguredToken(value=uuid.uuid4(), source="generated", generated=True)
            django_device.device_token = token_resolution.value
        else:
            token_resolution = ConfiguredToken(value=django_device.device_token, source="existing database token")

    await session.flush()
    return django_device, action, token_resolution


async def _ensure_uncategorized_category(session) -> tuple[Category, str]:
    normalized_name = _normalize_text(UNCATEGORIZED_CATEGORY_NAME)
    result = await session.execute(
        select(Category).where(
            or_(
                Category.code == UNCATEGORIZED_CATEGORY_CODE,
                Category.name == UNCATEGORIZED_CATEGORY_NAME,
                Category.normalized_name == normalized_name,
                and_(
                    Category.parent_id.is_(None),
                    func.lower(Category.name) == normalized_name,
                ),
            )
        )
    )
    categories = list(result.scalars().all())

    if len(categories) > 1:
        details = ", ".join(f"id={category.id}" for category in categories)
        raise RuntimeError(f"multiple uncategorized categories configured: {details}")

    if categories:
        category = categories[0]
        action = "updated"
    else:
        category = Category()
        session.add(category)
        action = "created"

    category.name = UNCATEGORIZED_CATEGORY_NAME
    category.normalized_name = normalized_name
    category.code = UNCATEGORIZED_CATEGORY_CODE
    category.parent_id = None
    category.is_active = True
    category.deleted_at = None
    category.deleted_by_user_id = None

    await session.flush()
    return category, action


async def _ensure_default_unit(session) -> tuple[Unit, str]:
    normalized_name = _normalize_text(DEFAULT_UNIT_NAME)
    result = await session.execute(
        select(Unit).where(
            or_(
                Unit.code == DEFAULT_UNIT_CODE,
                Unit.name == DEFAULT_UNIT_NAME,
                func.lower(Unit.name) == normalized_name,
                Unit.symbol == DEFAULT_UNIT_SYMBOL,
            )
        )
    )
    units = list(result.scalars().all())

    if len(units) > 1:
        details = ", ".join(
            f"id={unit.id}, code={unit.code!r}, name={unit.name!r}, symbol={unit.symbol!r}"
            for unit in units
        )
        raise RuntimeError(f"conflicting default unit records configured: {details}")

    if units:
        unit = units[0]
        action = "updated"
    else:
        unit = Unit()
        session.add(unit)
        action = "created"

    unit.code = DEFAULT_UNIT_CODE
    unit.name = DEFAULT_UNIT_NAME
    unit.symbol = DEFAULT_UNIT_SYMBOL
    unit.is_active = True
    unit.deleted_at = None
    unit.deleted_by_user_id = None

    await session.flush()
    return unit, action


async def bootstrap() -> None:
    """Apply schema migrations if needed, then idempotently seed system records."""

    root_token = _read_configured_uuid(ROOT_TOKEN_ENV_NAMES, "root user token")
    device_token = _read_configured_uuid(DEVICE_TOKEN_ENV_NAMES, "Django device token")

    await _ensure_schema()

    async with SessionFactory() as session:
        base_site, site_action, site_source = await _ensure_base_site(session)
        root_user, root_action, root_token = await _ensure_root_user(
            session,
            desired_token=root_token,
            base_site=base_site,
        )
        django_device, device_action, device_token = await _ensure_django_device(
            session,
            desired_token=device_token,
            base_site=base_site,
        )
        uncategorized_category, category_action = await _ensure_uncategorized_category(session)
        default_unit, unit_action = await _ensure_default_unit(session)

        await session.commit()

    print("\n" + "=" * 60)
    print("BOOTSTRAP COMPLETE")
    print("=" * 60)
    print("Schema: Alembic-managed for PostgreSQL; bootstrap only seeds/updates system records.")
    print("This script is not a replacement for migrations.")
    print()
    print("Root user:")
    print(f"  action:   {root_action}")
    print(f"  id:       {root_user.id}")
    print(f"  username: {root_user.username}")
    print(f"  token:    {root_user.user_token}")
    print(f"  source:   {root_token.source}")
    print()
    print("Django device:")
    print(f"  action:   {device_action}")
    print(f"  id:       {django_device.id}")
    print(f"  code:     {django_device.device_code}")
    print(f"  site_id:  {django_device.site_id}")
    print(f"  token:    {django_device.device_token}")
    print(f"  source:   {device_token.source}")
    print()
    print("Base site:")
    print(f"  action:   {site_action}")
    print(f"  id:       {base_site.id}")
    print(f"  code:     {base_site.code}")
    print(f"  name:     {base_site.name}")
    print(f"  source:   {site_source}")
    print()
    print("System category:")
    print(f"  action:   {category_action}")
    print(f"  id:       {uncategorized_category.id}")
    print(f"  code:     {uncategorized_category.code}")
    print(f"  name:     {uncategorized_category.name}")
    print()
    print("Default unit:")
    print(f"  action:   {unit_action}")
    print(f"  id:       {default_unit.id}")
    print(f"  code:     {default_unit.code}")
    print(f"  name:     {default_unit.name}")
    print(f"  symbol:   {default_unit.symbol}")
    if root_token.generated or device_token.generated:
        print()
        print("Generated tokens were written only to the database.")
        print("Copy them to client environment variables if external clients need stable credentials.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(bootstrap())
