"""Fast baseline sanity tests.

Quick checks that run in under 10 seconds and require no external services.
Verifies app creation, basic endpoint availability, and model instantiation.
"""

import os
import sys

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.fast
@pytest.mark.unit
def test_app_creates():
    """create_app() returns a FastAPI app instance."""
    from fastapi import FastAPI
    from main import create_app

    app = create_app(enable_startup_migrations=False)
    assert isinstance(app, FastAPI)
    assert app.title == "SyncServer API"


@pytest.mark.fast
@pytest.mark.unit
def test_root_endpoint_registered():
    """The root GET endpoint is registered in the app."""
    from main import create_app

    app = create_app(enable_startup_migrations=False)
    routes = {route.path for route in app.routes}
    assert "/" in routes


@pytest.mark.fast
@pytest.mark.unit
def test_health_endpoint_registered():
    """The /api/v1/health endpoint is registered in the app."""
    from main import create_app

    app = create_app(enable_startup_migrations=False)
    routes = {route.path for route in app.routes}
    assert "/api/v1/health" in routes


@pytest.mark.fast
@pytest.mark.unit
def test_api_v1_prefix_routes_exist():
    """Core API v1 route groups are registered."""
    from main import create_app

    app = create_app(enable_startup_migrations=False)
    paths = {route.path for route in app.routes}

    expected_prefixes = [
        "/api/v1/health",
        "/api/v1/catalog",
        "/api/v1/operations",
        "/api/v1/documents",
    ]
    for prefix in expected_prefixes:
        matching = [p for p in paths if p.startswith(prefix)]
        assert matching, f"No routes found under {prefix}"


@pytest.mark.fast
@pytest.mark.unit
def test_site_model_instantiation():
    """At least one model (Site) can be instantiated."""
    from app.models.site import Site

    site = Site(code="TEST-001", name="Test Site", is_active=True)
    assert site.code == "TEST-001"
    assert site.name == "Test Site"
    assert site.is_active is True


@pytest.mark.fast
@pytest.mark.unit
def test_operation_model_instantiation():
    """Operation model can be instantiated with required fields."""
    from uuid import uuid4

    from app.models.operation import Operation

    user_id = uuid4()
    site_id = 1

    op = Operation(
        site_id=site_id,
        operation_type="RECEIVE",
        status="draft",
        created_by_user_id=user_id,
    )
    assert op.operation_type == "RECEIVE"
    assert op.status == "draft"
    assert op.site_id == site_id
