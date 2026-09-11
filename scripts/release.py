"""发布前核对 tag、版本和变更说明，不执行远端写入。"""

import ast
import os
import re
import subprocess
import tomllib
from pathlib import Path


def main() -> None:
    tag = os.environ["TAG_NAME"]
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    if tag != f"v{version}":
        raise ValueError(f"Tag {tag} must match project version v{version}")
    tagged = subprocess.check_output(
        ["git", "rev-parse", f"refs/tags/{tag}^{{commit}}"], text=True
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if tagged != head:
        raise ValueError("Checkout must match the existing release tag")
    module = ast.parse(Path("src/nexus_agent_sdk/__init__.py").read_text())
    exported = next(
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        )
    )
    if exported != version:
        raise ValueError("__version__ must match pyproject.toml")
    changelog = Path("CHANGELOG.md").read_text()
    match = re.search(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    if match is None or not match[1].strip():
        raise ValueError(f"Add a nonempty CHANGELOG section for {version}")
    Path("release-notes.md").write_text(match[1].strip() + "\n")


if __name__ == "__main__":
    main()
