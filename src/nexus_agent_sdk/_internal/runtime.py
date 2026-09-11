"""运行时选择顺序：显式路径、包内产物、开发环境 PATH。"""

import os
import shutil
from pathlib import Path

from ..errors import ProcessError


def resolve_cli_path(explicit: str | Path | None) -> str:
    if explicit is not None:
        return str(explicit)
    bundled = Path(__file__).resolve().parent.parent / "_bundled"
    executable = bundled / ("nxs.exe" if os.name == "nt" else "nxs")
    if executable.is_file():
        return str(executable)
    if bundled.exists():
        raise ProcessError("Bundled nxs is missing; reinstall nexus-agent-sdk-python")
    found = shutil.which("nxs")
    if found:
        return found
    raise ProcessError(
        "nxs not found; install a platform wheel or set NexusAgentOptions(cli_path=...)"
    )
