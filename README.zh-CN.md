# Nexus Agent SDK for Python

Nexus Agent 的 Python SDK。

[English](README.md) · [API 参考](docs/api-reference.md) · [示例](examples/)

## 安装

Python 3.11+.

```sh
pip install nexus-agent-sdk-python
```

平台 wheel 包含 nxs 和 rg。支持 Linux、macOS、Windows 的 x86_64 与 ARM64。

```sh
export ANTHROPIC_API_KEY="your-api-key"
```

指定运行时

```python
from nexus_agent_sdk import NexusAgentOptions

options = NexusAgentOptions(cli_path="/path/to/nxs")
```

## 入门

```python
import asyncio

from nexus_agent_sdk import query


async def main():
    async for message in query(prompt="2 + 2 等于多少？"):
        print(message)


asyncio.run(main())
```

## Provider

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

| Provider | 字段 |
| --- | --- |
| `AnthropicProvider` | `api_key`, `auth_token`, `base_url`, `version`, `headers`, `tool_discovery_transport` |
| `OpenAIProvider` | `api_key`, `base_url`, `protocol`, `org_id`, `project_id`, `headers` |

`protocol` 支持 `chat_completions` 和 `responses`。兼容服务通过 `base_url` 配置。
Provider 字段覆盖 `options.env` 中的同名配置，未设置的字段沿用环境配置。
Anthropic 凭据选择 `api_key` 或 `auth_token`。

[Provider 示例](examples/providers.py) · [Provider API](src/nexus_agent_sdk/provider.py)

## query()

```python
import asyncio

from nexus_agent_sdk import AssistantMessage, NexusAgentOptions, TextBlock, query


async def main():
    options = NexusAgentOptions(
        system_prompt="你是一名代码审查员。",
        cwd="/path/to/project",
        tools=["Read", "Glob", "Grep"],
        allowed_tools=["Read", "Glob", "Grep"],
        max_turns=3,
    )
    async for message in query(prompt="审查这个项目", options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)


asyncio.run(main())
```

| 选项 | 用途 |
| --- | --- |
| `model` | 模型名称 |
| `system_prompt` | 系统提示词 |
| `cwd` | 工作目录 |
| `tools` | 内置工具集 |
| `allowed_tools` | 权限白名单 |
| `disallowed_tools` | 禁用工具 |
| `permission_mode` | 权限策略 |
| `max_turns` | 轮次上限 |
| `max_budget_usd` | 费用上限 |
| `env` | 运行时环境变量 |

[配置选项](src/nexus_agent_sdk/options.py)

## NexusSDKClient

```python
import asyncio

from nexus_agent_sdk import NexusSDKClient


async def main():
    async with NexusSDKClient() as client:
        await client.query("记住数字 7")
        print((await client.receive_result()).result)

        await client.query("我给你的数字是多少？")
        async for message in client.receive_response():
            print(message)


asyncio.run(main())
```

| 方法 | 用途 |
| --- | --- |
| `query(prompt)` | 提交提示词或异步可迭代对象 |
| `receive_response()` | 读取消息至下一条结果 |
| `receive_result()` | 获取结果；失败时抛出 `ResultError` |
| `receive_messages()` | 读取消息流 |
| `interrupt()` | 中断当前轮次 |
| `set_model(model)` | 切换模型 |
| `set_permission_mode(mode)` | 切换权限策略 |
| `get_context_usage()` | 获取上下文用量 |
| `get_mcp_status()` | 获取 MCP 服务状态 |

异步可迭代输入需通过 `receive_messages()` 消费至结束后提交新查询。

[客户端 API](src/nexus_agent_sdk/client.py) · [流式输入](examples/streaming.py)

## 自定义工具

```python
import asyncio

from nexus_agent_sdk import (
    NexusAgentOptions,
    NexusSDKClient,
    create_sdk_mcp_server,
    tool,
)


@tool("add", "计算两数之和", {"a": int, "b": int})
async def add(args):
    return {"content": [{"type": "text", "text": str(args["a"] + args["b"])}]}


async def main():
    server = create_sdk_mcp_server(name="calculator", tools=[add])
    options = NexusAgentOptions(
        mcp_servers={"calculator": server},
        allowed_tools=["mcp__calculator__add"],
    )
    async with NexusSDKClient(options) as client:
        await client.query("用计算器计算 12 加 30")
        print((await client.receive_result()).result)


asyncio.run(main())
```

### 外部 MCP 服务

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

[Hook 与权限回调](examples/callbacks.py)

## 会话

```python
from nexus_agent_sdk import NexusAgentOptions, SessionStore

store = SessionStore()
for session in store.list_sessions():
    print(session.session_id)

options = NexusAgentOptions(resume="session-id")
fork_options = NexusAgentOptions(resume="session-id", fork_session=True)
```

[会话 API](src/nexus_agent_sdk/sessions.py)

## 类型

| 类型 | 定义 |
| --- | --- |
| `NexusAgentOptions`, `AgentDefinition` | [options.py](src/nexus_agent_sdk/options.py) |
| `AssistantMessage`, `UserMessage`, `SystemMessage`, `ResultMessage` | [messages.py](src/nexus_agent_sdk/types/messages.py) |
| `TextBlock`, `ThinkingBlock`, `ToolUseBlock`, `ToolResultBlock` | [messages.py](src/nexus_agent_sdk/types/messages.py) |
| `PermissionResultAllow`, `PermissionResultDeny`, `HookMatcher` | [callbacks.py](src/nexus_agent_sdk/types/callbacks.py) |
| `InitializationResult`, `ContextUsageResponse`, `McpStatusResponse` | [control.py](src/nexus_agent_sdk/types/control.py) |

## 错误处理

| 异常 | 原因 |
| --- | --- |
| `NexusSDKError` | SDK 操作失败 |
| `ProcessError` | 运行时启动失败或异常退出 |
| `ProtocolError` | 运行时输出格式错误 |
| `ControlError` | 控制请求被拒绝 |
| `ResultError` | `receive_result()` 收到错误结果 |
| `BufferOverflowError` | 消息队列超限 |

[错误类型](src/nexus_agent_sdk/errors.py)

## 开发

```sh
uv sync --frozen --group dev
uv run python -m compileall -q examples
uv run ruff check .
uv run ruff format --check .
uv run mypy src/nexus_agent_sdk
uv build
```

源码开发需在 PATH 中配置 nxs，或设置 `cli_path`。

[构建与发布](docs/releasing.md) · [更新记录](CHANGELOG.md)

## 许可证

[Apache-2.0](LICENSE) · [第三方许可](THIRD_PARTY_NOTICES)
