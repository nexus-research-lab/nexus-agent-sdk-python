"""进程内 MCP 工具及活跃调用 identity；不另起监听服务器。"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from jsonschema.validators import validator_for
from referencing import Registry

from .types import JsonObject


@dataclass(frozen=True)
class McpToolContext:
    metadata: JsonObject

    @property
    def tool_use_id(self) -> str:
        """原生 nxs 的当前父调用身份，不根据工具名猜测。"""
        value = self.metadata.get("claudecode/toolUseId", "")
        return value if isinstance(value, str) else ""


_tool_context: ContextVar[McpToolContext] = ContextVar("nexus_mcp_tool_context")


def get_tool_context() -> McpToolContext:
    """只能在 SDK 工具处理函数中读取，任务间由 contextvars 隔离。"""
    return _tool_context.get()


@dataclass
class SdkMcpTool:
    name: str
    description: str
    input_schema: JsonObject
    handler: Callable[[JsonObject], Awaitable[JsonObject]]
    annotations: JsonObject | None = None
    output_schema: JsonObject | None = None
    meta: JsonObject | None = None
    _validator: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.name.strip() or not callable(self.handler):
            raise ValueError("Tool requires a name and callable handler")
        validator = validator_for(self.input_schema)
        validator.check_schema(self.input_schema)
        self._validator = validator(self.input_schema, registry=Registry())
        if self.output_schema is not None:
            validator_for(self.output_schema).check_schema(self.output_schema)

    def to_wire(self) -> JsonObject:
        result: JsonObject = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        for key, value in {
            "annotations": self.annotations,
            "outputSchema": self.output_schema,
            "_meta": self.meta,
        }.items():
            if value is not None:
                result[key] = value
        return result


def tool(
    name: str,
    description: str,
    input_schema: JsonObject,
    *,
    annotations: JsonObject | None = None,
    output_schema: JsonObject | None = None,
    meta: JsonObject | None = None,
) -> Callable[[Callable[[JsonObject], Awaitable[JsonObject]]], SdkMcpTool]:
    """支持完整 JSON Schema 或 Claude SDK 风格的基础 Python 类型字典。"""
    schema = input_schema
    if all(isinstance(value, type) for value in input_schema.values()):
        primitives = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            dict: "object",
            list: "array",
        }
        if any(value not in primitives for value in input_schema.values()):
            raise ValueError("Use JSON Schema for non-primitive types")
        schema = {
            "type": "object",
            "properties": {
                key: {"type": primitives[value]} for key, value in input_schema.items()
            },
            "required": list(input_schema),
            "additionalProperties": False,
        }

    def decorate(handler: Callable[[JsonObject], Awaitable[JsonObject]]) -> SdkMcpTool:
        return SdkMcpTool(
            name, description, schema, handler, annotations, output_schema, meta
        )

    return decorate


class SdkMcpServer:
    """独立工具表，支持 JSON-RPC 协商和工具调用。"""

    def __init__(self, name: str, tools: list[SdkMcpTool], version: str = "1.0.0"):
        if not name.strip():
            raise ValueError("MCP server requires a name")
        self.name = name
        self.version = version
        self.tools = {item.name: item for item in tools}
        if len(self.tools) != len(tools):
            raise ValueError("Duplicate MCP tool name")

    async def handle_message(self, message: JsonObject) -> JsonObject:
        """通知不回包；非法方法与参数按 JSON-RPC 返回，执行失败用 isError。"""
        response: JsonObject = {"jsonrpc": "2.0", "id": message.get("id")}
        if message.get("jsonrpc") != "2.0" or not isinstance(
            message.get("method"), str
        ):
            return {**response, "error": {"code": -32600, "message": "Invalid Request"}}
        if "id" not in message:
            return {}
        params = message.get("params", {})
        if not isinstance(params, dict):
            return {**response, "error": {"code": -32602, "message": "Invalid params"}}
        method = message["method"]
        result: JsonObject
        if method == "initialize":
            supported = {"2024-11-05", "2025-03-26", "2025-06-18"}
            requested = params.get("protocolVersion")
            result = {
                "protocolVersion": requested
                if requested in supported
                else "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": self.name, "version": self.version},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [item.to_wire() for item in self.tools.values()]}
        elif method == "tools/call":
            selected = self.tools.get(params.get("name", ""))
            if selected is None:
                return {
                    **response,
                    "error": {"code": -32602, "message": "Unknown tool"},
                }
            result = await self._call(selected, params)
        else:
            return {
                **response,
                "error": {"code": -32601, "message": "Method not found"},
            }
        return {**response, "result": result}

    async def _call(self, selected: SdkMcpTool, params: JsonObject) -> JsonObject:
        metadata = params.get("_meta", {})
        if not isinstance(metadata, dict):
            return {
                "isError": True,
                "content": [{"type": "text", "text": "Invalid _meta"}],
            }
        token = _tool_context.set(McpToolContext(metadata))
        try:
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise TypeError("Tool arguments must be an object")
            selected._validator.validate(arguments)
            result = await selected.handler(arguments)
            if not isinstance(result, dict) or not isinstance(
                result.get("content"), list
            ):
                raise TypeError("Tool must return an MCP result with content list")
            if selected.output_schema is not None and not result.get("isError"):
                validator = validator_for(selected.output_schema)
                validator(selected.output_schema, registry=Registry()).validate(
                    result.get("structuredContent")
                )
            return result
        except Exception as exc:
            return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
        finally:
            _tool_context.reset(token)


def create_sdk_mcp_server(
    *, name: str, tools: list[SdkMcpTool], version: str = "1.0.0"
) -> SdkMcpServer:
    return SdkMcpServer(name, tools, version)
