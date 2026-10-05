import json
from pathlib import Path

import pytest

from harness_evals.report import api_error_signatures, classify, load_job, render


def make_trial(
    job: Path,
    name: str,
    *,
    harness: str = "goose",
    reward: float | None = 0.0,
    exception: str | None = None,
    message: str = "",
    log: str = "",
    agent_ran: bool = True,
) -> Path:
    trial = job / name
    (trial / "agent").mkdir(parents=True)
    agent = {"name": harness, "model_name": "openai/acme/model-1"}
    (trial / "config.json").write_text(json.dumps({"agent": agent}))
    result = {
        "task_name": name.split("__")[0],
        "verifier_result": {"rewards": {"reward": reward}} if reward is not None else None,
        "exception_info": {"exception_type": exception, "exception_message": message}
        if exception
        else None,
        "agent_execution": {"started_at": "x"} if agent_ran else None,
    }
    (trial / "result.json").write_text(json.dumps(result))
    if log:
        (trial / "agent" / f"{harness}.txt").write_text(log)
    return trial


@pytest.mark.parametrize(
    ("kwargs", "outcome"),
    [
        ({"reward": 1.0}, "passed"),
        ({"reward": 0.0}, "failed"),
        ({"exception": "AgentTimeoutError"}, "timeout"),
        ({"exception": "NonZeroAgentExitCodeError", "message": "segfault"}, "harness_error"),
        ({"exception": "RuntimeError", "agent_ran": False}, "infra_error"),
        ({"exception": "VerifierTimeoutError", "reward": None}, "infra_error"),
        ({"exception": "SandboxError", "message": "Stream removed (RST_STREAM)"}, "infra_error"),
        (
            {
                "exception": "UnknownApiError",
                "log": '"result":"API Error: The response stream was malformed."',
            },
            "api_error",
        ),
    ],
)
def test_outcomes(tmp_path, kwargs, outcome):
    assert classify(make_trial(tmp_path, "task__1", **kwargs)).outcome == outcome


def test_pass_wins_over_api_errors_seen_along_the_way(tmp_path):
    trial = make_trial(tmp_path, "task__1", reward=1.0, log="API Error: 429 Too Many Requests")
    result = classify(trial)
    assert result.outcome == "passed"
    assert result.api_errors


def test_signatures_are_specific_and_deduplicated():
    text = (
        "API Error: 400 litellm.BadRequestError: OpenAIException - Invalid JSON data: Failed to "
        "deserialize the JSON body into the target type: tools[2].function: missing field "
        "`parameters` at line 1 column 49030\n"
        'BadRequestError: OpenAIException - {"error": ...'
    )
    assert api_error_signatures(text) == ["request rejected: tool definition missing `parameters`"]


def test_unrecognized_errors_fall_back_to_the_raw_message():
    assert api_error_signatures("API Error: 502 Bad Gateway from upstream") == [
        "API Error: 502 Bad Gateway from upstream"
    ]


def test_render_ranks_harnesses_and_lists_api_errors(tmp_path):
    make_trial(tmp_path, "a__1", harness="goose", reward=1.0)
    make_trial(tmp_path, "b__1", harness="goose", reward=0.0)
    make_trial(
        tmp_path,
        "a__2",
        harness="qwen-coder",
        exception="UnknownApiError",
        message="Invalid JSON data: tools[0].function: missing field `parameters`",
    )
    report = render(load_job(tmp_path), tmp_path)
    assert "# Harness report: acme/model-1" in report
    assert report.index("| goose | 50% |") < report.index("| qwen-coder | 0% |")
    assert "| qwen-coder | 1 | request rejected: tool definition missing `parameters`" in report
