# 发布 Python SDK

## 发布产物

正式 wheel 内置 nxs 与配套 rg，安装和首次运行 wheel 都不下载运行时。
`runtime-lock.json` 固定 bridge 的版本化 Release URL 与每个平台归档的 SHA-256。
运行时升级需更新锁文件并通过 wheel 验证。
校验失败或平台无对应产物时构建失败，不生成缺少运行时的通用 wheel。

| 系统 | 架构 | wheel 平台标签 |
| --- | --- | --- |
| Linux，glibc 2.28+ | x86_64 / ARM64 | manylinux_2_28_x86_64 / manylinux_2_28_aarch64 |
| macOS 14+ | Intel / Apple Silicon | macosx_14_0_x86_64 / macosx_14_0_arm64 |
| Windows | x64 / ARM64 | win_amd64 / win_arm64 |

Python 标签是 `py3-none`，最低 Python 3.11。不宣称支持 musl/Alpine、32 位或旧版 macOS。
平台声明遵循 [PyPA wheel 标签规范](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/)，
构建使用 [Hatch build hook](https://hatch.pypa.io/latest/plugins/builder/wheel/#build-data)。

sdist 包含 Python 源码、构建 hook 与运行时锁文件，不含 Go 源码和所有平台二进制。
从 sdist 构建 wheel 时需要联网下载锁定平台产物；推荐用户直接安装匹配平台的 wheel。
editable 安装不下载 nxs，开发者使用 PATH 或显式 `cli_path`。

## CI

- `ci.yml`：Python 3.11/3.13 的跨系统源码检查，并调用 wheel 构建流程。
- `build-wheels.yml`：六个平台原生 runner 从 sdist 构建 wheel，在独立环境安装后检查运行时启动与握手。
  验证通过默认路径启动内置 nxs，并执行 rg 版本检查。
  Linux 额外在 manylinux_2_28 容器中执行同一验证，检查声明的 glibc 下限。
- `publish.yml`：推送 `v*` tag 或手动传入已有 `tag_name` 触发。
  核对 tag、pyproject 版本、`__version__` 和版本 CHANGELOG，锁定 commit 后构建。
  所有平台成功后检查六个 wheel 与一个 sdist，经 twine 检查后上传 PyPI，再创建 GitHub Release。

发布使用仓库 Secret `PYPI_API_TOKEN`。
普通 push/PR 只构建，不接触发布令牌。手动重跑同一 tag 会跳过 PyPI 已存在的文件，
但不能覆盖 PyPI 文件；修复已发布内容应提升版本重新发布。

## 发布步骤

1. 在仓库 Actions Secrets 中配置 `PYPI_API_TOKEN`。
2. 同步 `pyproject.toml` 和 `src/nexus_agent_sdk/__init__.py` 的版本，
   把待发布改动移入 CHANGELOG 对应版本章节，例如 `## [0.1.0]`。
3. 提交并推送对应 `v0.1.0` tag；或手动运行 Publish to PyPI，输入已有 tag。

本地检查：

```sh
uv sync --frozen --group dev
uv run python -m compileall -q examples
uv run ruff check .
uv run ruff format --check .
uv run mypy src/nexus_agent_sdk
uv build --out-dir dist/release
uv run python scripts/test_wheel.py dist/release/*.whl
```

交叉构建使用 `NXS_BUILD_PLATFORM=linux-arm64 uv build --wheel`。
目标平台的执行验证由对应 CI runner 完成。
