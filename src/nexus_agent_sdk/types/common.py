"""协议共享的 JSON 与权限模式类型。"""

from typing import Any, Literal

JsonObject = dict[str, Any]


PermissionMode = Literal["default", "acceptEdits", "plan", "bypassPermissions", "auto"]
