"""Response schema for development audit events."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AuditEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    event_id: str
    actor_id: str
    actor_source: str
    action: Literal["created", "updated", "deleted"]
    resource_type: str
    resource_id: str | None
    outcome: Literal["success"]
    occurred_at: datetime
