"""查询与文本输出。"""

import asyncio

from nexus_agent_sdk import (
    AssistantMessage,
    NexusAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)


async def main():
    options = NexusAgentOptions(tools=[], max_turns=1, persist_session=False)
    async for message in query(prompt="用一句话介绍你自己", options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
        if isinstance(message, ResultMessage) and message.is_error:
            raise RuntimeError(message.errors or message.result)


if __name__ == "__main__":
    asyncio.run(main())
