"""SDK 错误与运行时失败结果分开，保留可定位的原始信息。"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import ResultMessage


class NexusSDKError(Exception):
    """SDK 操作失败。"""


class ProcessError(NexusSDKError):
    """进程启动、退出或管道失败。"""

    def __init__(self, message: str, exit_code: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


class ProtocolError(NexusSDKError):
    """运行时输出损坏或不符合消息包络。"""


class ControlError(NexusSDKError):
    """运行时拒绝控制请求。"""

    def __init__(self, message: str, request_id: str = ""):
        super().__init__(message)
        self.request_id = request_id


class BufferOverflowError(NexusSDKError):
    """消费者落后超过配置的队列内存预算。"""


class ResultError(NexusSDKError):
    """显式要求成功结果时，保留完整错误结果供调用方处理。"""

    def __init__(self, result: "ResultMessage"):
        self.result = result
        super().__init__("; ".join(result.errors) or result.result or result.subtype)
