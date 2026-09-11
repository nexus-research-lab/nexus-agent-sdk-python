"""会话恢复、分叉与记录读取。"""

import asyncio
from dataclasses import replace

from nexus_agent_sdk import NexusAgentOptions, NexusSDKClient, SessionStore


async def main():
    options = NexusAgentOptions(tools=[], max_turns=2)
    async with NexusSDKClient(options) as client:
        await client.query("记住项目代号 Cedar")
        print((await client.receive_result()).result)
        session_id = client.session_id

    async with NexusSDKClient(replace(options, resume=session_id)) as client:
        await client.query("项目代号是什么？")
        print((await client.receive_result()).result)

    async with NexusSDKClient(
        replace(options, resume=session_id, fork_session=True)
    ) as client:
        await client.query("为这个项目写一句介绍")
        print((await client.receive_result()).result)
        print("fork_session_id:", client.session_id)

    store = SessionStore()
    store.rename_session(session_id, "Cedar")
    store.tag_session(session_id, "example")
    print(store.get_session_info(session_id))
    for message in store.get_session_messages(session_id, limit=10):
        print(message.type, message.message)


if __name__ == "__main__":
    asyncio.run(main())
