from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ORMBaseModel(BaseModel):
    """Base model for response DTOs loaded from ORM objects."""

    model_config = ConfigDict(from_attributes=True)
