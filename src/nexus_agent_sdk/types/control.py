"""控制返回值使用原生 wire 字段的 TypedDict，不引入大小写转换。"""

from typing import Any, Literal, TypedDict


class SlashCommand(TypedDict, total=False):
    name: str
    description: str
    argumentHint: str


class ModelInfo(TypedDict, total=False):
    value: str
    displayName: str
    description: str


class AgentInfo(TypedDict, total=False):
    name: str
    description: str
    model: str


class AccountInfo(TypedDict, total=False):
    apiProvider: str
    apiKeySource: str
    email: str
    organization: str
    subscriptionType: str
    tokenSource: str


class InitializationResult(TypedDict, total=False):
    session_id: str
    cwd: str
    model: str
    pid: int
    protocol_capabilities: list[str]
    commands: list[SlashCommand]
    models: list[ModelInfo]
    agents: list[AgentInfo]
    account: AccountInfo
    output_style: str
    available_output_styles: list[str]
    fast_mode_state: str
    current_permission_mode: str


class ContextUsageCategory(TypedDict, total=False):
    name: str
    tokens: int
    color: str
    isDeferred: bool


class ContextUsageEntry(TypedDict, total=False):
    name: str
    path: str
    type: str
    serverName: str
    isLoaded: bool
    agentType: str
    source: str
    tokens: int


class ContextUsageGridCell(TypedDict, total=False):
    color: str
    isFilled: bool
    categoryName: str
    tokens: int
    percentage: float
    squareFullness: float


class ContextUsageResponse(TypedDict, total=False):
    categories: list[ContextUsageCategory]
    totalTokens: int
    maxTokens: int
    rawMaxTokens: int
    percentage: float
    model: str
    isAutoCompactEnabled: bool
    memoryFiles: list[ContextUsageEntry]
    mcpTools: list[ContextUsageEntry]
    agents: list[ContextUsageEntry]
    gridRows: list[list[ContextUsageGridCell]]
    autoCompactThreshold: int
    deferredBuiltinTools: list[ContextUsageEntry]
    systemTools: list[ContextUsageEntry]
    systemPromptSections: list[ContextUsageEntry]
    slashCommands: dict[str, int]
    apiUsage: dict[str, int]


class RewindFilesResult(TypedDict, total=False):
    canRewind: bool
    error: str
    filesChanged: list[str]
    insertions: int
    deletions: int


class SettingsSource(TypedDict, total=False):
    source: str
    settings: dict[str, Any]


class SettingsApplied(TypedDict, total=False):
    model: str
    effort: str


class SettingsResponse(TypedDict, total=False):
    effective: dict[str, Any]
    sources: list[SettingsSource]
    applied: SettingsApplied


class AutoDreamResult(TypedDict, total=False):
    status: Literal["skipped", "completed"]
    reason: str
    sessions_reviewed: int
    next_check_at_ms: int
    summary: str
    written_paths: list[str]


class McpToolInfo(TypedDict, total=False):
    name: str
    description: str
    inputSchema: dict[str, Any]
    annotations: dict[str, Any]
    _meta: dict[str, Any]


class McpServerStatus(TypedDict, total=False):
    name: str
    status: str
    error: str
    scope: str
    config: dict[str, Any]
    instructions: str
    serverInfo: dict[str, str]
    tools: list[McpToolInfo]


class McpStatusResponse(TypedDict, total=False):
    mcpServers: list[McpServerStatus]


class McpSetServersResult(TypedDict, total=False):
    added: list[str]
    removed: list[str]
    errors: dict[str, str]


class TaskMessageResult(TypedDict, total=False):
    task_id: str
    status: str
