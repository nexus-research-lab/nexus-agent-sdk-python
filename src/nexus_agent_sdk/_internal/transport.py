"""仅管理 nxs 进程及字节流；消息、控制和回调由客户端负责。"""

import asyncio
import json
import os
import signal
import sys
from collections.abc import AsyncGenerator
from contextlib import suppress

from ..errors import NexusSDKError, ProcessError, ProtocolError
from ..options import NexusAgentOptions
from ..types.common import JsonObject


class ProcessTransport:
    def __init__(self, options: NexusAgentOptions):
        self.options = options
        self.process: asyncio.subprocess.Process | None = None
        self._stderr = bytearray()
        self._stderr_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()
        self._closing: asyncio.Task | None = None

    @property
    def stderr(self) -> str:
        return self._stderr.decode(errors="replace")

    async def start(self, command: list[str]) -> None:
        environment = {**os.environ, **self.options.env}
        if self.options.provider is not None:
            environment.update(self.options.provider.to_env())
        if self.options.enable_file_checkpointing:
            environment["CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING"] = "true"
        if self.options.on_oauth_token_refresh:
            environment["CLAUDE_CODE_SDK_HAS_OAUTH_REFRESH"] = "1"
        spawn = asyncio.create_task(
            asyncio.create_subprocess_exec(
                *command,
                cwd=self.options.cwd,
                env=environment,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=self.options.max_buffer_size,
                start_new_session=sys.platform != "win32",
            )
        )
        try:
            self.process = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            # 先取得进程句柄，connect 的失败清理才能回收已启动的子进程。
            self.process = await asyncio.shield(spawn)
            self._stderr_task = asyncio.create_task(self._read_stderr())
            raise
        except OSError as exc:
            raise ProcessError(f"Cannot start nxs: {exc}") from exc
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def write(self, payload: JsonObject) -> None:
        process = self.process
        if self._closing or process is None or process.stdin is None:
            raise NexusSDKError("Transport is not connected")
        data = (
            json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n"
        ).encode()
        if len(data) > self.options.max_buffer_size:
            raise ValueError("Outbound JSON exceeds max_buffer_size")
        try:
            async with self._write_lock:
                process.stdin.write(data)
                await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise ProcessError(
                "nxs input pipe closed", process.returncode, self.stderr
            ) from exc

    async def messages(self) -> AsyncGenerator[tuple[JsonObject, int], None]:
        assert self.process is not None and self.process.stdout is not None
        try:
            while line := await self.process.stdout.readline():
                if not line.strip():
                    continue
                raw = json.loads(line)
                if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
                    raise ProtocolError("Expected message object with string type")
                yield raw, len(line)
        except (ValueError, UnicodeError) as exc:
            raise ProtocolError(f"Invalid nxs JSON output: {exc}") from exc
        try:
            code = await asyncio.wait_for(
                self.process.wait(), self.options.shutdown_timeout
            )
        except TimeoutError as exc:
            raise ProcessError(
                "nxs closed stdout without exiting", stderr=self.stderr
            ) from exc
        if self._stderr_task:
            await self._stderr_task
        if code:
            raise ProcessError(f"nxs exited with code {code}", code, self.stderr)

    async def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        while data := await self.process.stderr.read(4096):
            self._stderr.extend(data)
            del self._stderr[:-65536]

    async def close(self) -> None:
        """共享关闭任务，调用方取消也不能中止资源回收。"""
        if self._closing is None:
            self._closing = asyncio.create_task(self._close())
        try:
            await asyncio.shield(self._closing)
        except asyncio.CancelledError:
            await asyncio.shield(self._closing)
            raise

    async def _close(self) -> None:
        process = self.process
        if process is None:
            return
        assert process.stdin is not None and process.stdout is not None
        process.stdin.close()
        drain = asyncio.create_task(self._drain(process.stdout))
        try:
            try:
                await asyncio.wait_for(process.wait(), self.options.shutdown_timeout)
            except TimeoutError:
                self._signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(
                        process.wait(), self.options.shutdown_timeout
                    )
                except TimeoutError:
                    self._signal(signal.SIGTERM, kill=True)
                    await process.wait()
            # POSIX 的同组子进程也属于此 transport，父进程退出后仍需回收。
            if sys.platform != "win32":
                self._signal(signal.SIGKILL)
        finally:
            tasks = [task for task in (drain, self._stderr_task) if task is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def _signal(self, sig: int, *, kill: bool = False) -> None:
        assert self.process is not None
        with suppress(ProcessLookupError):
            if sys.platform != "win32":
                os.killpg(self.process.pid, signal.SIGKILL if kill else sig)
            elif kill:
                self.process.kill()
            else:
                self.process.terminate()

    @staticmethod
    async def _drain(stream: asyncio.StreamReader) -> None:
        while await stream.read(65536):
            pass
