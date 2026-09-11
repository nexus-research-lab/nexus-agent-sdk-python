# 示例

```sh
pip install nexus-agent-sdk-python
export ANTHROPIC_API_KEY="your-api-key"
```

在仓库根目录运行。

| 示例 | 命令 |
| --- | --- |
| 查询与文本输出 | `python examples/quick_start.py` |
| 多轮会话与错误处理 | `python examples/conversation.py` |
| 流式输入与执行预算 | `python examples/streaming.py` |
| MCP 工具、权限与 Hook | `python examples/callbacks.py` |
| 会话恢复、分叉与记录 | `python examples/sessions.py` |
| JSON Schema 输出 | `python examples/structured_output.py` |

## Provider

```sh
python examples/providers.py anthropic --model claude-sonnet-4-6

export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="your-model"
python examples/providers.py chat_completions --model "$OPENAI_MODEL"
python examples/providers.py responses --model "$OPENAI_MODEL"
```

兼容服务通过 `--base-url` 配置。

```sh
python examples/providers.py responses \
  --model "$OPENAI_MODEL" \
  --base-url "https://api.example.com/v1" \
  --prompt "计算 12 加 30"
```

## 源码开发

```sh
uv sync --frozen --group dev
uv run python examples/quick_start.py
```

源码开发需在 PATH 中配置 nxs。模型和配置根可通过 `NEXUS_MODEL`、`NEXUS_CONFIG_DIR` 设置。
示例会发起模型请求。`sessions.py` 会创建会话、分叉和会话标签。
