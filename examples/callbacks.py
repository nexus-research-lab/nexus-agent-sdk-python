"""MCP 工具、权限回调与 PreToolUse Hook。"""

import asyncio

from nexus_agent_sdk import (
    HookMatcher,
    NexusAgentOptions,
    NexusSDKClient,
    PermissionResultDeny,
    create_sdk_mcp_server,
    tool,
)


@tool(
    "greet",
    "向指定名字问好",
    {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
)
async def greet(arguments):
    return {"content": [{"type": "text", "text": f"你好，{arguments['name']}"}]}


async def deny_unapproved(name, input_data, context):
    return PermissionResultDeny(f"示例仅授权 greet 工具，拒绝 {name}")


async def observe(input_data, tool_use_id, context):
    print("准备调用", input_data.get("tool_name"))
    return {}


async def main():
    options = NexusAgentOptions(
        mcp_servers={"local": create_sdk_mcp_server(name="local", tools=[greet])},
        allowed_tools=["mcp__local__greet"],
        can_use_tool=deny_unapproved,
        hooks={"PreToolUse": [HookMatcher(hooks=[observe])]},
        max_turns=3,
    )
    async with NexusSDKClient(options) as client:
        await client.query("调用 greet 工具向 Alice 问好")
        async for message in client.receive_response():
            print(message)


if __name__ == "__main__":
    asyncio.run(main())
