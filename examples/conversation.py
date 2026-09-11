"""多轮会话与错误处理。"""

import asyncio

from nexus_agent_sdk import NexusAgentOptions, NexusSDKClient, ProcessError, ResultError


async def main():
    options = NexusAgentOptions(tools=[], max_turns=3)
    try:
        async with NexusSDKClient(options) as client:
            for prompt in ["记住数字 7", "把这个数字乘以 6"]:
                await client.query(prompt)
                result = await client.receive_result()
                print(result.result)
            print("session_id:", client.session_id)
            print("context:", await client.get_context_usage())
    except ResultError as error:
        print("查询失败:", error.result.errors or error.result.result)
        raise
    except ProcessError as error:
        print("运行时退出:", error.exit_code, error.stderr)
        raise


if __name__ == "__main__":
    asyncio.run(main())
