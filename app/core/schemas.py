"""Public request and response contracts."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    message: str = Field(min_length=1, max_length=16000)


class ChatResponse(BaseModel):
    text: str
    pending_actions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    token: str = Field(min_length=20, max_length=100)


class PreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
