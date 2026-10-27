"""Request bodies for the REST API."""
from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Priority = Literal["low", "medium", "high", "urgent"]
Effort = Literal["S", "M", "L", "XL"]
Status = Literal["basket", "active", "backlog", "done"]


Notify = Literal["desktop", "email", "both", "off"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    notes_html: str = ""
    status: Status = "basket"
    priority: Priority = "medium"
    important: bool = False
    my_day: Optional[str] = None
    effort: Effort = "M"
    due_at: Optional[str] = None
    reminder_at: Optional[str] = None
    tags: list[str] = []
    creative_score: Optional[int] = Field(default=None, ge=0, le=100)
    checklist: list[str] = []
    repeat: Literal["", "daily", "weekdays", "weekly", "monthly"] = ""
    notify: Notify = "desktop"


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    notes_html: Optional[str] = None
    status: Optional[Status] = None
    priority: Optional[Priority] = None
    important: Optional[bool] = None
    my_day: Optional[str] = None
    effort: Optional[Effort] = None
    due_at: Optional[str] = None
    reminder_at: Optional[str] = None
    repeat: Optional[Literal["", "daily", "weekdays", "weekly", "monthly"]] = None
    notify: Optional[Notify] = None
    assigned_week: Optional[str] = None
    week_locked: Optional[bool] = None
    pinned: Optional[bool] = None
    tags: Optional[list[str]] = None
    creative_score: Optional[int] = Field(default=None, ge=0, le=100)
    creative_locked: Optional[bool] = None


class PlaceBody(BaseModel):
    slot_index: int


class UnplaceBody(BaseModel):
    to: Literal["backlog", "basket"] = "backlog"


class ChecklistCreate(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class ChecklistUpdate(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    done: Optional[bool] = None


class ReorderBody(BaseModel):
    ids: list[int]


class LinkBody(BaseModel):
    other_id: int


class RethinkBody(BaseModel):
    include_basket: bool = False


class QuickLink(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    target: str = Field(min_length=1, max_length=2000, pattern=r"^([A-Za-z][A-Za-z0-9+.-]*:|~[\\/]|\\\\)")  # URI/app link, ~\path or \\server


class SettingsUpdate(BaseModel):
    ram_slots: Optional[int] = Field(default=None, ge=1, le=15)
    weekly_capacity_hours: Optional[float] = Field(default=None, ge=1, le=168)
    auto_fill: Optional[bool] = None
    model: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_tenant_id: Optional[str] = None
    planner_auto_sync: Optional[bool] = None
    briefing_enabled: Optional[bool] = None
    theme: Optional[Literal["blue", "teal", "green", "gold", "orange", "red", "purple", "silver"]] = None
    quick_links: Optional[list[QuickLink]] = Field(default=None, max_length=24)
    slot_positions: Optional[dict[str, list[float]]] = None
    notify_email: Optional[str] = Field(default=None, max_length=254, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")


    @field_validator("slot_positions")
    @classmethod
    def _positions(cls, v):
        if v is None:
            return v
        for k, p in v.items():
            if not k.isdigit() or int(k) > 14 or len(p) != 6 or any(not math.isfinite(x) or abs(x) > 3 for x in p):
                raise ValueError("slot_positions must map a synapse index to [x, y, z, nx, ny, nz]")
        return v


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatBody(BaseModel):
    messages: list[ChatMessage]


class Assignment(BaseModel):
    task_id: int
    slot_index: Optional[int] = None  # None => backlog
    reason: str = ""


class DelegateApply(BaseModel):
    assignments: list[Assignment]


class InsightBody(BaseModel):
    task_id: Optional[int] = None


class TemplateBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=500)
    notes_html: str = ""
    priority: Priority = "medium"
    effort: Effort = "M"
    tags: list[str] = []
    checklist: list[str] = []
    creative_score: Optional[int] = Field(default=None, ge=0, le=100)
    repeat: Literal["", "daily", "weekdays", "weekly", "monthly"] = ""
    notify: Notify = "desktop"
    due_in_days: Optional[int] = Field(default=None, ge=0, le=365)


class TemplateFromTask(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)


class TemplateUse(BaseModel):
    title: Optional[str] = Field(default=None, max_length=500)


class DependencyBody(BaseModel):
    depends_on_id: int


class OpenBody(BaseModel):
    task_id: Optional[int] = None
    new: bool = False                                    # open the new-task form
    window: Literal["tab", "popup", "app"] = "tab"       # popup/app: chromeless window (used by the wallpaper)
    view: Optional[Literal["settings"]] = None           # open the app with Settings showing
