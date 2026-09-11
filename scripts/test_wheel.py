"""在独立环境测试已安装 wheel，包含默认内置运行时的真实会话。"""

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> None:
    wheel = Path(sys.argv[1]).resolve()
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as temporary:
        venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(temporary)
        python = Path(temporary) / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                str(wheel),
                "hatchling",
            ],
            check=True,
        )
        code = """
import asyncio, json, os, subprocess, tempfile
from pathlib import Path
import nexus_agent_sdk
from nexus_agent_sdk._internal.runtime import resolve_cli_path
binary = Path(resolve_cli_path(None))
assert '_bundled' in binary.parts, binary
assert binary.is_relative_to(Path(nexus_agent_sdk.__file__).resolve().parent)
metadata = json.loads((binary.parent / 'runtime.json').read_text())
version = subprocess.check_output([str(binary), '--version'], text=True)
assert metadata['version'] in version, version
rg = binary.with_name('rg.exe' if binary.suffix == '.exe' else 'rg')
subprocess.run([str(rg), '--version'], check=True)
print(version.strip())
from nexus_agent_sdk import NexusAgentOptions, NexusSDKClient
async def handshake():
    with tempfile.TemporaryDirectory() as config:
        options = NexusAgentOptions(
            persist_session=False, cwd=config,
            env={"NEXUS_CONFIG_DIR": config}, control_timeout=15,
        )
        async with NexusSDKClient(options) as client:
            assert client.is_connected
            assert isinstance(client.get_server_info(), dict)
asyncio.run(handshake())
"""
        subprocess.run([str(python), "-c", code], cwd=temporary, check=True)
        if (root / "tests").is_dir():
            environment = {**os.environ, "NXS_TEST_BINARY": "bundled"}
            subprocess.run(
                [str(python), "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=root,
                env=environment,
                check=True,
            )


if __name__ == "__main__":
    main()
