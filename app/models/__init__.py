from app.models.asset_register import (
    IssuedAssetBalance,
    LostAssetBalance,
    OperationAcceptanceAction,
    PendingAcceptanceBalance,
)
from app.models.audit_event import AuditEvent
from app.models.audit_event_resource import AuditEventResource
from app.models.audit_item_effect import AuditItemEffect
from app.models.balance import Balance
from app.models.base import Base
from app.models.category import Category
from app.models.device import Device
from app.models.event import Event
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.machine import MachineBatch, MachineReport, MachineSnapshot
from app.models.document import Document, DocumentOperation, DocumentSource
from app.models.operation import Operation, OperationLine
from app.models.issue_object import IssueObject, IssueObjectAlias
from app.models.issue_object_category import IssueObjectCategory
from app.models.site import Site
from app.models.sync_state import SyncState
from app.models.temporary_item import TemporaryItem
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope

# Register SQLAlchemy event listeners for auto-computing normalized_name
# This import must come after all model imports
import app.models.events  # noqa: F401, E402


__all__ = [
    "AuditEvent",
    "AuditEventResource",
    "AuditItemEffect",
    "Base",
    "Site",
    "TemporaryItem",
    "Device",
    "IssueObject",
    "IssueObjectAlias",
    "IssueObjectCategory",
    "Category",
    "Item",
    "InventorySubject",
    "MachineSnapshot",
    "MachineReport",
    "MachineBatch",
    "Event",
    "Balance",
    "PendingAcceptanceBalance",
    "LostAssetBalance",
    "IssuedAssetBalance",
    "OperationAcceptanceAction",
    "Unit",
    "Operation",
    "OperationLine",
    "User",
    "UserAccessScope",
    "SyncState",
    "Document",
    "DocumentOperation",
    "DocumentSource",
]
