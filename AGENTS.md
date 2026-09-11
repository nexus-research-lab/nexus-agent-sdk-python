# nexus-agent-sdk-python

公开 Python SDK，通过 stdio stream-json 启动 nxs，不实现 agent loop，不依赖 Go 源码。
协议真相源为相邻 nexus-agent-sdk-bridge/protocol 与 nxs 实际行为。

- `src/nexus_agent_sdk/client.py`：会话、异步输入生产者、control 分发、宿主回调和公开控制方法。
- `src/nexus_agent_sdk/_internal/transport.py`：子进程、字节流、stderr 和取消安全的回收。
- `src/nexus_agent_sdk/_internal/configuration.py`：CLI 参数、initialize 请求和 hook ID 注册。
- `src/nexus_agent_sdk/errors.py`：通信错误与结果错误。
- `src/nexus_agent_sdk/types/control.py`：原生 wire 字段的控制响应 TypedDict。
- `src/nexus_agent_sdk/sessions.py`：transcript 检索和追加标题、标签元数据。
- `src/nexus_agent_sdk/provider.py`：Anthropic/OpenAI 配置与 nxs 环境变量映射；凭据不进入 CLI。
- `src/nexus_agent_sdk/options.py`：启动选项与输入校验。
- `src/nexus_agent_sdk/types/messages.py`：消息、内容块、出站消息及 wire 投影；保留原始字段。
- `src/nexus_agent_sdk/types/callbacks.py`：权限、hook、elicitation、对话和 OAuth 回调契约。
- `src/nexus_agent_sdk/types/common.py`：共享 JSON 与权限模式类型。
- `src/nexus_agent_sdk/types/__init__.py`：公开类型导出；包根继续提供统一公开 API。
- `src/nexus_agent_sdk/mcp.py`：进程内 MCP 工具及 schema 校验。
- `tests/`：本地协议与模型服务集成验证；Git 忽略，不进入发行包。
- `examples/`：查询、多轮、Provider、MCP/Hook、流式输入、会话与结构化输出；入口见 examples/README.md。
- `docs/api-reference.md`：Python API 的用途、参数和使用约束。
- `.github/workflows/ci.yml`：Linux、macOS、Windows 的 Python 3.11/3.13 测试矩阵。
- `.github/workflows/build-wheels.yml`：六平台内置运行时构建、安装后测试与 Linux 基线验证。
- `.github/workflows/publish.yml`：tag 检查、PyPI 上传和 GitHub Release。
- `hatch_build.py`、`runtime-lock.json`：只在正式 wheel 构建时下载并校验固定运行时。
- `src/nexus_agent_sdk/_internal/runtime.py`：显式路径、内置运行时、开发环境 PATH 的选择。
- `scripts/`：已安装 wheel 集成验证与发布前检查。
- `docs/releasing.md`：发布配置、平台下限与运行时升级流程。
- `THIRD_PARTY_NOTICES`：随内置 rg 分发的许可说明。

注释中文，使用 Google Python 命名和文档风格。优先标准库，不引入重复传输抽象。
保留协议原生 mixed-casing，未知消息不得静默丢弃。权限回调缺失时拒绝。
新增可选协议能力先明确 capability 与完整处理语义，再加入 initialize 协商。
用户可见变化同步更新 CHANGELOG.md、README.md 与 README.zh-CN.md。
修改文件结构同步本文件。提交使用 emoji 前缀和英文摘要。

验证：`python -m unittest discover -s tests -v`、`uvx ruff check .`、
`uvx ruff format --check .`、`uv build`。真实运行时测试设置 `NXS_TEST_BINARY`。

单条消息执行限制、hook applied ACK、auto review 和子智能体控制分别按协商能力开放。
流式输入必须消费 receive_messages 到结束；不能在流尚未消费结束时插入新 query。
回调必须传播取消；不能持有共享锁等待另一个控制请求。动态 MCP 更新超时后关闭会话，
避免无法判断 runtime 是否已应用造成注册表分裂。
开发环境使用 `uv sync --group dev`，随后用 `uv run` 执行测试、ruff、mypy。

依赖方向：客户端使用 `_internal`、选项和类型；`_internal` 不反向导入客户端。
`types` 只依赖标准库和同包类型，不导入客户端、MCP 实现或启动选项。
会话生命周期、控制请求与回调任务的取消由客户端统一管理，不用 mixin 拆散状态所有权。

发布产物必须包含 nxs 与 rg；不得退化成 py3-none-any wheel。运行时不动态下载。
`_bundled/` 由构建 hook 注入 wheel，不写入源码树。版本、平台、摘要以锁文件为准。

CI 不依赖本地 `tests/`。wheel 检查包含运行时版本和握手；本地存在测试目录时追加测试。
