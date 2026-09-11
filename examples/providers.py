"""选择 Anthropic Messages、OpenAI Chat Completions 或 Responses。"""

import argparse
import asyncio
import os

from nexus_agent_sdk import (
    AnthropicProvider,
    NexusAgentOptions,
    NexusSDKClient,
    OpenAIProvider,
)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "provider", choices=["anthropic", "chat_completions", "responses"]
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--prompt", default="用一句话介绍你自己")
    args = parser.parse_args()
    if args.provider == "anthropic":
        provider = AnthropicProvider(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            base_url=args.base_url or os.environ.get("ANTHROPIC_BASE_URL"),
        )
    else:
        provider = OpenAIProvider(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=args.base_url or os.environ.get("OPENAI_BASE_URL"),
            protocol=args.provider,
        )
    options = NexusAgentOptions(
        provider=provider, model=args.model, tools=[], max_turns=1
    )
    async with NexusSDKClient(options) as client:
        await client.query(args.prompt)
        print((await client.receive_result()).result)


if __name__ == "__main__":
    asyncio.run(main())
