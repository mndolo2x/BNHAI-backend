"""API request and response schemas for authentication."""
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        cleaned = value.strip().casefold()
        if not cleaned:
            raise ValueError("Username cannot be blank.")
        return cleaned


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class FacilityRole(BaseModel):
    facility_id: str
    role: str


class CurrentUserResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
    is_active: bool
    assignments: list[FacilityRole]
