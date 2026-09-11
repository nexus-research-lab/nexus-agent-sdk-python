"""构建时下载已锁定运行时；editable 安装保持离线。"""

import hashlib
import json
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

PLATFORMS = {
    "darwin-amd64": "macosx_14_0_x86_64",
    "darwin-arm64": "macosx_14_0_arm64",
    "linux-amd64": "manylinux_2_28_x86_64",
    "linux-arm64": "manylinux_2_28_aarch64",
    "windows-amd64": "win_amd64",
    "windows-arm64": "win_arm64",
}


def host_platform() -> str:
    system = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}.get(
        platform.system(), "unknown"
    )
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64"}.get(
        machine, machine
    )
    return f"{system}-{arch}"


def extract_runtime(archive: Path, destination: Path, names: list[str]) -> None:
    """只读取指定的普通文件，拒绝链接和重复成员，不执行通用路径解压。"""
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            for name in names:
                matches = [item for item in bundle.infolist() if item.filename == name]
                if len(matches) != 1 or matches[0].is_dir():
                    raise ValueError(f"Missing or duplicate runtime file: {name}")
                mode = matches[0].external_attr >> 16
                if mode & 0o170000 == 0o120000:
                    raise ValueError(f"Runtime file cannot be a symlink: {name}")
                (destination / name).write_bytes(bundle.read(matches[0]))
    else:
        with tarfile.open(archive) as bundle:
            for name in names:
                matches = [item for item in bundle.getmembers() if item.name == name]
                if len(matches) != 1 or not matches[0].isfile():
                    raise ValueError(f"Missing or invalid runtime file: {name}")
                source = bundle.extractfile(matches[0])
                assert source is not None
                with source, (destination / name).open("wb") as output:
                    shutil.copyfileobj(source, output)
    for name in names:
        path = destination / name
        if not path.stat().st_size:
            raise ValueError(f"Empty runtime file: {name}")
        path.chmod(0o755)


class RuntimeBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        if self.target_name != "wheel" or version == "editable":
            return
        target = os.environ.get("NXS_BUILD_PLATFORM") or host_platform()
        if target not in PLATFORMS:
            raise ValueError(f"Unsupported bundled nxs platform: {target}")
        root = Path(self.root)
        lock = json.loads((root / "runtime-lock.json").read_text())
        asset = next(
            item
            for item in lock["assets"]
            if f"{item['goos']}-{item['goarch']}" == target
        )
        prefix = (
            "https://github.com/nexus-research-lab/nexus-agent-sdk-bridge/"
            f"releases/download/{lock['release_tag']}/"
        )
        filename = asset["filename"]
        if Path(filename).name != filename or asset["url"] != prefix + filename:
            raise ValueError("Runtime lock must point to a versioned bridge asset")
        output = root / "build" / "runtime" / target
        output.mkdir(parents=True, exist_ok=True)
        names = (
            ["nxs.exe", "rg.exe"] if target.startswith("windows-") else ["nxs", "rg"]
        )
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / filename
            with urllib.request.urlopen(asset["url"], timeout=120) as response:
                with archive.open("wb") as stream:
                    shutil.copyfileobj(response, stream)
            with archive.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != asset["sha256"]:
                raise ValueError(f"SHA-256 mismatch for {filename}")
            extract_runtime(archive, output, names)
        metadata = output / "runtime.json"
        metadata.write_text(
            json.dumps(
                {"version": lock["version"], "platform": target, **asset}, indent=2
            )
            + "\n"
        )
        for path in [*(output / name for name in names), metadata]:
            build_data["force_include"][str(path)] = (
                f"nexus_agent_sdk/_bundled/{path.name}"
            )
        build_data["force_include"][str(root / "THIRD_PARTY_NOTICES")] = (
            "nexus_agent_sdk/_bundled/THIRD_PARTY_NOTICES"
        )
        build_data["tag"] = f"py3-none-{PLATFORMS[target]}"
        build_data["pure_python"] = False
