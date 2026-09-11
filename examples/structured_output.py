"""使用 JSON Schema 获取结构化结果。"""

import asyncio
import json

from nexus_agent_sdk import NexusAgentOptions, NexusSDKClient


async def main():
    options = NexusAgentOptions(
        tools=[],
        max_turns=3,
        output_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "language": {"type": "string"},
            },
            "required": ["name", "language"],
            "additionalProperties": False,
        },
    )
    async with NexusSDKClient(options) as client:
        await client.query("项目名称是 Nexus，开发语言是 Python。提取名称与语言。")
        result = await client.receive_result()
        print(json.dumps(result.structured_output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
