"""How each Harbor harness reaches a custom model endpoint."""

from dataclasses import dataclass
from typing import Literal

Protocol = Literal["openai", "anthropic"]

OPENAI_ENV = {"OPENAI_BASE_URL": "${OPENAI_BASE_URL}", "OPENAI_API_KEY": "${OPENAI_API_KEY}"}
ANTHROPIC_ENV = {
    "ANTHROPIC_BASE_URL": "${ANTHROPIC_BASE_URL}",
    "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
}


@dataclass(frozen=True)
class Harness:
    name: str
    protocol: Protocol
    note: str = ""


HARNESSES: dict[str, Harness] = {
    h.name: h
    for h in [
        Harness("terminus-2", "openai", "Harbor's reference harness"),
        Harness("mini-swe-agent", "openai"),
        Harness("goose", "openai"),
        Harness("opencode", "openai", "uses the OpenAI Responses API"),
        Harness("qwen-coder", "openai"),
        Harness("claude-code", "anthropic", "uses the Anthropic Messages API"),
        Harness(
            "codex",
            "openai",
            "Harbor 0.23 drops everything before the last '/' of the model name, "
            "so models named 'org/model' are sent as 'model'",
        ),
    ]
}

DEFAULT_HARNESSES = [
    "terminus-2",
    "mini-swe-agent",
    "goose",
    "opencode",
    "qwen-coder",
    "claude-code",
]


def agent_config(harness: Harness, model: str) -> dict:
    if harness.protocol == "anthropic":
        # Harbor sends a provider-prefixed model name unchanged when a base URL is set,
        # so pass the bare name through ANTHROPIC_MODEL instead of model_name.
        return {"name": harness.name, "env": {**ANTHROPIC_ENV, "ANTHROPIC_MODEL": model}}
    return {"name": harness.name, "model_name": f"openai/{model}", "env": dict(OPENAI_ENV)}
