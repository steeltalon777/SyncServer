from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.site import Site
from app.models.user import User
from main import create_app

app = create_app(enable_startup_migrations=False)

ADMIN_PREFIX = "/api/v1/admin"


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def seeded_roles_and_site(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict:
    async with session_factory() as session:
        site = Site(code=f"S-{uuid4().hex[:6]}", name="Test Site")
        users = {
            "observer": User(
                username=f"obs-{uuid4().hex[:6]}",
                email="observer@example.com",
                full_name="Observer User",
                is_active=True,
                is_root=False,
                role="observer",
            ),
            "storekeeper": User(
                username=f"stk-{uuid4().hex[:6]}",
                email="storekeeper@example.com",
                full_name="Storekeeper User",
                is_active=True,
                is_root=False,
                role="storekeeper",
            ),
            "chief_storekeeper": User(
                username=f"chief-{uuid4().hex[:6]}",
                email="chief@example.com",
                full_name="Chief Storekeeper",
                is_active=True,
                is_root=False,
                role="chief_storekeeper",
            ),
            "root": User(
                username=f"root-{uuid4().hex[:6]}",
                email="root@example.com",
                full_name="Root User",
                is_active=True,
                is_root=True,
                role="root",
            ),
        }
        session.add_all([site, *users.values()])
        await session.commit()
        await session.refresh(site)
        for user in users.values():
            await session.refresh(user)
        return {"site": site, **users}


# ── Device endpoints (all require root) ─────────────────────────────────

DEVICE_ENDPOINTS = [
    ("GET", f"{ADMIN_PREFIX}/devices", None),
    ("GET", f"{ADMIN_PREFIX}/devices/99999", None),
    ("POST", f"{ADMIN_PREFIX}/devices", {"device_name": "test-device"}),
    ("PATCH", f"{ADMIN_PREFIX}/devices/99999", {}),
    ("DELETE", f"{ADMIN_PREFIX}/devices/99999", None),
    ("POST", f"{ADMIN_PREFIX}/devices/99999/rotate-token", None),
    ("PUT", f"{ADMIN_PREFIX}/devices/by-code/test-ensure", {"device_name": "test-ensure-device"}),
]


@pytest.mark.asyncio
async def test_device_endpoints_require_root(
    client: AsyncClient,
    seeded_roles_and_site: dict,
) -> None:
    for method, path, json_body in DEVICE_ENDPOINTS:
        for role_name in ("observer", "storekeeper", "chief_storekeeper"):
            user = seeded_roles_and_site[role_name]
            response = await client.request(method, path, headers={"X-User-Token": str(user.user_token)}, json=json_body)
            assert response.status_code == 403, (
                f"Expected 403 for {role_name} on {method} {path}, got {response.status_code}"
            )


@pytest.mark.asyncio
async def test_device_endpoints_allow_root(
    client: AsyncClient,
    seeded_roles_and_site: dict,
) -> None:
    root = seeded_roles_and_site["root"]
    for method, path, json_body in DEVICE_ENDPOINTS:
        response = await client.request(method, path, headers={"X-User-Token": str(root.user_token)}, json=json_body)
        assert response.status_code != 403, (
            f"Root got 403 on {method} {path}"
        )


@pytest.mark.asyncio
async def test_device_endpoints_reject_anonymous(
    client: AsyncClient,
) -> None:
    for method, path, json_body in DEVICE_ENDPOINTS:
        response = await client.request(method, path, json=json_body)
        assert response.status_code == 401, (
            f"Expected 401 for anonymous on {method} {path}, got {response.status_code}"
        )


# ── Site list (allows chief_storekeeper) ────────────────────────────────

@pytest.mark.asyncio
async def test_site_list_allows_root_and_chief_storekeeper(
    client: AsyncClient,
    seeded_roles_and_site: dict,
) -> None:
    for role_name in ("root", "chief_storekeeper"):
        user = seeded_roles_and_site[role_name]
        response = await client.get(
            f"{ADMIN_PREFIX}/sites",
            headers={"X-User-Token": str(user.user_token)},
        )
        assert response.status_code == 200, (
            f"Expected 200 for {role_name} on GET /admin/sites, got {response.status_code}"
        )


@pytest.mark.asyncio
async def test_site_list_rejects_lower_roles(
    client: AsyncClient,
    seeded_roles_and_site: dict,
) -> None:
    for role_name in ("observer", "storekeeper"):
        user = seeded_roles_and_site[role_name]
        response = await client.get(
            f"{ADMIN_PREFIX}/sites",
            headers={"X-User-Token": str(user.user_token)},
        )
        assert response.status_code == 403, (
            f"Expected 403 for {role_name} on GET /admin/sites, got {response.status_code}"
        )


# ── Site mutation (requires root) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_site_mutation_requires_root(
    client: AsyncClient,
    seeded_roles_and_site: dict,
) -> None:
    site = seeded_roles_and_site["site"]
    create_payload = {"code": f"S-{uuid4().hex[:6]}", "name": "New Site"}
    update_payload = {"name": "Updated"}

    for role_name in ("observer", "storekeeper", "chief_storekeeper"):
        user = seeded_roles_and_site[role_name]

        post_resp = await client.post(
            f"{ADMIN_PREFIX}/sites",
            headers={"X-User-Token": str(user.user_token)},
            json=create_payload,
        )
        assert post_resp.status_code == 403, (
            f"Expected 403 for {role_name} on POST /admin/sites, got {post_resp.status_code}"
        )

        patch_resp = await client.patch(
            f"{ADMIN_PREFIX}/sites/{site.id}",
            headers={"X-User-Token": str(user.user_token)},
            json=update_payload,
        )
        assert patch_resp.status_code == 403, (
            f"Expected 403 for {role_name} on PATCH /admin/sites, got {patch_resp.status_code}"
        )


@pytest.mark.asyncio
async def test_site_mutation_allows_root(
    client: AsyncClient,
    seeded_roles_and_site: dict,
) -> None:
    root = seeded_roles_and_site["root"]
    create_payload = {"code": f"S-{uuid4().hex[:6]}", "name": "New Root Site"}

    post_resp = await client.post(
        f"{ADMIN_PREFIX}/sites",
        headers={"X-User-Token": str(root.user_token)},
        json=create_payload,
    )
    assert post_resp.status_code == 200, (
        f"Root got {post_resp.status_code} on POST /admin/sites"
    )

    created = post_resp.json()
    site_id = created["site_id"]

    patch_resp = await client.patch(
        f"{ADMIN_PREFIX}/sites/{site_id}",
        headers={"X-User-Token": str(root.user_token)},
        json={"name": "Updated Root Site"},
    )
    assert patch_resp.status_code == 200


# ── User admin endpoints (all require root) ─────────────────────────────

USER_ROOT_ENDPOINTS = [
    ("GET", f"{ADMIN_PREFIX}/users/{{user_id}}"),
    ("POST", f"{ADMIN_PREFIX}/users"),
    ("PATCH", f"{ADMIN_PREFIX}/users/{{user_id}}"),
    ("DELETE", f"{ADMIN_PREFIX}/users/{{user_id}}"),
]


@pytest.mark.parametrize("method,path_template", USER_ROOT_ENDPOINTS)
@pytest.mark.asyncio
async def test_user_admin_endpoints_require_root(
    client: AsyncClient,
    seeded_roles_and_site: dict,
    method: str,
    path_template: str,
) -> None:
    target_user = seeded_roles_and_site["storekeeper"]
    path = path_template.format(user_id=target_user.id)

    bodies = {
        "GET": None,
        "POST": {"username": "newuser", "role": "observer", "is_active": True, "is_root": False},
        "PATCH": {},
        "DELETE": None,
    }

    for role_name in ("observer", "storekeeper", "chief_storekeeper"):
        user = seeded_roles_and_site[role_name]
        response = await client.request(method, path, headers={"X-User-Token": str(user.user_token)}, json=bodies[method])
        assert response.status_code == 403, (
            f"Expected 403 for {role_name} on {method} {path}, got {response.status_code}"
        )
