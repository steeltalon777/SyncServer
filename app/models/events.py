"""SQLAlchemy event listeners for auto-computing normalized_name on insert/update.

All models with a `normalized_name` column derived from a name field
automatically compute it via normalize_for_storage before insert/update.

This guarantees normalized_name is always set regardless of the creation path
(service, ORM fixture, batch, machine).
"""

from __future__ import annotations

from sqlalchemy import event

from app.core.search_utils import normalize_for_storage
from app.models.category import Category
from app.models.device import Device
from app.models.item import Item
from app.models.site import Site
from app.models.temporary_item import TemporaryItem


@event.listens_for(Item, "before_insert")
@event.listens_for(Item, "before_update")
def _set_item_normalized_name(mapper, connection, target):
    if target.name is not None:
        target.normalized_name = normalize_for_storage(target.name)


@event.listens_for(Category, "before_insert")
@event.listens_for(Category, "before_update")
def _set_category_normalized_name(mapper, connection, target):
    if target.name is not None:
        target.normalized_name = normalize_for_storage(target.name)


@event.listens_for(TemporaryItem, "before_insert")
@event.listens_for(TemporaryItem, "before_update")
def _set_temporary_item_normalized_name(mapper, connection, target):
    if target.name is not None:
        target.normalized_name = normalize_for_storage(target.name)


@event.listens_for(Site, "before_insert")
@event.listens_for(Site, "before_update")
def _set_site_normalized_name(mapper, connection, target):
    if target.name is not None and hasattr(target, "normalized_name"):
        target.normalized_name = normalize_for_storage(target.name)


@event.listens_for(Device, "before_insert")
@event.listens_for(Device, "before_update")
def _set_device_normalized_name(mapper, connection, target):
    if target.device_name is not None and hasattr(target, "normalized_name"):
        target.normalized_name = normalize_for_storage(target.device_name)
