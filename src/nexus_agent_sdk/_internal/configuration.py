"""将公开选项映射为 nxs 启动参数与 initialize 请求。"""

import json
import uuid

from ..mcp import SdkMcpServer
from ..options import AgentDefinition, NexusAgentOptions
from ..types import HookCallback, JsonObject
from .runtime import resolve_cli_path

SUPPORTED_CAPABILITIES = frozenset(
    {
        "auto_review_v1",
        "hook_response_ack_v1",
        "message_execution_policy_v1",
        "subagent_control_v1",
    }
)


class RuntimeConfiguration:
    """保存握手生成的 hook ID，供同一会话的回调分发使用。"""

    def __init__(self, options: NexusAgentOptions):
        self.options = options
        self.hooks: dict[str, HookCallback] = {}
        self.hook_timeouts: dict[str, float | None] = {}

    def command(self) -> list[str]:
        """映射明确支持的 CLI 参数，不引入 shell。"""
        options = self.options
        command = [
            resolve_cli_path(options.cli_path),
            *options.cli_args,
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-prompt-tool",
            "stdio",
        ]
        values = {
            "model": options.model,
            "fallback-model": options.fallback_model,
            "name": options.session_title,
            "agent": options.agent,
            "system-prompt-file": options.system_prompt_file,
            "resume-session-at": options.resume_session_at,
            "thinking": options.thinking,
            "thinking-display": options.thinking_display,
            "effort": options.effort,
            "task-budget": options.task_budget,
            "permission-mode": options.permission_mode,
            "max-turns": options.max_turns,
            "max-budget-usd": options.max_budget_usd,
            "max-thinking-tokens": options.max_thinking_tokens,
            "resume": options.resume,
            "session-id": options.session_id,
        }
        for name, value in values.items():
            if value is not None:
                command.extend([f"--{name}", str(value)])
        lists = {
            "betas": options.betas,
            "tools": options.tools,
            "allowedTools": options.allowed_tools,
            "disallowedTools": options.disallowed_tools,
            "setting-sources": options.setting_sources,
        }
        for name, items in lists.items():
            if items is not None:
                command.extend([f"--{name}", ",".join(items)])
        flags = {
            "strict-mcp-config": options.strict_mcp_config,
            "include-hook-events": options.include_hook_events,
            "replay-user-messages": options.replay_user_messages,
            "continue": options.continue_conversation,
            "fork-session": options.fork_session,
            "no-session-persistence": not options.persist_session,
            "include-partial-messages": options.include_partial_messages,
            "allow-dangerously-skip-permissions": (
                options.allow_dangerously_skip_permissions
            ),
        }
        command.extend(f"--{name}" for name, enabled in flags.items() if enabled)
        servers = {
            name: value
            for name, value in options.mcp_servers.items()
            if not isinstance(value, SdkMcpServer)
        }
        for name, payload in {
            "settings": options.settings,
            "mcp-config": {"mcpServers": servers} if servers else None,
        }.items():
            if payload is not None:
                command.extend([f"--{name}", json.dumps(payload, allow_nan=False)])
        for directory in options.additional_directories:
            command.extend(["--add-dir", str(directory)])
        return command

    def initialize_request(self) -> JsonObject:
        """保持 bridge 定义的 mixed-casing，不全局转换字段。"""
        options = self.options
        hooks: JsonObject = {}
        for event, matchers in options.hooks.items():
            hooks[event] = []
            for matcher in matchers:
                ids = []
                for callback in matcher.hooks:
                    callback_id = uuid.uuid4().hex
                    self.hooks[callback_id] = callback
                    self.hook_timeouts[callback_id] = matcher.timeout
                    ids.append(callback_id)
                entry: JsonObject = {"hookCallbackIds": ids}
                if matcher.matcher is not None:
                    entry["matcher"] = matcher.matcher
                if matcher.timeout is not None:
                    entry["timeout"] = matcher.timeout
                hooks[event].append(entry)
        request: JsonObject = {
            "subtype": "initialize",
            "protocol_capabilities": sorted(SUPPORTED_CAPABILITIES),
            "hooks": hooks,
            "agents": {
                name: value.to_wire() if isinstance(value, AgentDefinition) else value
                for name, value in options.agents.items()
            },
            "sdkMcpServers": [
                name
                for name, value in options.mcp_servers.items()
                if isinstance(value, SdkMcpServer)
            ],
        }
        for name, value in {
            "systemPrompt": options.system_prompt,
            "appendSystemPrompt": options.append_system_prompt,
            "jsonSchema": options.output_schema,
            "appendSystemPromptStatic": options.append_system_prompt_static,
            "appendSystemPromptDynamic": options.append_system_prompt_dynamic,
            "excludeDynamicSections": options.exclude_dynamic_sections,
            "agentProgressSummaries": options.agent_progress_summaries,
            "skills": options.skills,
            "disabledSkills": options.disabled_skills,
        }.items():
            if value is not None:
                request[name] = value
        return request
