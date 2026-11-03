"""Schemas for dashboard, notifications, facility and user administration APIs."""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class RoleName(str, Enum):
    receptionist = "receptionist"
    nurse = "nurse"
    clinician = "clinician"
    laboratory_worker = "laboratory_worker"
    follow_up_worker = "follow_up_worker"
    facility_admin = "facility_admin"
    auditor = "auditor"
    platform_admin = "platform_admin"


class FacilityBase(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    district: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=1000)
    contact_email: str | None = Field(default=None, max_length=254)
    contact_phone: str | None = Field(default=None, max_length=40)

    @field_validator("name", "district", "address", "contact_email", "contact_phone")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class FacilityCreate(FacilityBase):
    facility_id: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class FacilityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    district: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=1000)
    contact_email: str | None = Field(default=None, max_length=254)
    contact_phone: str | None = Field(default=None, max_length=40)

    @field_validator("name", "district", "address", "contact_email", "contact_phone")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class FacilityRead(FacilityBase):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    facility_id: str
    created_at: datetime
    updated_at: datetime


class FacilityRoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    assignment_id: str
    facility_id: str
    role: RoleName
    assigned_at: datetime


class ManagedUserRead(BaseModel):
    user_id: str
    username: str
    display_name: str
    is_active: bool
    created_at: datetime
    assignments: list[FacilityRoleRead]


class ManagedUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    display_name: str = Field(min_length=2, max_length=200)
    initial_password: SecretStr = Field(min_length=12, max_length=128)
    facility_id: str = Field(min_length=2, max_length=80)
    role: RoleName

    @field_validator("username", "display_name", "facility_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned


class ManagedUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    is_active: bool | None = None

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name cannot be blank.")
        return cleaned


class RoleAssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facility_id: str = Field(min_length=2, max_length=80)
    role: RoleName


class DashboardActivity(BaseModel):
    event_id: str
    action: str
    resource_type: str
    resource_id: str | None
    actor_display_name: str
    occurred_at: datetime


class DashboardSummary(BaseModel):
    generated_at: datetime
    facility_count: int
    patient_count: int
    active_patient_count: int
    encounters_in_progress: int
    notes_awaiting_review: int
    lab_reports_awaiting_review: int
    follow_ups_open: int
    follow_ups_overdue: int
    recent_activity: list[DashboardActivity]


class NotificationCategory(str, Enum):
    workflow = "workflow"
    laboratory = "laboratory"
    follow_up = "follow_up"
    administration = "administration"
    system = "system"


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    notification_id: str
    facility_id: str
    category: NotificationCategory
    title: str
    message: str
    resource_type: str | None
    resource_id: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationList(BaseModel):
    items: list[NotificationRead]
    total: int
    unread_count: int


class NotificationMarkRead(BaseModel):
    notification_id: str
    read_at: datetime
