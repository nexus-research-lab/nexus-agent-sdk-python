"""宿主权限、hook 与交互回调的输入输出类型。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, TypedDict

from .common import JsonObject


class HookContext(TypedDict):
    request_id: str
    cancelled: asyncio.Event


HookCallback = Callable[[JsonObject, str | None, HookContext], Awaitable[JsonObject]]


@dataclass
class PermissionResultAllow:
    updated_input: JsonObject | None = None
    updated_permissions: list[JsonObject] | None = None
    accept_feedback: str | None = None

    def to_wire(self, original: JsonObject) -> JsonObject:
        """保留权限协议指定的大小写。"""
        result: JsonObject = {
            "behavior": "allow",
            "updatedInput": self.updated_input
            if self.updated_input is not None
            else original,
        }
        if self.updated_permissions is not None:
            result["updatedPermissions"] = self.updated_permissions
        if self.accept_feedback is not None:
            result["acceptFeedback"] = self.accept_feedback
        return result


@dataclass
class PermissionResultDeny:
    message: str = "Permission denied"
    interrupt: bool = False
    error_code: str = ""

    def to_wire(self, original: JsonObject) -> JsonObject:
        """明确拒绝，不把回调缺失解释为允许。"""
        return {
            "behavior": "deny",
            "message": self.message,
            "interrupt": self.interrupt,
            "errorCode": self.error_code,
        }


@dataclass
class ToolPermissionContext:
    tool_use_id: str | None = None
    suggestions: list[JsonObject] = field(default_factory=list)
    raw: JsonObject = field(default_factory=dict)

    cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    request_id: str = ""


PermissionCallback = Callable[
    [str, JsonObject, ToolPermissionContext],
    Awaitable[PermissionResultAllow | PermissionResultDeny],
]


@dataclass
class HookMatcher:
    hooks: list[HookCallback]
    matcher: str | None = None
    timeout: float | None = None


@dataclass
class ElicitationRequest:
    mcp_server_name: str = ""
    message: str = ""
    mode: str = "form"
    url: str = ""
    elicitation_id: str = ""
    requested_schema: JsonObject = field(default_factory=dict)
    title: str = ""
    display_name: str = ""
    description: str = ""
    raw: JsonObject = field(default_factory=dict)


@dataclass
class ElicitationResult:
    action: Literal["accept", "decline", "cancel"] = "cancel"
    content: JsonObject | None = None

    def to_wire(self) -> JsonObject:
        if self.action not in {"accept", "decline", "cancel"}:
            raise ValueError("Invalid elicitation action")
        return {"action": self.action, "content": self.content}


@dataclass
class UserDialogRequest:
    dialog_kind: str = ""
    payload: JsonObject = field(default_factory=dict)
    tool_use_id: str = ""
    raw: JsonObject = field(default_factory=dict)


ElicitationCallback = Callable[[ElicitationRequest], Awaitable[ElicitationResult]]


UserDialogCallback = Callable[[UserDialogRequest], Awaitable[JsonObject]]


OAuthTokenCallback = Callable[[], Awaitable[str | None]]
