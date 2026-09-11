# Python API

## Query

`query(*, prompt, options=None)` returns an async iterator of messages.

```python
import asyncio

from nexus_agent_sdk import query


async def main():
    async for message in query(prompt="Describe this project"):
        print(message)


asyncio.run(main())
```

Prompts accept text, content block lists, `OutboundMessage`, or an async iterable.
Use `contextlib.aclosing()` when breaking out of a query iterator before completion.

## NexusSDKClient

| Method | Usage |
| --- | --- |
| `connect(prompt=None)` | Open a session |
| `query(prompt, session_id=None)` | Submit input |
| `receive_response()` | Read messages through the next result |
| `receive_result(raise_on_error=True)` | Return a result; raise `ResultError` on failure |
| `receive_messages()` | Read the message stream |
| `interrupt(reason="")` | Interrupt the current turn |
| `disconnect()` | Close the session |

Use `async with NexusSDKClient(options) as client` to manage the connection.
One consumer reads a client's output. Consume async iterable input through
`receive_messages()` before submitting another query.

### Configuration

| Method | Usage |
| --- | --- |
| `set_model(model)` | Change the model |
| `set_permission_mode(mode)` | Change the permission policy |
| `set_max_thinking_tokens(tokens)` | Set the thinking token budget |
| `update_environment(variables)` | Update runtime environment variables |
| `get_context_usage()` | Get context token usage |
| `get_settings()` | Get effective settings |
| `apply_flag_settings(settings)` | Apply settings |
| `set_next_turn_context(context)` | Attach host context to the next input |
| `clear_next_turn_context()` | Clear pending host context |

### Files and Tasks

| Method | Usage |
| --- | --- |
| `rewind_files(user_message_id, dry_run=False)` | Restore files to a checkpoint; `dry_run=True` previews changes |
| `seed_read_state(path, mtime)` | Register a file read and its modification time |
| `remove_messages(message_uuids)` | Remove messages from the conversation |
| `stop_task(task_id)` | Stop a background task |
| `send_task_message(task_id, message, summary="")` | Send a message to a task |
| `run_auto_dream()` | Run memory maintenance |
| `control_subagent(tool_use_id, operation, input=None)` | Spawn, list, get, wait for, message or stop subagents |

`control_subagent()` requires an active MCP tool call. Obtain its ID with
`get_tool_context().tool_use_id`. Use `asyncio.timeout()` to limit waits for
`run_auto_dream()` and `control_subagent()`.

### MCP

| Method | Usage |
| --- | --- |
| `get_mcp_status()` | Get server status |
| `set_mcp_servers(servers)` | Replace the server configuration |
| `authenticate_mcp(server_name)` | Start server authentication |
| `clear_mcp_auth(server_name)` | Clear server credentials |
| `submit_mcp_oauth_callback(server_name, callback_url)` | Complete an OAuth callback |
| `reconnect_mcp(server_name)` | Reconnect a server |
| `set_mcp_enabled(server_name, enabled)` | Enable or disable a server |

### Session Information

| Member | Value |
| --- | --- |
| `session_id` | Session ID |
| `is_connected` | Connection state |
| `tasks` | Background task states by ID |
| `get_server_info()` | Session initialization information |
| `supported_commands()` | Available commands |
| `supported_models()` | Available models |
| `supported_agents()` | Available agents |
| `account_info()` | Account information |

## Providers

`NexusAgentOptions(provider=...)` accepts `AnthropicProvider` or `OpenAIProvider`.

| Provider | Configuration |
| --- | --- |
| `AnthropicProvider` | `api_key` or `auth_token`, `base_url`, `version`, `headers`, `tool_discovery_transport` |
| `OpenAIProvider` | `api_key`, `base_url`, `protocol`, `org_id`, `project_id`, `headers` |

OpenAI protocols: `chat_completions`, `responses`.
Provider fields override matching `options.env` entries. Unset fields inherit
environment configuration. Nonempty `headers` replace inherited headers.
Set the model and fallback with `NexusAgentOptions.model` and `fallback_model`.

[Provider example](../examples/providers.py)

## Callbacks

| Option | Return value |
| --- | --- |
| `can_use_tool(name, input, context)` | `PermissionResultAllow` or `PermissionResultDeny` |
| `hooks` | `HookMatcher` registrations |
| `on_elicitation(request)` | `ElicitationResult` |
| `on_user_dialog(request)` | Response dictionary |
| `on_oauth_token_refresh()` | Token string or `None` |

Callbacks are async functions. Set `callback_timeout` on `NexusAgentOptions`,
or `timeout` on a `HookMatcher`. Propagate `asyncio.CancelledError`.

[Callback example](../examples/callbacks.py)

## SessionStore

| Method | Usage |
| --- | --- |
| `list_sessions()` | List saved sessions |
| `get_session_info(session_id)` | Get session metadata |
| `get_session_messages(session_id, limit=..., offset=...)` | Read session messages |
| `rename_session(session_id, title)` | Set a title |
| `tag_session(session_id, tag)` | Set a tag; `None` removes it |

`SessionStore(config_dir=None)` uses `NEXUS_CONFIG_DIR` or `~/.nexus`.

[Session example](../examples/sessions.py) · [Message and result types](../src/nexus_agent_sdk/types/messages.py)
