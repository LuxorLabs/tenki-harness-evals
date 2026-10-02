"""Summarize a Harbor job: pass rate per harness, and why the rest didn't pass."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

OUTCOMES = ["passed", "failed", "api_error", "timeout", "harness_error", "infra_error"]
OUTCOME_LABELS = {
    "passed": "Passed",
    "failed": "Failed",
    "api_error": "API errors",
    "timeout": "Timeouts",
    "harness_error": "Harness errors",
    "infra_error": "Infra errors",
}
# Agent logs can be large; the errors that end a run are near the end.
LOG_TAIL_BYTES = 400_000

_API_ERROR = re.compile(
    r"API Error[^\"\\\n]{0,240}"
    r"|BadRequestError[^\"\\\n]{0,240}"
    r"|Invalid JSON data[^\"\\\n]{0,240}"
    r"|response stream was malformed"
    r"|key not allowed to access model[^\"\\\n]{0,80}"
    r"|[Rr]ate limit[^\"\\\n]{0,80}"
    r"|\b(?:4\d\d|5\d\d) (?:Bad Request|Unauthorized|Forbidden|Not Found|Too Many Requests"
    r"|Internal Server Error|Bad Gateway|Service Unavailable)[^\"\\\n]{0,120}"
)
# Specific causes first, so one request failure maps to one readable signature.
_SIGNATURES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"missing field `(\w+)`"), "request rejected: tool definition missing `{0}`"),
    (
        re.compile(r"did not match any variant of untagged enum (\w+)"),
        "request rejected: Responses API `input` not accepted ({0})",
    ),
    (re.compile(r"response stream was malformed"), "malformed streaming response"),
    (re.compile(r"key not allowed to access model"), "403: API key not allowed to use this model"),
    (re.compile(r"[Rr]ate limit"), "rate limited"),
]


@dataclass
class Trial:
    harness: str
    task: str
    outcome: str
    reward: float | None
    exception_type: str | None
    api_errors: list[str] = field(default_factory=list)
    path: Path | None = None


def api_error_signatures(text: str) -> list[str]:
    """Readable causes of endpoint errors in *text*; generic ones only if nothing specific."""
    specific, generic = set(), set()
    for match in _API_ERROR.finditer(text):
        snippet = match.group(0)
        for pattern, label in _SIGNATURES:
            found = pattern.search(snippet)
            if found:
                specific.add(label.format(*found.groups()))
                break
        else:
            normalized = re.sub(r" at line \d+ column \d+|\[\d+\]", "", snippet)
            generic.add(normalized.strip()[:160])
    return sorted(specific or generic)


def classify(trial_dir: Path) -> Trial:
    result = json.loads((trial_dir / "result.json").read_text())
    agent = json.loads((trial_dir / "config.json").read_text())["agent"]
    exception = result.get("exception_info") or {}
    exception_type = exception.get("exception_type")
    reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")

    texts = [exception.get("exception_message") or ""]
    for log in sorted((trial_dir / "agent").glob("*.txt")):
        data = log.read_bytes()[-LOG_TAIL_BYTES:]
        texts.append(data.decode(errors="replace"))
    api_errors = api_error_signatures("\n".join(texts))

    if reward is not None and reward >= 1:
        outcome = "passed"
    elif exception_type and result.get("agent_execution") is None:
        outcome = "infra_error"  # the agent never started
    elif api_errors:
        outcome = "api_error"
    elif exception_type == "AgentTimeoutError":
        outcome = "timeout"
    elif exception_type == "VerifierTimeoutError":
        outcome = "infra_error"
    elif exception_type:
        outcome = "harness_error"
    else:
        outcome = "failed"
    return Trial(
        harness=agent["name"],
        task=result.get("task_name") or trial_dir.name.split("__")[0],
        outcome=outcome,
        reward=reward,
        exception_type=exception_type,
        api_errors=api_errors,
        path=trial_dir,
    )


def load_job(job_dir: Path) -> list[Trial]:
    return [classify(p.parent) for p in sorted(job_dir.glob("*/result.json"))]


def job_model(job_dir: Path) -> str:
    for config in sorted(job_dir.glob("*/config.json")):
        agent = json.loads(config.read_text())["agent"]
        model = agent.get("model_name") or (agent.get("env") or {}).get("ANTHROPIC_MODEL")
        if model:
            return model.removeprefix("openai/")
    return "unknown"


def render(trials: list[Trial], job_dir: Path) -> str:
    by_harness: dict[str, list[Trial]] = defaultdict(list)
    for trial in trials:
        by_harness[trial.harness].append(trial)
    ranked = sorted(
        by_harness.items(),
        key=lambda item: (-sum(t.outcome == "passed" for t in item[1]) / len(item[1]), item[0]),
    )

    lines = [
        f"# Harness report: {job_model(job_dir)}",
        "",
        f"Job: `{job_dir}` · {len(trials)} trials · "
        f"{len({t.task for t in trials})} tasks · {len(by_harness)} harnesses",
        "",
        "| Harness | Pass rate | " + " | ".join(OUTCOME_LABELS[o] for o in OUTCOMES) + " |",
        "|---|---|" + "---|" * len(OUTCOMES),
    ]
    for harness, harness_trials in ranked:
        counts = Counter(t.outcome for t in harness_trials)
        rate = counts["passed"] / len(harness_trials)
        cells = " | ".join(str(counts[o]) for o in OUTCOMES)
        lines.append(f"| {harness} | {rate:.0%} | {cells} |")

    api_rows = []
    for harness, harness_trials in ranked:
        signature_trials: dict[str, list[Trial]] = defaultdict(list)
        for trial in harness_trials:
            for signature in trial.api_errors:
                signature_trials[signature].append(trial)
        for signature, hit in sorted(signature_trials.items(), key=lambda kv: -len(kv[1])):
            example = hit[0].path.name if hit[0].path else ""
            api_rows.append(f"| {harness} | {len(hit)} | {signature} | `{example}` |")
    if api_rows:
        lines += [
            "",
            "## API errors",
            "",
            "Requests the endpoint rejected or broke. These are fixes on the endpoint side.",
            "",
            "| Harness | Trials | Error | Example trial |",
            "|---|---|---|---|",
            *api_rows,
        ]

    lines += [
        "",
        "## Outcomes",
        "",
        "- **Failed**: the harness ran to completion and the task's tests failed.",
        "- **API errors**: the endpoint rejected or broke a request (a trial that still "
        "passed is counted as passed).",
        "- **Timeouts**: the agent hit the task's time limit.",
        "- **Harness errors**: the harness crashed for another reason.",
        "- **Infra errors**: the environment or verifier failed; not the model's fault.",
    ]
    return "\n".join(lines) + "\n"
