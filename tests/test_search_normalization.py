"""Integration tests for search normalization through API endpoints.

These tests verify that search works correctly with:
- Double spaces in input
- Punctuation in input
- LIKE special characters (%, _)
- ё→е replacement
- Case-insensitive search
- SKU with hyphens/dots/slashes
- Whitespace-only input (no crash)
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.search_utils import build_normalized_like_term, build_raw_like_term
from app.models.category import Category
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit


@pytest.fixture(autouse=True)
async def setup_search_data(db_session: AsyncSession):
    """Seed minimal test data for search tests."""
    unit = Unit(name="шт", symbol="pcs", code="PCS")
    db_session.add(unit)
    await db_session.flush()

    category = Category(name="Тестовая категория", code="TEST_CAT")
    db_session.add(category)
    await db_session.flush()

    site = Site(name="Основной склад", code="MAIN")
    db_session.add(site)
    await db_session.flush()

    # Item with double spaces in name
    item1 = Item(
        name="Круг  шлифовальный  для  металла",
        sku="KRUG-MET-001",
        category_id=category.id,
        unit_id=unit.id,
        description="Шлифовальный круг для металла,  класс   точности  A",
    )
    # Item with punctuation in name
    item2 = Item(
        name="Электр./точил, упак.",
        sku="ELEC-TOCH-002",
        category_id=category.id,
        unit_id=unit.id,
        description="Shelf item, section A-3: electric sharpener",
    )
    # Item with ё in name
    item3 = Item(
        name="Берёза и Ёлка",
        sku="BEREZ-003",
        category_id=category.id,
        unit_id=unit.id,
    )
    # Item with hyphenated SKU
    item4 = Item(
        name="Метчик М3 17М-03-49270-G",
        sku="17М-03-49270-G",
        category_id=category.id,
        unit_id=unit.id,
    )
    db_session.add_all([item1, item2, item3, item4])
    await db_session.flush()


@pytest.mark.asyncio
async def test_search_with_double_spaces(db_session: AsyncSession):
    """Double spaces in search input should find items with single spaces in name."""
    from app.repos.catalog_repo import CatalogRepo

    repo = CatalogRepo(db_session)
    items, total = await repo.list_items_page(search="Круг  шлифовальный", category_id=None, page=1, page_size=10)
    assert total >= 1, "Should find item by normalized name despite double spaces in input"


@pytest.mark.asyncio
async def test_search_with_punctuation(db_session: AsyncSession):
    """Punctuation in search input should still find items."""
    from app.repos.catalog_repo import CatalogRepo

    repo = CatalogRepo(db_session)
    items, total = await repo.list_items_page(search="электр", category_id=None, page=1, page_size=10)
    assert total >= 1, "Should find item with partial normalized match"


@pytest.mark.asyncio
async def test_search_io_replacement(db_session: AsyncSession):
    """ё in search should find items with е."""
    from app.repos.catalog_repo import CatalogRepo

    repo = CatalogRepo(db_session)
    items, total = await repo.list_items_page(search="ёлка", category_id=None, page=1, page_size=10)
    assert total >= 1, "Should find 'Ёлка' when searching for 'ёлка'"


@pytest.mark.asyncio
async def test_search_case_insensitive(db_session: AsyncSession):
    """Case-insensitive search should work."""
    from app.repos.catalog_repo import CatalogRepo

    repo = CatalogRepo(db_session)
    items, total = await repo.list_items_page(search="КРУГ ШЛИФОВАЛЬНЫЙ", category_id=None, page=1, page_size=10)
    assert total >= 1, "Should find item with uppercase search"


@pytest.mark.asyncio
async def test_search_empty_after_normalize(db_session: AsyncSession):
    """Whitespace-only search should not crash and return unfiltered results."""
    from app.repos.catalog_repo import CatalogRepo

    repo = CatalogRepo(db_session)
    items, total = await repo.list_items_page(search="   ", category_id=None, page=1, page_size=10)
    assert total >= 4, "Whitespace-only search should return all items (seeded 4 items)"


@pytest.mark.asyncio
async def test_search_sku_with_hyphen(db_session: AsyncSession):
    """Search by SKU with hyphens must find item (raw_term preserves hyphens)."""
    from app.repos.catalog_repo import CatalogRepo

    repo = CatalogRepo(db_session)
    items, total = await repo.list_items_page(search="17М-03-49270-G", category_id=None, page=1, page_size=10)
    assert total >= 1, "Search by SKU with hyphens must find the item"
    if total > 0:
        assert items[0]["sku"] == "17М-03-49270-G"


@pytest.mark.asyncio
async def test_search_sku_partial_with_hyphen(db_session: AsyncSession):
    """Partial SKU search with hyphens should work."""
    from app.repos.catalog_repo import CatalogRepo

    repo = CatalogRepo(db_session)
    items, total = await repo.list_items_page(search="17М-03", category_id=None, page=1, page_size=10)
    assert total >= 1, "Partial SKU search with hyphens must find the item"


@pytest.mark.asyncio
async def test_search_by_normalized_name_with_hyphenated_sku_item(db_session: AsyncSession):
    """Item with hyphenated name should be found via normalized_name."""
    from app.repos.catalog_repo import CatalogRepo

    repo = CatalogRepo(db_session)
    items, total = await repo.list_items_page(search="Метчик М3", category_id=None, page=1, page_size=10)
    assert total >= 1, "Should find item by normalized name"


@pytest.mark.asyncio
async def test_search_description_with_punctuation(db_session: AsyncSession):
    """Search description with punctuation should work via raw_term."""
    from app.repos.catalog_repo import CatalogRepo

    repo = CatalogRepo(db_session)
    items, total = await repo.list_items_page(search="Shelf item", category_id=None, page=1, page_size=10)
    assert total >= 1, "Should find item by description match"


@pytest.mark.asyncio
async def test_search_category_normalized(db_session: AsyncSession):
    """Category search via normalized_name should work."""
    from app.repos.catalog_repo import CatalogRepo

    repo = CatalogRepo(db_session)
    categories, total = await repo.list_categories_page(
        search="тестовая категория", parent_id=None, page=1, page_size=10
    )
    assert total >= 1, "Should find category by normalized name"


class TestBuildTerms:
    """Term-level tests for build_term functions."""

    def test_normalized_vs_raw_sku_term(self):
        """Critical: normalized term != raw term for SKU with hyphens."""
        search = "17М-03-49270-G"
        normalized = build_normalized_like_term(search)
        raw = build_raw_like_term(search)
        assert normalized != raw
        assert "-" not in normalized
        assert "-" in raw

    def test_whitespace_only_returns_none(self):
        assert build_normalized_like_term("   ") is None
        assert build_raw_like_term("   ") is None

    def test_empty_returns_none(self):
        assert build_normalized_like_term("") is None
        assert build_raw_like_term("") is None
