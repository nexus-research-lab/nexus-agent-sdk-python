"""异步会话、流式输入和 nxs 宿主控制；传输资源由 ProcessTransport 管理。"""

import asyncio
import copy
import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import suppress
from typing import cast

from ._internal.configuration import RuntimeConfiguration
from ._internal.transport import ProcessTransport
from .errors import (
    BufferOverflowError,
    ControlError,
    NexusSDKError,
    ProcessError,
    ProtocolError,
    ResultError,
)
from .mcp import SdkMcpServer
from .options import NexusAgentOptions
from .types import (
    ElicitationRequest,
    ElicitationResult,
    HookContext,
    JsonObject,
    Message,
    OutboundMessage,
    PermissionMode,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    ToolPermissionContext,
    UserDialogRequest,
    parse_message,
)
from .types.control import (
    AccountInfo,
    AgentInfo,
    AutoDreamResult,
    ContextUsageResponse,
    InitializationResult,
    McpSetServersResult,
    McpStatusResponse,
    ModelInfo,
    RewindFilesResult,
    SettingsResponse,
    SlashCommand,
    TaskMessageResult,
)
from .types.messages import _content, _project

_END = object()
_STREAM_END = object()
Prompt = str | list[JsonObject] | OutboundMessage | JsonObject


class NexusSDKClient:
    """每个实例持有独立会话，流式输入串行提交、输出由单一消费者读取。"""

    def __init__(self, options: NexusAgentOptions | None = None):
        self.options = options or NexusAgentOptions()
        self.initialization_result: InitializationResult = {}
        self._transport = ProcessTransport(self.options)
        self._reader: asyncio.Task | None = None
        self._input_task: asyncio.Task | None = None
        self._close_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._callbacks: dict[str, asyncio.Task] = {}
        self._cancelled: dict[str, asyncio.Event] = {}
        self._configuration = RuntimeConfiguration(self.options)
        self._mcp_servers = dict(self.options.mcp_servers)
        self._mcp_lock = asyncio.Lock()
        self._messages: asyncio.Queue = asyncio.Queue()
        self._queued_bytes = 0
        self._receiving = False
        self._active_turn = False
        self._stream_active = False
        self._turn_done = asyncio.Event()
        self._turn_done.set()
        self._closed = False
        self._connecting = False
        self._failure: Exception | None = None
        self._next_context: str | None = None
        self.tasks: dict[str, Message] = {}

    @property
    def is_connected(self) -> bool:
        process = self._transport.process
        return process is not None and process.returncode is None and not self._closed

    @property
    def session_id(self) -> str:
        return self.initialization_result.get("session_id", "")

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset(self.initialization_result.get("protocol_capabilities", []))

    async def __aenter__(self) -> "NexusSDKClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.disconnect()

    async def connect(
        self, prompt: Prompt | AsyncIterable[Prompt] | None = None
    ) -> None:
        """完成握手后才提交输入，初始化失败或取消会关闭子进程。"""
        if self._closed or self._connecting or self._transport.process is not None:
            raise NexusSDKError("Create a fresh client for a new connection")
        self.options.validate()
        self._connecting = True
        try:
            await self._transport.start(self._configuration.command())
            self._reader = asyncio.create_task(self._read_messages())
            response = await self.control(self._configuration.initialize_request())
            self.initialization_result = cast(InitializationResult, response)
            if self.options.permission_mode == "auto":
                self._require_capability("auto_review_v1")
            if prompt is not None:
                await self.query(prompt)
        except BaseException:
            await self.disconnect()
            raise
        finally:
            self._connecting = False

    def _require_capability(self, capability: str) -> None:
        if capability not in self.capabilities:
            raise ControlError(f"Unsupported capability: {capability}")

    async def _write(self, message: JsonObject) -> None:
        if self._failure is not None:
            raise self._failure
        if not self.is_connected:
            raise NexusSDKError("Client is not connected")
        await self._transport.write(message)

    async def control(
        self,
        request: JsonObject,
        *,
        capability: str | None = None,
        timeout: float | None = -1,
    ) -> JsonObject:
        """None 表示等待至完成；-1 使用默认超时；取消传播原 request ID。"""
        if capability is not None:
            self._require_capability(capability)
        if not isinstance(request.get("subtype"), str):
            raise ValueError("Control request requires subtype")
        if timeout is not None and timeout != -1 and timeout <= 0:
            raise ValueError("timeout must be positive or None")
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            async with asyncio.timeout(
                self.options.control_timeout if timeout == -1 else timeout
            ):
                await self._write(
                    {
                        "type": "control_request",
                        "request_id": request_id,
                        "request": request,
                    }
                )
                return await future
        except (asyncio.CancelledError, TimeoutError):
            with suppress(Exception):
                async with asyncio.timeout(self.options.shutdown_timeout):
                    await self._write(
                        {"type": "control_cancel_request", "request_id": request_id}
                    )
            raise
        finally:
            self._pending.pop(request_id, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()

    async def query(
        self, prompt: Prompt | AsyncIterable[Prompt], *, session_id: str | None = None
    ) -> None:
        """文本提交一轮；异步可迭代输入由后台生产者逐轮提交。"""
        if not self.is_connected:
            raise NexusSDKError("Client is not connected")
        if self._active_turn or self._stream_active:
            raise NexusSDKError("A query is already in progress")
        if isinstance(prompt, AsyncIterable):
            self._stream_active = True
            self._input_task = asyncio.create_task(self._feed(prompt, session_id))
        else:
            await self._send(prompt, session_id)

    async def _send(self, prompt: Prompt, session_id: str | None) -> None:
        if isinstance(prompt, OutboundMessage):
            message = prompt.to_wire()
        elif isinstance(prompt, dict):
            message = copy.deepcopy(prompt)
        elif isinstance(prompt, (str, list)):
            message = OutboundMessage(prompt).to_wire()
        else:
            raise TypeError("Expected text, content blocks, or a user message")
        body = message.get("message")
        if (
            message.get("type") != "user"
            or not isinstance(body, dict)
            or body.get("role") != "user"
            or not isinstance(body.get("content"), (str, list))
        ):
            raise ValueError("Input must be a user message envelope")
        _content(body["content"])
        if message.get("tool_access") not in (None, "", "inherit", "none"):
            raise ValueError("Invalid tool_access")
        budget = message.get("max_output_tokens")
        if budget is not None and (not isinstance(budget, int) or budget <= 0):
            raise ValueError("max_output_tokens must be a positive integer")
        if (
            message.get("tool_access") == "none"
            or budget is not None
            or message.get("skip_auto_memory")
        ):
            self._require_capability("message_execution_policy_v1")
        if session_id is not None:
            message["session_id"] = session_id
        if self._next_context:
            message["nexus_internal_context"] = self._next_context
        self._active_turn = True
        self._turn_done.clear()
        try:
            await self._write(message)
            self._next_context = None
        except BaseException:
            self._active_turn = False
            self._turn_done.set()
            raise

    async def _feed(
        self, source: AsyncIterable[Prompt], session_id: str | None
    ) -> None:
        """等待运行时 result 而非消费者进度，避免输入输出互相等待。"""
        try:
            iterator = aiter(source)
            try:
                async for prompt in iterator:
                    await self._send(prompt, session_id)
                    await self._turn_done.wait()
                    if self._failure:
                        raise self._failure
            finally:
                close = getattr(iterator, "aclose", None)
                if close:
                    await close()
            self._messages.put_nowait((_STREAM_END, 0))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._begin_close(exc)

    async def receive_messages(self) -> AsyncGenerator[Message, None]:
        """持续读取到流式输入结束或进程退出，禁止竞争消费同一队列。"""
        if self._transport.process is None:
            raise NexusSDKError("Client is not connected")
        if self._receiving:
            raise NexusSDKError("Only one message consumer is supported")
        self._receiving = True
        try:
            while True:
                if self._messages.empty() and self._closed:
                    if self._failure:
                        raise self._failure
                    return
                message, size = await self._messages.get()
                self._queued_bytes -= size
                if isinstance(message, Exception):
                    raise message
                if message is _STREAM_END:
                    self._stream_active = False
                    return
                if message is _END:
                    return
                yield message
        finally:
            self._receiving = False

    async def receive_response(self) -> AsyncGenerator[Message, None]:
        """到下一条 result 为止；提前 EOF 是错误，不伪造成功结果。"""
        stream = self.receive_messages()
        try:
            async for message in stream:
                yield message
                if isinstance(message, ResultMessage):
                    return
            raise ProcessError(
                "Stream ended before result", stderr=self._transport.stderr
            )
        finally:
            await stream.aclose()

    async def receive_result(self, *, raise_on_error: bool = True) -> ResultMessage:
        """读取最终结果，默认把 is_error 转为保留完整结果的 ResultError。"""
        stream = self.receive_response()
        try:
            async for message in stream:
                if isinstance(message, ResultMessage):
                    if raise_on_error and message.is_error:
                        raise ResultError(message)
                    return message
        finally:
            await stream.aclose()
        raise ProcessError("No result")

    async def _read_messages(self) -> None:
        try:
            async for raw, size in self._transport.messages():
                self._dispatch(raw, size)
            if self._active_turn or self._pending:
                assert self._transport.process is not None
                raise ProcessError(
                    "nxs exited before completing pending work",
                    self._transport.process.returncode,
                    self._transport.stderr,
                )
            self._begin_close(None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._begin_close(
                exc if isinstance(exc, NexusSDKError) else ProtocolError(str(exc))
            )

    def _dispatch(self, raw: JsonObject, size: int = 0) -> None:
        kind = raw["type"]
        if kind == "control_response":
            response = raw["response"]
            future = self._pending.get(response["request_id"])
            if future is None or future.done():
                return
            if response["subtype"] == "error":
                future.set_exception(
                    ControlError(
                        response.get("error", "Control failed"), response["request_id"]
                    )
                )
            elif response["subtype"] == "success" and isinstance(
                response.get("response", {}), dict
            ):
                future.set_result(response.get("response", {}))
            else:
                raise ProtocolError("Invalid control response")
            return
        if kind == "control_request":
            request_id = raw["request_id"]
            if (
                not isinstance(request_id, str)
                or not request_id
                or request_id in self._callbacks
            ):
                raise ProtocolError("Invalid or duplicate callback request_id")
            self._cancelled[request_id] = asyncio.Event()
            task = asyncio.create_task(self._respond(raw))
            self._callbacks[request_id] = task
            task.add_done_callback(lambda done: self._forget_callback(request_id, done))
            return
        if kind == "control_cancel_request":
            request_id = raw["request_id"]
            if request_id in self._callbacks:
                self._cancelled[request_id].set()
                self._callbacks[request_id].cancel()
            return
        message = parse_message(raw)
        if message.session_id:
            self.initialization_result["session_id"] = message.session_id
        if isinstance(message, ResultMessage):
            self._active_turn = False
            self._turn_done.set()
        task_id = getattr(message, "task_id", "")
        if task_id:
            self.tasks[task_id] = message
        if self._queued_bytes + size > self.options.max_queue_bytes:
            raise BufferOverflowError(
                "Event queue exceeded max_queue_bytes; consume messages faster"
            )
        self._queued_bytes += size
        self._messages.put_nowait((message, size))

    def _forget_callback(self, request_id: str, task: asyncio.Task) -> None:
        """任务开始前即被取消时，也必须移除注册记录。"""
        if self._callbacks.get(request_id) is task:
            self._callbacks.pop(request_id, None)
            self._cancelled.pop(request_id, None)

    async def _callback(self, request: JsonObject, request_id: str) -> JsonObject:
        kind = request["subtype"]
        if kind == "can_use_tool":
            original = request["input"]
            decision: PermissionResultAllow | PermissionResultDeny = (
                PermissionResultDeny("No can_use_tool callback configured")
            )
            if self.options.can_use_tool:
                context = ToolPermissionContext(
                    request.get("tool_use_id"),
                    request.get("permission_suggestions") or [],
                    request,
                    self._cancelled[request_id],
                    request_id,
                )
                decision = await self.options.can_use_tool(
                    request["tool_name"], original, context
                )
            if not isinstance(decision, (PermissionResultAllow, PermissionResultDeny)):
                raise TypeError("Permission callback must return an explicit decision")
            return decision.to_wire(original)
        if kind == "hook_callback":
            hook_context: HookContext = {
                "request_id": request_id,
                "cancelled": self._cancelled[request_id],
            }
            return await self._configuration.hooks[request["callback_id"]](
                request["input"], request.get("tool_use_id"), hook_context
            )
        if kind == "mcp_message":
            server = self._mcp_servers[request["server_name"]]
            if not isinstance(server, SdkMcpServer):
                raise ControlError("Not an SDK MCP server")
            return {"mcp_response": await server.handle_message(request["message"])}
        if kind == "elicitation":
            result = ElicitationResult()
            if self.options.on_elicitation:
                result = await self.options.on_elicitation(
                    _project(ElicitationRequest, request)
                )
            return result.to_wire()
        if kind == "request_user_dialog":
            if not self.options.on_user_dialog:
                raise ControlError("No on_user_dialog callback configured")
            return await self.options.on_user_dialog(
                _project(UserDialogRequest, request)
            )
        if kind == "oauth_token_refresh":
            token = None
            if self.options.on_oauth_token_refresh:
                token = await self.options.on_oauth_token_refresh()
            if token is not None and not isinstance(token, str):
                raise TypeError("OAuth callback must return a token string or None")
            return {"accessToken": token}
        raise ControlError(f"Unsupported runtime callback: {kind}")

    async def _respond(self, raw: JsonObject) -> None:
        request_id = raw["request_id"]
        try:
            try:
                timeout = (
                    self._configuration.hook_timeouts.get(
                        raw["request"].get("callback_id")
                    )
                    or self.options.callback_timeout
                )
                async with asyncio.timeout(timeout):
                    result = await self._callback(raw["request"], request_id)
                if not isinstance(result, dict):
                    raise TypeError("Callback must return an object")
                json.dumps(result, allow_nan=False)
                response = {
                    "subtype": "success",
                    "request_id": request_id,
                    "response": result,
                }
            except Exception as exc:
                response = {
                    "subtype": "error",
                    "request_id": request_id,
                    "error": str(exc) or type(exc).__name__,
                }
            await self._write({"type": "control_response", "response": response})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._begin_close(exc)
        finally:
            self._callbacks.pop(request_id, None)
            self._cancelled.pop(request_id, None)

    def _begin_close(self, error: Exception | None) -> None:
        if self._close_task is not None:
            return
        self._closed = True
        self._failure = error
        self._turn_done.set()
        self._messages.put_nowait((error or _END, 0))
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error or ProcessError("nxs disconnected"))
        self._close_task = asyncio.create_task(self._close())

    async def _close(self) -> None:
        tasks = [self._reader, self._input_task, *self._callbacks.values()]
        for event in self._cancelled.values():
            event.set()
        for task in tasks:
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in tasks if task is not None), return_exceptions=True
        )
        await self._transport.close()

    async def disconnect(self) -> None:
        """可重入且受 shield 保护，取消调用方仍等待进程回收完成。"""
        self._begin_close(NexusSDKError("Client disconnected"))
        assert self._close_task is not None
        try:
            await asyncio.shield(self._close_task)
        except asyncio.CancelledError:
            await asyncio.shield(self._close_task)
            raise

    async def interrupt(self, reason: str = "") -> None:
        """中断当前轮次，继续通过消息流接收终态。"""
        await self.control({"subtype": "interrupt", "reason": reason})

    async def set_model(self, model: str) -> None:
        await self.control({"subtype": "set_model", "model": model})
        self.options.model = model

    async def set_permission_mode(self, mode: PermissionMode) -> None:
        candidate = copy.copy(self.options)
        candidate.permission_mode = mode
        candidate.validate()
        await self.control(
            {"subtype": "set_permission_mode", "mode": mode},
            capability="auto_review_v1" if mode == "auto" else None,
        )
        self.options.permission_mode = mode

    async def set_max_thinking_tokens(self, tokens: int) -> None:
        if tokens < 0:
            raise ValueError("Thinking budget cannot be negative")
        await self.control(
            {"subtype": "set_max_thinking_tokens", "max_thinking_tokens": tokens}
        )
        self.options.max_thinking_tokens = tokens

    async def update_environment(self, variables: dict[str, str]) -> None:
        await self.control(
            {"subtype": "update_environment_variables", "variables": variables}
        )
        self.options.env.update(variables)

    async def get_context_usage(self) -> ContextUsageResponse:
        return cast(
            ContextUsageResponse, await self.control({"subtype": "get_context_usage"})
        )

    async def get_settings(self) -> SettingsResponse:
        return cast(SettingsResponse, await self.control({"subtype": "get_settings"}))

    async def apply_flag_settings(self, settings: JsonObject) -> None:
        await self.control({"subtype": "apply_flag_settings", "settings": settings})

    async def rewind_files(
        self, user_message_id: str, *, dry_run: bool = False
    ) -> RewindFilesResult:
        self._require_text(user_message_id, "user_message_id")
        return cast(
            RewindFilesResult,
            await self.control(
                {
                    "subtype": "rewind_files",
                    "user_message_id": user_message_id,
                    "dry_run": dry_run,
                }
            ),
        )

    async def seed_read_state(self, path: str, mtime: int) -> None:
        self._require_text(path, "path")
        await self.control({"subtype": "seed_read_state", "path": path, "mtime": mtime})

    async def remove_messages(self, message_uuids: list[str]) -> None:
        if not message_uuids or any(not value.strip() for value in message_uuids):
            raise ValueError("At least one non-empty message UUID is required")
        await self.control(
            {
                "subtype": "remove_messages",
                "message_uuids": list(dict.fromkeys(message_uuids)),
            }
        )

    async def stop_task(self, task_id: str) -> None:
        self._require_text(task_id, "task_id")
        await self.control({"subtype": "stop_task", "task_id": task_id})

    async def send_task_message(
        self, task_id: str, message: str, summary: str = ""
    ) -> TaskMessageResult:
        self._require_text(task_id, "task_id")
        self._require_text(message, "message")
        return cast(
            TaskMessageResult,
            await self.control(
                {
                    "subtype": "send_task_message",
                    "task_id": task_id,
                    "payload": {"message": message, "summary": summary},
                }
            ),
        )

    async def run_auto_dream(self) -> AutoDreamResult:
        """长时控制不套用握手超时，调用方可通过 asyncio.timeout 自行约束。"""
        return cast(
            AutoDreamResult,
            await self.control({"subtype": "run_auto_dream"}, timeout=None),
        )

    async def control_subagent(
        self, tool_use_id: str, operation: str, input: JsonObject | None = None
    ) -> JsonObject:
        """调用方必须使用当前活跃 MCP 的 identity；执行资格由 nxs 校验。"""
        self._require_text(tool_use_id, "tool_use_id")
        if operation not in {"spawn", "list", "get", "wait", "send", "stop"}:
            raise ValueError("Invalid subagent operation")
        return await self.control(
            {
                "subtype": "subagent_control",
                "tool_use_id": tool_use_id,
                "operation": operation,
                "input": input or {},
            },
            capability="subagent_control_v1",
            timeout=None,
        )

    def get_server_info(self) -> InitializationResult:
        return copy.deepcopy(self.initialization_result)

    def supported_commands(self) -> list[SlashCommand]:
        return copy.deepcopy(self.initialization_result.get("commands", []))

    def supported_models(self) -> list[ModelInfo]:
        return copy.deepcopy(self.initialization_result.get("models", []))

    def supported_agents(self) -> list[AgentInfo]:
        return copy.deepcopy(self.initialization_result.get("agents", []))

    def account_info(self) -> AccountInfo:
        return copy.deepcopy(self.initialization_result.get("account", {}))

    def set_next_turn_context(self, context: str) -> None:
        """隐藏宿主上下文仅绑定下一次成功发送，不写入用户 transcript。"""
        self._next_context = context or None

    def clear_next_turn_context(self) -> None:
        self._next_context = None

    async def get_mcp_status(self) -> McpStatusResponse:
        return cast(McpStatusResponse, await self.control({"subtype": "mcp_status"}))

    async def set_mcp_servers(
        self, servers: dict[str, SdkMcpServer | JsonObject]
    ) -> McpSetServersResult:
        """握手期间先暴露新 SDK 回调，按运行时部分成功结果更新本地注册表。"""
        async with self._mcp_lock:
            previous = self._mcp_servers
            proposed = dict(servers)
            self._mcp_servers = {**previous, **proposed}
            serialized = {
                name: {"type": "sdk", "name": value.name}
                if isinstance(value, SdkMcpServer)
                else value
                for name, value in proposed.items()
            }
            try:
                result = cast(
                    McpSetServersResult,
                    await self.control(
                        {"subtype": "mcp_set_servers", "servers": serialized}
                    ),
                )
            except ControlError:
                self._mcp_servers = previous
                raise
            except BaseException:
                # 超时无法判断 runtime 是否已应用；关闭会话，避免两端注册表分裂。
                await self.disconnect()
                raise
            for name in result.get("errors", {}):
                if name in previous:
                    proposed[name] = previous[name]
                else:
                    proposed.pop(name, None)
            self._mcp_servers = proposed
            self.options.mcp_servers = dict(proposed)
            return result

    async def authenticate_mcp(self, server_name: str) -> JsonObject:
        return await self.control(
            {"subtype": "mcp_authenticate", "serverName": server_name}
        )

    async def clear_mcp_auth(self, server_name: str) -> JsonObject:
        return await self.control(
            {"subtype": "mcp_clear_auth", "serverName": server_name}
        )

    async def submit_mcp_oauth_callback(
        self, server_name: str, callback_url: str
    ) -> JsonObject:
        return await self.control(
            {
                "subtype": "mcp_oauth_callback_url",
                "serverName": server_name,
                "callbackUrl": callback_url,
            }
        )

    async def reconnect_mcp(self, server_name: str) -> None:
        await self.control({"subtype": "mcp_reconnect", "serverName": server_name})

    async def set_mcp_enabled(self, server_name: str, enabled: bool) -> None:
        await self.control(
            {"subtype": "mcp_toggle", "serverName": server_name, "enabled": enabled}
        )

    @staticmethod
    def _require_text(value: str, name: str) -> None:
        if not value.strip():
            raise ValueError(f"{name} cannot be empty")


async def query(
    *, prompt: Prompt | AsyncIterable[Prompt], options: NexusAgentOptions | None = None
) -> AsyncGenerator[Message, None]:
    """单次文本到 result；异步输入迭代到全部输入的结果，关闭或取消均释放进程。"""
    async with NexusSDKClient(options) as client:
        await client.query(prompt)
        stream = (
            client.receive_messages()
            if isinstance(prompt, AsyncIterable)
            else client.receive_response()
        )
        try:
            async for message in stream:
                yield message
        finally:
            await stream.aclose()
