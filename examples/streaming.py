"""流式多轮输入与消息执行预算。"""

import asyncio

from nexus_agent_sdk import (
    NexusSDKClient,
    OutboundMessage,
    OutboundMessageOptions,
    ResultMessage,
)


async def prompts():
    yield "记住数字 7"
    yield OutboundMessage(
        "刚才的数字是什么？",
        OutboundMessageOptions(tool_access="none", max_output_tokens=100),
    )


async def main():
    async with NexusSDKClient() as client:
        await client.query(prompts())
        async for message in client.receive_messages():
            if isinstance(message, ResultMessage):
                print(message.result, message.errors)
        print("恢复会话时使用", client.session_id)
        print("上下文用量", await client.get_context_usage())


if __name__ == "__main__":
    asyncio.run(main())
