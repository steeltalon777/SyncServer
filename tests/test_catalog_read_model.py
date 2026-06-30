from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.category import Category
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from main import create_app

app = create_app(enable_startup_migrations=False)


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


async def _seed_catalog_read_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"S-{uuid4().hex[:6]}", name="Catalog Site")
        session.add(site)
        await session.flush()

        user = User(
            username=f"observer-{uuid4().hex[:6]}",
            email=f"observer-{uuid4().hex[:6]}@example.com",
            full_name="Catalog Observer",
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=site.id,
        )
        session.add(user)
        await session.flush()

        scope = UserAccessScope(
            user_id=user.id,
            site_id=site.id,
            can_view=True,
            can_operate=False,
            can_manage_catalog=False,
            is_active=True,
        )
        session.add(scope)

        unit_liter = Unit(name=f"Liter-{suffix}", symbol=f"l{suffix[:3]}", is_active=True)
        unit_piece = Unit(name=f"Piece-{suffix}", symbol=f"p{suffix[:3]}", is_active=True)
        session.add_all([unit_liter, unit_piece])
        await session.flush()

        root_name = f"Food {suffix}"
        milk_name = f"Milk {suffix}"
        cheese_name = f"Cheese {suffix}"
        whole_milk_name = f"Whole Milk {suffix}"
        whole_milk_item_name = f"Whole Milk 1L {suffix}"
        farm_milk_item_name = f"Farm Milk 2L {suffix}"
        milk_search_term = f"MILK-{suffix}"

        root = Category(name=root_name, code=f"FOOD-{suffix}", sort_order=1, is_active=True)
        session.add(root)
        await session.flush()

        milk = Category(name=milk_name, code=f"MILK-{suffix}", parent_id=root.id, sort_order=1, is_active=True)
        cheese = Category(name=cheese_name, code=f"CHEESE-{suffix}", parent_id=root.id, sort_order=2, is_active=True)
        archived = Category(name=f"Archived {suffix}", code=f"ARCH-{suffix}", parent_id=root.id, sort_order=3, is_active=False)
        session.add_all([milk, cheese, archived])
        await session.flush()

        whole_milk = Category(
            name=whole_milk_name,
            code=f"MILK-WHOLE-{suffix}",
            parent_id=milk.id,
            sort_order=1,
            is_active=True,
        )
        session.add(whole_milk)
        await session.flush()

        items = [
            Item(
                sku=f"{milk_search_term}-001",
                name=whole_milk_item_name,
                category_id=whole_milk.id,
                unit_id=unit_liter.id,
                description="Shelf item",
                is_active=True,
            ),
            Item(
                sku=f"{milk_search_term}-002",
                name=farm_milk_item_name,
                category_id=milk.id,
                unit_id=unit_liter.id,
                description="Fresh delivery",
                is_active=True,
            ),
            Item(
                sku=f"CHEESE-001-{suffix}",
                name=f"Cheese Wheel {suffix}",
                category_id=cheese.id,
                unit_id=unit_piece.id,
                description="Aged cheese",
                is_active=True,
            ),
            Item(
                sku=f"{milk_search_term}-999",
                name=f"Old Milk {suffix}",
                category_id=milk.id,
                unit_id=unit_liter.id,
                description="Inactive item",
                is_active=False,
            ),
        ]
        session.add_all(items)
        await session.commit()

        # Capture the first active item id for read-by-id tests
        active_item_id = items[0].id

        return {
            "token": str(user.user_token),
            "root_id": root.id,
            "milk_id": milk.id,
            "whole_milk_id": whole_milk.id,
            "active_item_id": active_item_id,
            "root_name": root_name,
            "milk_name": milk_name,
            "cheese_name": cheese_name,
            "whole_milk_name": whole_milk_name,
            "whole_milk_item_name": whole_milk_item_name,
            "farm_milk_item_name": farm_milk_item_name,
            "milk_search_term": milk_search_term,
            "unit_liter_id": unit_liter.id,
            "unit_liter_symbol": unit_liter.symbol,
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_catalog_read_categories_returns_row_ready_data(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_catalog_read_fixture(session_factory)

    response = await client.get(
        "/api/v1/catalog/read/categories",
        headers={"X-User-Token": seed["token"]},
        params={"search": "Whole", "page": 1, "page_size": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 10

    category = body["categories"][0]
    assert category["name"] == seed["whole_milk_name"]
    assert category["parent"]["name"] == seed["milk_name"]
    assert [node["name"] for node in category["parent_chain_summary"]] == [seed["root_name"], seed["milk_name"]]
    assert category["items_count"] == 1
    assert category["children_count"] == 0
    assert [item["name"] for item in category["items_preview"]] == [seed["whole_milk_item_name"]]

    parent_only_response = await client.get(
        "/api/v1/catalog/read/categories",
        headers={"X-User-Token": seed["token"]},
        params={
            "parent_id": seed["root_id"],
            "include": "parent",
            "page": 1,
            "page_size": 10,
        },
    )

    assert parent_only_response.status_code == 200
    parent_only_body = parent_only_response.json()
    assert parent_only_body["total_count"] == 2
    names = [row["name"] for row in parent_only_body["categories"]]
    assert names == [seed["milk_name"], seed["cheese_name"]]
    assert all(row["parent"]["name"] == seed["root_name"] for row in parent_only_body["categories"])
    assert all(row["parent_chain_summary"] == [] for row in parent_only_body["categories"])
    assert all(row["items_preview"] == [] for row in parent_only_body["categories"])


@pytest.mark.asyncio(loop_scope="session")
async def test_catalog_read_items_children_and_parent_chain(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_catalog_read_fixture(session_factory)

    items_response = await client.get(
        "/api/v1/catalog/read/items",
        headers={"X-User-Token": seed["token"]},
        params={"search": seed["milk_search_term"], "page": 1, "page_size": 10},
    )

    assert items_response.status_code == 200
    items_body = items_response.json()
    assert items_body["total_count"] == 2
    assert [item["name"] for item in items_body["items"]] == [seed["farm_milk_item_name"], seed["whole_milk_item_name"]]
    assert all(item["unit_symbol"] == seed["unit_liter_symbol"] for item in items_body["items"])

    children_response = await client.get(
        f"/api/v1/catalog/read/categories/{seed['milk_id']}/children",
        headers={"X-User-Token": seed["token"]},
        params={"page": 1, "page_size": 10, "items_preview_limit": 1},
    )

    assert children_response.status_code == 200
    children_body = children_response.json()
    assert children_body["total_count"] == 1
    assert children_body["categories"][0]["name"] == seed["whole_milk_name"]
    assert [item["name"] for item in children_body["categories"][0]["items_preview"]] == [seed["whole_milk_item_name"]]

    category_items_response = await client.get(
        f"/api/v1/catalog/read/categories/{seed['whole_milk_id']}/items",
        headers={"X-User-Token": seed["token"]},
        params={"page": 1, "page_size": 10},
    )

    assert category_items_response.status_code == 200
    category_items_body = category_items_response.json()
    assert category_items_body["total_count"] == 1
    assert category_items_body["items"][0]["name"] == seed["whole_milk_item_name"]
    assert category_items_body["items"][0]["category_name"] == seed["whole_milk_name"]

    parent_chain_response = await client.get(
        f"/api/v1/catalog/read/categories/{seed['whole_milk_id']}/parent-chain",
        headers={"X-User-Token": seed["token"]},
    )

    assert parent_chain_response.status_code == 200
    parent_chain_body = parent_chain_response.json()
    assert parent_chain_body["category_id"] == seed["whole_milk_id"]
    assert [node["name"] for node in parent_chain_body["parent_chain_summary"]] == [seed["root_name"], seed["milk_name"]]


@pytest.mark.asyncio(loop_scope="session")
async def test_catalog_read_items_accepts_page_size_1000(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /catalog/read/items?page_size=1000 should return 200, not 422 validation error."""
    seed = await _seed_catalog_read_fixture(session_factory)

    response = await client.get(
        "/api/v1/catalog/read/items",
        headers={"X-User-Token": seed["token"]},
        params={"page": 1, "page_size": 1000},
    )

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total_count" in body
    assert body["page"] == 1
    assert body["page_size"] == 1000


@pytest.mark.asyncio(loop_scope="session")
async def test_catalog_read_items_returns_hashtags(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /catalog/read/items returns hashtags field for items that have them."""
    seed = await _seed_catalog_read_fixture(session_factory)
    suffix = seed["milk_search_term"].split("-")[-1]
    tagged_name = f"Tagged Item {suffix}"

    async with session_factory() as session:
        item = Item(
            sku=f"HASHTAG-{suffix}",
            name=tagged_name,
            category_id=seed["whole_milk_id"],
            unit_id=seed["unit_liter_id"],
            description="Item with hashtags",
            is_active=True,
            hashtags=["electronics", "premium", "sale"],
        )
        session.add(item)
        await session.commit()

    response = await client.get(
        "/api/v1/catalog/read/items",
        headers={"X-User-Token": seed["token"]},
        params={"search": tagged_name, "page": 1, "page_size": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] >= 1

    tagged_item = next(
        (item for item in body["items"] if item["name"] == tagged_name),
        None,
    )
    assert tagged_item is not None, "Tagged item should be found"
    assert "hashtags" in tagged_item, "hashtags field should be present in response"
    assert tagged_item["hashtags"] == ["electronics", "premium", "sale"]


# ── Categories tree with active_only ────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_categories_tree_active_only_default_excludes_inactive(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Default active_only=true → inactive categories are excluded from tree."""
    seed = await _seed_catalog_read_fixture(session_factory)

    response = await client.get(
        "/api/v1/catalog/categories/tree",
        headers={"X-User-Token": seed["token"]},
    )

    assert response.status_code == 200
    tree = response.json()

    # Flatten all category ids in tree
    def collect_ids(nodes):
        ids = set()
        for n in nodes:
            ids.add(n["id"])
            ids.update(collect_ids(n.get("children", [])))
        return ids

    visible_ids = collect_ids(tree)

    # Root + milk + cheese + whole_milk = 4 active categories
    assert seed["root_id"] in visible_ids
    assert seed["milk_id"] in visible_ids
    assert seed["whole_milk_id"] in visible_ids

    # Inactive "archived" category should NOT be in the tree
    async with session_factory() as session:
        from sqlalchemy import select
        archived = (await session.execute(
            select(Category).where(Category.name.like(f"Archived %"))
        )).scalar_one()
        assert archived.id not in visible_ids, f"Inactive category {archived.id} should be excluded"


@pytest.mark.asyncio(loop_scope="session")
async def test_categories_tree_active_only_false_returns_inactive(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """active_only=false → inactive categories are included in tree."""
    seed = await _seed_catalog_read_fixture(session_factory)

    response = await client.get(
        "/api/v1/catalog/categories/tree",
        headers={"X-User-Token": seed["token"]},
        params={"active_only": False},
    )

    assert response.status_code == 200
    tree = response.json()

    def collect_ids(nodes):
        ids = set()
        for n in nodes:
            ids.add(n["id"])
            ids.update(collect_ids(n.get("children", [])))
        return ids

    visible_ids = collect_ids(tree)

    async with session_factory() as session:
        from sqlalchemy import select
        archived = (await session.execute(
            select(Category).where(Category.name.like(f"Archived %"))
        )).scalar_one()
        assert archived.id in visible_ids, f"Inactive category {archived.id} should be included with active_only=false"


@pytest.mark.asyncio(loop_scope="session")
async def test_categories_tree_structure_not_broken_by_filter(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """After active_only filter, the tree structure remains correct:
    whole_milk is still a child of milk, milk is still a child of root."""
    seed = await _seed_catalog_read_fixture(session_factory)

    response = await client.get(
        "/api/v1/catalog/categories/tree",
        headers={"X-User-Token": seed["token"]},
    )

    assert response.status_code == 200
    tree = response.json()
    assert len(tree) >= 1  # Root categories

    root = next((n for n in tree if n["id"] == seed["root_id"]), None)
    assert root is not None, "Root category should be in tree"
    assert len(root.get("children", [])) >= 2  # milk + cheese

    milk = next((c for c in root["children"] if c["id"] == seed["milk_id"]), None)
    assert milk is not None, "Milk category should be child of root"
    assert len(milk.get("children", [])) >= 1  # whole_milk

    whole = next((c for c in milk["children"] if c["id"] == seed["whole_milk_id"]), None)
    assert whole is not None, "Whole milk should be child of milk"


@pytest.mark.asyncio(loop_scope="session")
async def test_categories_tree_inactive_parent_with_active_child(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Active child of inactive parent becomes a root node (no silent hiding)."""
    seed = await _seed_catalog_read_fixture(session_factory)

    async with session_factory() as session:
        # Create: inactive_parent → active_child
        inactive_parent = Category(
            name=f"Inactive Parent {uuid4().hex[:6]}",
            code=f"IP-{uuid4().hex[:6]}",
            is_active=False,
        )
        session.add(inactive_parent)
        await session.flush()

        active_child = Category(
            name=f"Active Child {uuid4().hex[:6]}",
            code=f"AC-{uuid4().hex[:6]}",
            parent_id=inactive_parent.id,
            is_active=True,
        )
        session.add(active_child)
        await session.commit()

        child_id = active_child.id

    response = await client.get(
        "/api/v1/catalog/categories/tree",
        headers={"X-User-Token": seed["token"]},
    )

    assert response.status_code == 200
    tree = response.json()

    def collect_root_ids(nodes):
        return {n["id"] for n in nodes}

    root_ids = collect_root_ids(tree)
    assert child_id in root_ids, (
        "Active child of inactive parent must appear as root node, not be hidden"
    )

    # The inactive parent itself should NOT be in tree
    def collect_all_ids(nodes):
        ids = set()
        for n in nodes:
            ids.add(n["id"])
            ids.update(collect_all_ids(n.get("children", [])))
        return ids

    all_ids = collect_all_ids(tree)
    assert inactive_parent.id not in all_ids, "Inactive parent should not be visible"


@pytest.mark.asyncio(loop_scope="session")
async def test_categories_tree_active_only_explicit_true(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Explicit active_only=true behaves identically to default."""
    seed = await _seed_catalog_read_fixture(session_factory)

    default_resp = await client.get(
        "/api/v1/catalog/categories/tree",
        headers={"X-User-Token": seed["token"]},
    )
    explicit_resp = await client.get(
        "/api/v1/catalog/categories/tree",
        headers={"X-User-Token": seed["token"]},
        params={"active_only": True},
    )

    assert default_resp.status_code == 200
    assert explicit_resp.status_code == 200
    assert default_resp.json() == explicit_resp.json(), (
        "Default and explicit active_only=true must return identical trees"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_categories_tree_all_inactive_returns_empty(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """When all categories are inactive, tree is empty (doesn't crash)."""
    seed = await _seed_catalog_read_fixture(session_factory)

    # Set ALL categories to inactive
    async with session_factory() as session:
        from sqlalchemy import update
        await session.execute(update(Category).values(is_active=False))
        await session.commit()

    response = await client.get(
        "/api/v1/catalog/categories/tree",
        headers={"X-User-Token": seed["token"]},
    )

    assert response.status_code == 200
    tree = response.json()
    assert tree == [], "Empty tree expected when all categories are inactive"


@pytest.mark.asyncio(loop_scope="session")
async def test_categories_tree_inactive_category_is_hidden(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An inactive category is excluded from tree but does not affect siblings."""
    seed = await _seed_catalog_read_fixture(session_factory)

    response = await client.get(
        "/api/v1/catalog/categories/tree",
        headers={"X-User-Token": seed["token"]},
    )

    assert response.status_code == 200

    def find_by_id(nodes, target_id):
        for n in nodes:
            if n["id"] == target_id:
                return n
            found = find_by_id(n.get("children", []), target_id)
            if found:
                return found
        return None

    # Archived is inactive — must be absent from tree
    async with session_factory() as session:
        from sqlalchemy import select
        archived = (await session.execute(
            select(Category).where(Category.name.like(f"Archived %"))
        )).scalar_one()

    archived_node = find_by_id(response.json(), archived.id)
    assert archived_node is None, "Inactive archived category must be absent from tree"

    # Milk is active — must have exactly one child (whole_milk, not archived)
    milk_node = find_by_id(response.json(), seed["milk_id"])
    assert milk_node is not None
    assert len(milk_node["children"]) == 1, "Milk should have only whole_milk child"
    assert milk_node["children"][0]["id"] == seed["whole_milk_id"]


# ── Item-by-id read endpoint ───────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_read_item_by_id_active_returns_200(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /catalog/read/items/{id} returns 200 for an active item."""
    seed = await _seed_catalog_read_fixture(session_factory)

    response = await client.get(
        f"/api/v1/catalog/read/items/{seed['active_item_id']}",
        headers={"X-User-Token": seed["token"]},
    )

    assert response.status_code == 200
    body = response.json()
    # Must have the same shape as a browse item DTO
    assert body["id"] == seed["active_item_id"]
    assert "name" in body
    assert "sku" in body
    assert "category_id" in body
    assert "category_name" in body
    assert "unit_id" in body
    assert "unit_symbol" in body
    assert "description" in body
    assert "is_active" in body
    assert "hashtags" in body
    assert "updated_at" in body
    assert body["is_active"] is True


@pytest.mark.asyncio(loop_scope="session")
async def test_read_item_by_id_missing_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /catalog/read/items/{id} returns 404 for a non-existent id."""
    seed = await _seed_catalog_read_fixture(session_factory)

    response = await client.get(
        "/api/v1/catalog/read/items/999999",
        headers={"X-User-Token": seed["token"]},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_read_item_by_id_inactive_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /catalog/read/items/{id} returns 404 for an inactive item."""
    seed = await _seed_catalog_read_fixture(session_factory)

    # The seed already creates an inactive item — find it
    async with session_factory() as session:
        from sqlalchemy import select
        inactive = (await session.execute(
            select(Item).where(Item.is_active.is_(False))
        )).scalar_one()

    response = await client.get(
        f"/api/v1/catalog/read/items/{inactive.id}",
        headers={"X-User-Token": seed["token"]},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_read_item_by_id_inactive_category_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /catalog/read/items/{id} returns 404 when the item's category is inactive."""
    seed = await _seed_catalog_read_fixture(session_factory)

    # Find the active item created by the seed, deactivate its category
    async with session_factory() as session:
        from sqlalchemy import update
        await session.execute(
            update(Category)
            .where(Category.id == seed["whole_milk_id"])
            .values(is_active=False)
        )
        await session.commit()

    # Now the Whole Milk item has an inactive category — should be 404
    response = await client.get(
        f"/api/v1/catalog/read/items/{seed['active_item_id']}",
        headers={"X-User-Token": seed["token"]},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_read_item_by_id_inactive_unit_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /catalog/read/items/{id} returns 404 when the item's unit is inactive."""
    seed = await _seed_catalog_read_fixture(session_factory)

    # Deactivate the unit
    async with session_factory() as session:
        from sqlalchemy import update
        await session.execute(
            update(Unit)
            .where(Unit.id == seed["unit_liter_id"])
            .values(is_active=False)
        )
        await session.commit()

    # Now the item has an inactive unit — should be 404
    response = await client.get(
        f"/api/v1/catalog/read/items/{seed['active_item_id']}",
        headers={"X-User-Token": seed["token"]},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
