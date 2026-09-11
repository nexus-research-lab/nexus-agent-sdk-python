"""模型服务配置映射为 nxs 环境变量，凭据不进入命令行。"""

import json
import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit


def _validate(base_url: str | None, headers: dict[str, str]) -> None:
    if base_url is not None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an HTTP or HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url cannot contain credentials, query or fragment")
    for name, value in headers.items():
        if not isinstance(name, str) or not re.fullmatch(
            r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name
        ):
            raise ValueError("Invalid provider header name")
        if not isinstance(value, str) or any(c in value for c in "\r\n\x00"):
            raise ValueError("Invalid provider header value")


def _environment(values: dict[str, str | None]) -> dict[str, str]:
    for name, value in values.items():
        if value is not None and (not isinstance(value, str) or "\x00" in value):
            raise ValueError(f"Invalid provider value for {name}")
    return {key: value for key, value in values.items() if value is not None}


@dataclass
class AnthropicProvider:
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    auth_token: str | None = field(default=None, repr=False)
    version: str | None = None
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    tool_discovery_transport: (
        Literal["schema_promotion", "native_references"] | None
    ) = None

    def to_env(self) -> dict[str, str]:
        _validate(self.base_url, self.headers)
        if self.api_key is not None and self.auth_token is not None:
            raise ValueError("Choose api_key or auth_token")
        if self.tool_discovery_transport not in {
            None,
            "schema_promotion",
            "native_references",
        }:
            raise ValueError("Invalid tool_discovery_transport")
        return _environment(
            {
                "NEXUS_API_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": self.api_key if self.auth_token is None else "",
                "ANTHROPIC_AUTH_TOKEN": self.auth_token if self.api_key is None else "",
                "ANTHROPIC_BASE_URL": self.base_url,
                "ANTHROPIC_VERSION": self.version,
                "ANTHROPIC_CUSTOM_HEADERS": json.dumps(self.headers)
                if self.headers
                else None,
                "NEXUS_TOOL_DISCOVERY_TRANSPORT": self.tool_discovery_transport,
            }
        )


@dataclass
class OpenAIProvider:
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    protocol: Literal["chat_completions", "responses"] = "chat_completions"
    org_id: str | None = None
    project_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict, repr=False)

    def to_env(self) -> dict[str, str]:
        _validate(self.base_url, self.headers)
        if self.protocol not in {"chat_completions", "responses"}:
            raise ValueError("Invalid OpenAI protocol")
        return _environment(
            {
                "NEXUS_API_PROVIDER": "openai",
                "NEXUS_OPENAI_PROTOCOL": self.protocol,
                "OPENAI_API_KEY": self.api_key,
                "OPENAI_BASE_URL": self.base_url,
                "OPENAI_ORG_ID": self.org_id,
                "OPENAI_PROJECT_ID": self.project_id,
                "OPENAI_CUSTOM_HEADERS": json.dumps(self.headers)
                if self.headers
                else None,
            }
        )
