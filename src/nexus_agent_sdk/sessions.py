"""从 nxs transcript 读取会话目录，不维护第二份会话数据库。"""

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Any

from .errors import ProtocolError
from .types import JsonObject


@dataclass
class SessionInfo:
    session_id: str
    path: Path
    summary: str = ""
    cwd: str = ""
    first_prompt: str = ""
    custom_title: str = ""
    tag: str | None = None
    git_branch: str = ""
    last_modified: int = 0
    file_size: int = 0


@dataclass
class SessionMessage:
    type: str
    uuid: str
    session_id: str
    message: JsonObject
    parent_tool_use_id: str | None
    raw: JsonObject


class SessionStore:
    """显式配置根下的本地会话检索和追加元数据操作。"""

    def __init__(self, config_dir: str | Path | None = None):
        self.config_dir = (
            Path(
                config_dir
                or os.environ.get("NEXUS_CONFIG_DIR")
                or Path.home() / ".nexus"
            )
            .expanduser()
            .resolve()
        )

    def _entries(self, path: Path) -> Iterator[JsonObject]:
        """读取已打开文件的大小快照，仅忽略最后一条未完成的追加记录。"""
        with path.open("rb") as source:
            size = os.fstat(source.fileno()).st_size
            number = 0
            while source.tell() < size:
                line = source.readline(size - source.tell())
                number += 1
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except (ValueError, UnicodeError) as exc:
                    if source.tell() == size and not line.endswith(b"\n"):
                        return
                    raise ProtocolError(f"Invalid transcript {path}:{number}") from exc
                if not isinstance(value, dict):
                    raise ProtocolError(f"Expected transcript object {path}:{number}")
                yield value

    def list_sessions(
        self,
        *,
        directory: str | Path | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[SessionInfo]:
        """按最近修改排序；directory 精确匹配，不自动扩展其他 worktree。"""
        if offset < 0 or (limit is not None and limit < 0):
            raise ValueError("offset and limit cannot be negative")
        projects = self.config_dir / "projects"
        records = []
        # ponytail: 全扫描 transcript；目录规模实测成为瓶颈时再增加按项目索引。
        for path in projects.glob("*/*.jsonl"):
            if path.is_symlink() or not path.resolve().is_relative_to(
                projects.resolve()
            ):
                continue
            try:
                record = self._info(path)
            except FileNotFoundError:
                continue
            if directory is None or (
                record.cwd and Path(record.cwd).resolve() == Path(directory).resolve()
            ):
                records.append(record)
        records.sort(
            key=lambda item: (item.last_modified, item.session_id), reverse=True
        )
        return records[offset:] if limit is None else records[offset : offset + limit]

    def get_session_info(self, session_id: str) -> SessionInfo | None:
        if not session_id.strip():
            raise ValueError("session_id cannot be empty")
        return next(
            (item for item in self.list_sessions() if item.session_id == session_id),
            None,
        )

    def _require(self, session_id: str) -> SessionInfo:
        info = self.get_session_info(session_id)
        if info is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        return info

    def get_session_messages(
        self, session_id: str, *, offset: int = 0, limit: int | None = None
    ) -> list[SessionMessage]:
        if offset < 0 or (limit is not None and limit < 0):
            raise ValueError("offset and limit cannot be negative")
        info = self._require(session_id)
        messages = (
            SessionMessage(
                value["type"],
                value.get("uuid", ""),
                info.session_id,
                value.get("message", {}),
                value.get("parent_tool_use_id"),
                value,
            )
            for value in self._entries(info.path)
            if value.get("type") in {"user", "assistant"}
        )
        return list(islice(messages, offset, None if limit is None else offset + limit))

    def rename_session(self, session_id: str, title: str) -> None:
        if not title.strip():
            raise ValueError("title cannot be empty")
        self._append(session_id, {"type": "custom-title", "customTitle": title.strip()})

    def tag_session(self, session_id: str, tag: str | None) -> None:
        if tag is not None and not tag.strip():
            raise ValueError("Use None to clear a tag")
        self._append(
            session_id, {"type": "session-tag", "tag": tag.strip() if tag else None}
        )

    def _append(self, session_id: str, value: JsonObject) -> None:
        info = self._require(session_id)
        payload = {
            **value,
            "sessionId": info.session_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        flags = os.O_RDWR | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(info.path, flags)
        with os.fdopen(descriptor, "a+b") as output:
            if os.fstat(output.fileno()).st_size:
                output.seek(-1, os.SEEK_END)
                if output.read(1) != b"\n":
                    raise ProtocolError(
                        "Cannot append metadata to an incomplete transcript"
                    )
            output.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())

    def _info(self, path: Path) -> SessionInfo:
        stat = path.stat()
        info = SessionInfo(
            path.stem,
            path,
            last_modified=stat.st_mtime_ns // 1_000_000,
            file_size=stat.st_size,
        )
        ai_title = ""
        for item in self._entries(path):
            info.session_id = item.get("sessionId") or info.session_id
            info.cwd = item.get("cwd") or info.cwd
            info.git_branch = item.get("gitBranch") or info.git_branch
            kind = item.get("type")
            if kind == "custom-title":
                info.custom_title = item.get("customTitle", "")
            elif kind == "ai-title":
                ai_title = item.get("aiTitle", "")
            elif kind == "session-tag":
                info.tag = item.get("tag")
            elif kind == "user" and not info.first_prompt and not item.get("isMeta"):
                info.first_prompt = self._text(item.get("message", {}).get("content"))
        info.summary = (
            info.custom_title or ai_title or info.first_prompt or info.session_id
        )
        return info

    @staticmethod
    def _text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        return "\n".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
