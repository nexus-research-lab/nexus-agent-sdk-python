"""nxs 启动配置，仅封装已存在的 CLI 参数。"""

import math
from dataclasses import dataclass, field
from pathlib import Path

from .mcp import SdkMcpServer
from .provider import AnthropicProvider, OpenAIProvider
from .types import (
    ElicitationCallback,
    HookMatcher,
    JsonObject,
    OAuthTokenCallback,
    PermissionCallback,
    PermissionMode,
    UserDialogCallback,
)


@dataclass
class AgentDefinition:
    description: str
    prompt: str
    tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    model: str | None = None
    mcp_servers: list = field(default_factory=list)
    required_mcp_servers: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    initial_prompt: str | None = None
    max_turns: int | None = None
    background: bool | None = None
    isolation: str | None = None
    effort: str | None = None
    permission_mode: PermissionMode | None = None

    def to_wire(self) -> JsonObject:
        return {
            key: value
            for key, value in {
                "description": self.description,
                "prompt": self.prompt,
                "tools": self.tools,
                "disallowedTools": self.disallowed_tools,
                "model": self.model,
                "mcpServers": self.mcp_servers,
                "requiredMcpServers": self.required_mcp_servers,
                "skills": self.skills,
                "initialPrompt": self.initial_prompt,
                "maxTurns": self.max_turns,
                "background": self.background,
                "isolation": self.isolation,
                "effort": self.effort,
                "permissionMode": self.permission_mode,
            }.items()
            if value is not None
        }


@dataclass
class NexusAgentOptions:
    cli_path: str | Path | None = None
    cli_args: list[str] = field(default_factory=list)
    cwd: str | Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    provider: AnthropicProvider | OpenAIProvider | None = None
    model: str | None = None
    fallback_model: str | None = None
    betas: list[str] = field(default_factory=list)
    agent: str | None = None
    session_title: str | None = None
    system_prompt_file: str | Path | None = None
    append_system_prompt_static: str | None = None
    append_system_prompt_dynamic: str | None = None
    exclude_dynamic_sections: bool | None = None
    agent_progress_summaries: bool | None = None
    skills: list[str] | None = None
    disabled_skills: list[str] = field(default_factory=list)
    additional_directories: list[str | Path] = field(default_factory=list)
    thinking: str | None = None
    thinking_display: str | None = None
    effort: str | None = None
    task_budget: int | None = None
    resume_session_at: str | None = None
    strict_mcp_config: bool = False
    include_hook_events: bool = False
    enable_file_checkpointing: bool = False
    replay_user_messages: bool = False
    system_prompt: str | None = None
    append_system_prompt: str | None = None
    tools: list[str] | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    permission_mode: PermissionMode = "default"
    allow_dangerously_skip_permissions: bool = False
    max_turns: int | None = None
    max_budget_usd: float | None = None
    max_thinking_tokens: int | None = None
    resume: str | None = None
    session_id: str | None = None
    continue_conversation: bool = False
    fork_session: bool = False
    persist_session: bool = True
    include_partial_messages: bool = False
    settings: JsonObject | None = None
    setting_sources: list[str] | None = None
    mcp_servers: dict[str, SdkMcpServer | JsonObject] = field(default_factory=dict)
    agents: dict[str, AgentDefinition | JsonObject] = field(default_factory=dict)
    output_schema: JsonObject | None = None
    can_use_tool: PermissionCallback | None = None
    hooks: dict[str, list[HookMatcher]] = field(default_factory=dict)
    on_elicitation: ElicitationCallback | None = None
    on_user_dialog: UserDialogCallback | None = None
    on_oauth_token_refresh: OAuthTokenCallback | None = None
    callback_timeout: float | None = None
    control_timeout: float = 60
    shutdown_timeout: float = 5
    max_buffer_size: int = 16 * 1024 * 1024
    max_queue_bytes: int = 64 * 1024 * 1024

    def validate(self) -> None:
        """进程启动前拒绝无效预算及隐式权限绕过。"""
        if self.provider is not None:
            if not isinstance(self.provider, (AnthropicProvider, OpenAIProvider)):
                raise TypeError("provider must be AnthropicProvider or OpenAIProvider")
            self.provider.to_env()
        if self.resume and self.continue_conversation:
            raise ValueError("resume and continue_conversation are mutually exclusive")
        if self.system_prompt is not None and self.system_prompt_file is not None:
            raise ValueError("Choose system_prompt or system_prompt_file")
        if self.thinking not in {None, "adaptive", "disabled", "enabled"}:
            raise ValueError("Invalid thinking mode")
        if self.permission_mode not in {
            "default",
            "acceptEdits",
            "plan",
            "bypassPermissions",
            "auto",
        }:
            raise ValueError("Invalid permission_mode")
        if (
            self.permission_mode == "bypassPermissions"
            and not self.allow_dangerously_skip_permissions
        ):
            raise ValueError("bypassPermissions requires explicit opt-in")
        for name in (
            "max_turns",
            "task_budget",
            "max_thinking_tokens",
            "max_buffer_size",
            "max_queue_bytes",
        ):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool)
            ):
                raise ValueError(f"{name} must be an integer")
        if self.max_thinking_tokens is not None and self.max_thinking_tokens < 0:
            raise ValueError("max_thinking_tokens must be non-negative")
        for name in (
            "max_turns",
            "max_budget_usd",
            "control_timeout",
            "shutdown_timeout",
            "max_buffer_size",
            "max_queue_bytes",
            "callback_timeout",
            "task_budget",
        ):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"{name} must be positive")

        for matchers in self.hooks.values():
            for matcher in matchers:
                if matcher.timeout is not None and (
                    not math.isfinite(matcher.timeout) or matcher.timeout <= 0
                ):
                    raise ValueError("Hook timeout must be positive and finite")
