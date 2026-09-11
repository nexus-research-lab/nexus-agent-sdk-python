# Nexus Agent SDK for Python

Python SDK for Nexus Agent.

[中文](README.zh-CN.md) · [API reference](docs/api-reference.md) · [Examples](examples/)

## Installation

Python 3.11+.

```sh
pip install nexus-agent-sdk-python
```

Platform wheels include nxs and rg. Supported platforms: Linux, macOS and Windows on x86_64 and ARM64.

```sh
export ANTHROPIC_API_KEY="your-api-key"
```

Custom runtime:

```python
from nexus_agent_sdk import NexusAgentOptions

options = NexusAgentOptions(cli_path="/path/to/nxs")
```

## Quick Start

```python
import asyncio

from nexus_agent_sdk import query


async def main():
    async for message in query(prompt="What is 2 + 2?"):
        print(message)


asyncio.run(main())
```

## Providers

### Anthropic Messages

```python
import os

from nexus_agent_sdk import AnthropicProvider, NexusAgentOptions

options = NexusAgentOptions(
    provider=AnthropicProvider(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url="https://api.anthropic.com",
    ),
    model="claude-sonnet-4-6",
)
```

### OpenAI

```python
import os

from nexus_agent_sdk import NexusAgentOptions, OpenAIProvider

options = NexusAgentOptions(
    provider=OpenAIProvider(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url="https://api.openai.com/v1",
        protocol="responses",
    ),
    model=os.environ["OPENAI_MODEL"],
)
```

| Provider | Fields |
| --- | --- |
| `AnthropicProvider` | `api_key`, `auth_token`, `base_url`, `version`, `headers`, `tool_discovery_transport` |
| `OpenAIProvider` | `api_key`, `base_url`, `protocol`, `org_id`, `project_id`, `headers` |

`protocol` accepts `chat_completions` or `responses`. Use `base_url` for compatible services.
Provider fields override matching `options.env` entries. Unset fields inherit environment configuration.
Anthropic credentials use `api_key` or `auth_token`.

[Provider example](examples/providers.py) · [Provider API](src/nexus_agent_sdk/provider.py)

## query()

```python
import asyncio

from nexus_agent_sdk import AssistantMessage, NexusAgentOptions, TextBlock, query


async def main():
    options = NexusAgentOptions(
        system_prompt="You are a code reviewer.",
        cwd="/path/to/project",
        tools=["Read", "Glob", "Grep"],
        allowed_tools=["Read", "Glob", "Grep"],
        max_turns=3,
    )
    async for message in query(prompt="Review this project", options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)


asyncio.run(main())
```

| Option | Purpose |
| --- | --- |
| `model` | Model name |
| `system_prompt` | System prompt |
| `cwd` | Working directory |
| `tools` | Built-in tool set |
| `allowed_tools` | Permission allowlist |
| `disallowed_tools` | Blocked tools |
| `permission_mode` | Permission policy |
| `max_turns` | Turn limit |
| `max_budget_usd` | Cost limit |
| `env` | Runtime environment variables |

[Options](src/nexus_agent_sdk/options.py)

## NexusSDKClient

```python
import asyncio

from nexus_agent_sdk import NexusSDKClient


async def main():
    async with NexusSDKClient() as client:
        await client.query("Remember the number 7")
        print((await client.receive_result()).result)

        await client.query("What number did I give you?")
        async for message in client.receive_response():
            print(message)


asyncio.run(main())
```

| Method | Purpose |
| --- | --- |
| `query(prompt)` | Submit a prompt or async iterable |
| `receive_response()` | Read through the next result |
| `receive_result()` | Return the result; raise `ResultError` on failure |
| `receive_messages()` | Read the message stream |
| `interrupt()` | Interrupt the current turn |
| `set_model(model)` | Change the model |
| `set_permission_mode(mode)` | Change the permission policy |
| `get_context_usage()` | Read context usage |
| `get_mcp_status()` | Read MCP server status |

Consume async iterable input with `receive_messages()` through completion before submitting another query.

[Client API](src/nexus_agent_sdk/client.py) · [Streaming input](examples/streaming.py)

## Custom Tools

```python
import asyncio

from nexus_agent_sdk import (
    NexusAgentOptions,
    NexusSDKClient,
    create_sdk_mcp_server,
    tool,
)


@tool("add", "Add two numbers", {"a": int, "b": int})
async def add(args):
    return {"content": [{"type": "text", "text": str(args["a"] + args["b"])}]}


async def main():
    server = create_sdk_mcp_server(name="calculator", tools=[add])
    options = NexusAgentOptions(
        mcp_servers={"calculator": server},
        allowed_tools=["mcp__calculator__add"],
    )
    async with NexusSDKClient(options) as client:
        await client.query("Use the calculator to add 12 and 30")
        print((await client.receive_result()).result)


asyncio.run(main())
```

### External MCP Servers

```python
from nexus_agent_sdk import NexusAgentOptions

options = NexusAgentOptions(
    mcp_servers={
        "tools": {
            "type": "stdio",
            "command": "python",
            "args": ["/path/to/mcp_server.py"],
        }
    }
)
```

## Hooks

```python
from nexus_agent_sdk import HookMatcher, NexusAgentOptions


async def log_tool_call(input_data, tool_use_id, context):
    print(input_data["tool_name"], input_data["tool_input"])
    return {}


options = NexusAgentOptions(
    hooks={
        "PreToolUse": [HookMatcher(hooks=[log_tool_call])],
    }
)
```

[Hooks and permission callbacks](examples/callbacks.py)

## Sessions

```python
from nexus_agent_sdk import NexusAgentOptions, SessionStore

store = SessionStore()
for session in store.list_sessions():
    print(session.session_id)

options = NexusAgentOptions(resume="session-id")
fork_options = NexusAgentOptions(resume="session-id", fork_session=True)
```

[Session API](src/nexus_agent_sdk/sessions.py)

## Types

| Types | Source |
| --- | --- |
| `NexusAgentOptions`, `AgentDefinition` | [options.py](src/nexus_agent_sdk/options.py) |
| `AssistantMessage`, `UserMessage`, `SystemMessage`, `ResultMessage` | [messages.py](src/nexus_agent_sdk/types/messages.py) |
| `TextBlock`, `ThinkingBlock`, `ToolUseBlock`, `ToolResultBlock` | [messages.py](src/nexus_agent_sdk/types/messages.py) |
| `PermissionResultAllow`, `PermissionResultDeny`, `HookMatcher` | [callbacks.py](src/nexus_agent_sdk/types/callbacks.py) |
| `InitializationResult`, `ContextUsageResponse`, `McpStatusResponse` | [control.py](src/nexus_agent_sdk/types/control.py) |

## Error Handling

| Exception | Cause |
| --- | --- |
| `NexusSDKError` | SDK operation failure |
| `ProcessError` | Runtime startup or exit failure |
| `ProtocolError` | Invalid runtime output |
| `ControlError` | Rejected control request |
| `ResultError` | Error result from `receive_result()` |
| `BufferOverflowError` | Message queue limit exceeded |

[Error types](src/nexus_agent_sdk/errors.py)

## Development

```sh
uv sync --frozen --group dev
uv run python -m compileall -q examples
uv run ruff check .
uv run ruff format --check .
uv run mypy src/nexus_agent_sdk
uv build
```

Source checkouts require nxs on PATH or `cli_path`.

[Build and release](docs/releasing.md) · [Changelog](CHANGELOG.md)

## License

[Apache-2.0](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES)
