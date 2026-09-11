"""消息、内容块及 wire 投影；未知字段保留在 raw。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal, TypeVar, cast

from .common import JsonObject


@dataclass
class TextBlock:
    text: str
    raw: JsonObject = field(default_factory=dict)


@dataclass
class ThinkingBlock:
    thinking: str
    signature: str = ""
    raw: JsonObject = field(default_factory=dict)


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: JsonObject
    raw: JsonObject = field(default_factory=dict)


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: Any = None
    is_error: bool = False
    raw: JsonObject = field(default_factory=dict)


@dataclass
class UnknownBlock:
    raw: JsonObject


@dataclass
class Message:
    raw: JsonObject

    @property
    def type(self) -> str:
        return self.raw["type"]

    @property
    def session_id(self) -> str:
        return self.raw.get("session_id", "")

    @property
    def uuid(self) -> str:
        return self.raw.get("uuid", "")


@dataclass
class AssistantMessage(Message):
    content: list[ContentBlock]
    model: str = ""
    parent_tool_use_id: str | None = None
    usage: JsonObject = field(default_factory=dict)
    stop_reason: str | None = None
    error: str | None = None
    api_error: str | None = None
    error_details: str | None = None
    is_api_error_message: bool = False


@dataclass
class UserMessage(Message):
    content: list[ContentBlock]
    parent_tool_use_id: str | None = None
    is_meta: bool = False
    is_replay: bool = False
    is_synthetic: bool = False
    tool_use_result: Any = None


@dataclass
class SystemMessage(Message):
    subtype: str = ""


@dataclass
class ResultMessage(Message):
    subtype: str = ""
    is_error: bool = False
    result: str | None = None
    num_turns: int = 0
    total_cost_usd: float | None = None
    usage: JsonObject = field(default_factory=dict)
    structured_output: Any = None
    duration_ms: int = 0
    duration_api_ms: int = 0
    stop_reason: str | None = None
    terminal_reason: str = ""
    model_usage: dict[str, JsonObject] = field(default_factory=dict)
    permission_denials: list[JsonObject] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fast_mode_state: str = ""


@dataclass
class StreamEvent(Message):
    event: JsonObject = field(default_factory=dict)


@dataclass
class ImageBlock:
    source: JsonObject = field(default_factory=dict)
    data: str = ""
    mime_type: str = ""
    raw: JsonObject = field(default_factory=dict)


@dataclass
class DocumentBlock:
    source: JsonObject = field(default_factory=dict)
    title: str = ""
    mime_type: str = ""
    raw: JsonObject = field(default_factory=dict)


@dataclass
class SearchResultBlock:
    query: str = ""
    source: str = ""
    title: str = ""
    url: str = ""
    snippet: str = ""
    raw: JsonObject = field(default_factory=dict)


@dataclass
class ResourceLinkBlock:
    name: str = ""
    uri: str = ""
    description: str = ""
    raw: JsonObject = field(default_factory=dict)


@dataclass
class ToolProgressMessage(Message):
    tool_use_id: str = ""
    tool_name: str = ""
    parent_tool_use_id: str | None = None
    elapsed_time_seconds: float = 0
    task_id: str = ""


@dataclass
class ToolUseSummaryMessage(Message):
    summary: str = ""
    preceding_tool_use_ids: list[str] = field(default_factory=list)


@dataclass
class TaskStartedMessage(Message):
    task_id: str = ""
    tool_use_id: str = ""
    agent_id: str = ""
    agent_type: str = ""
    child_session_id: str = ""
    description: str = ""
    task_type: str = ""
    parent_task_id: str = ""
    output_file: str = ""
    prompt: str = ""


@dataclass
class TaskProgressMessage(TaskStartedMessage):
    last_tool_name: str = ""
    summary: str = ""
    usage: JsonObject = field(default_factory=dict)


@dataclass
class TaskNotificationMessage(TaskProgressMessage):
    status: str = ""


@dataclass
class TaskUpdatedMessage(Message):
    task_id: str = ""
    status: str = ""
    patch: JsonObject = field(default_factory=dict)


@dataclass
class RateLimitEvent(Message):
    rate_limit_info: JsonObject = field(default_factory=dict)


@dataclass
class AuthStatusMessage(Message):
    is_authenticating: bool = False
    output: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class PromptSuggestionMessage(Message):
    suggestion: str = ""


@dataclass
class AttachmentMessage(Message):
    attachment: JsonObject = field(default_factory=dict)


@dataclass
class ControlAck(Message):
    request_id: str = ""
    request_subtype: str = ""
    stage: str = ""
    hook_event_name: str = ""
    tool_use_id: str = ""


ContentBlock = (
    TextBlock
    | ThinkingBlock
    | ToolUseBlock
    | ToolResultBlock
    | ImageBlock
    | DocumentBlock
    | SearchResultBlock
    | ResourceLinkBlock
    | UnknownBlock
)


_BLOCK_TYPES = {
    "text": TextBlock,
    "thinking": ThinkingBlock,
    "tool_use": ToolUseBlock,
    "tool_result": ToolResultBlock,
    "image": ImageBlock,
    "document": DocumentBlock,
    "search_result": SearchResultBlock,
    "resource_link": ResourceLinkBlock,
}


_MESSAGE_TYPES = {
    "result": ResultMessage,
    "system": SystemMessage,
    "stream_event": StreamEvent,
    "tool_progress": ToolProgressMessage,
    "tool_use_summary": ToolUseSummaryMessage,
    "task_started": TaskStartedMessage,
    "task_progress": TaskProgressMessage,
    "task_notification": TaskNotificationMessage,
    "task_updated": TaskUpdatedMessage,
    "rate_limit_event": RateLimitEvent,
    "auth_status": AuthStatusMessage,
    "prompt_suggestion": PromptSuggestionMessage,
    "attachment": AttachmentMessage,
    "control_ack": ControlAck,
}


T = TypeVar("T")


def _project(cls: type[T], raw: JsonObject, **overrides: Any) -> T:
    """只投影同名已声明字段；未知字段仍保留在 raw，禁止全局改写键名。"""
    names = {item.name for item in fields(cast(Any, cls))}
    return cls(
        **{
            **{key: value for key, value in raw.items() if key in names},
            "raw": raw,
            **overrides,
        }
    )


def _content(value: Any) -> list[ContentBlock]:
    """保留多模态数据和未知块，同时拒绝损坏的内容包络。"""
    if isinstance(value, str):
        return [TextBlock(value)]
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Message content must be text or a list")
    blocks: list[ContentBlock] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise ValueError("Content block requires a string type")
        cls = _BLOCK_TYPES.get(item["type"], UnknownBlock)
        blocks.append(_project(cls, item))
    return blocks


def parse_message(raw: JsonObject) -> Message:
    """按稳定协议字段生成消息，保留未知事件。"""
    kind = raw["type"]
    if kind in {"assistant", "user"}:
        body = raw["message"]
        if not isinstance(body, dict):
            raise ValueError("message must be an object")
        values: JsonObject = {"content": _content(body.get("content"))}
        if kind == "assistant":
            values.update(
                model=body.get("model", ""),
                usage=body.get("usage") or {},
                stop_reason=body.get("stop_reason"),
            )
            return _project(AssistantMessage, raw, **values)
        return _project(UserMessage, raw, **values)
    # nxs 会把任务事件放在 system subtype；与顶层同名事件保持同一投影。
    effective = raw.get("subtype", "") if kind == "system" else kind
    cls = _MESSAGE_TYPES.get(effective, _MESSAGE_TYPES.get(kind, Message))
    return _project(cls, raw)


@dataclass
class OutboundMessageOptions:
    uuid: str = ""
    is_meta: bool = False
    is_synthetic: bool = False
    hidden_from_user: bool = False
    recall_query: str = ""
    purpose: str = ""
    priority: str = ""
    tool_access: Literal["none", "inherit", ""] = ""
    max_output_tokens: int | None = None
    skip_auto_memory: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    def to_wire(self) -> JsonObject:
        """消息执行限制与元数据使用 bridge 的顶层字段。"""
        if self.tool_access not in {"none", "inherit", ""}:
            raise ValueError("Invalid tool_access")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        result = {
            key: value
            for key, value in asdict(self).items()
            if value is not None and value != "" and value != {} and value is not False
        }
        if self.is_meta:
            result["is_synthetic"] = True
        return result


@dataclass
class OutboundMessage:
    content: str | list[JsonObject]
    options: OutboundMessageOptions = field(default_factory=OutboundMessageOptions)
    session_id: str | None = None
    parent_tool_use_id: str | None = None

    def to_wire(self) -> JsonObject:
        return {
            "type": "user",
            "message": {"role": "user", "content": self.content},
            "parent_tool_use_id": self.parent_tool_use_id,
            **({"session_id": self.session_id} if self.session_id else {}),
            **self.options.to_wire(),
        }
