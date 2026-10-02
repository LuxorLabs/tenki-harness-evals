import pytest
from harbor.models.job.config import JobConfig

from harness_evals.config import RunSpec, build_job_config

MODEL = "primalabs-ai/DeepSeek-V4-Flash-0731"


def test_config_is_a_valid_harbor_job():
    config = build_job_config(RunSpec(model=MODEL, harnesses=["terminus-2", "claude-code"]))
    job = JobConfig.model_validate(config)
    assert job.environment.import_path == "tenki_harbor:TenkiEnvironment"
    assert job.datasets[0].name == "terminal-bench"
    assert job.datasets[0].version == "2.0"
    assert job.datasets[0].n_tasks == 10


def test_openai_harnesses_get_prefixed_model_and_endpoint_env():
    config = build_job_config(RunSpec(model=MODEL, harnesses=["opencode"]))
    agent = config["agents"][0]
    assert agent["model_name"] == f"openai/{MODEL}"
    assert agent["env"]["OPENAI_BASE_URL"] == "${OPENAI_BASE_URL}"


def test_claude_code_gets_the_bare_model_through_env():
    config = build_job_config(RunSpec(model=MODEL, harnesses=["claude-code"]))
    agent = config["agents"][0]
    assert "model_name" not in agent
    assert agent["env"]["ANTHROPIC_MODEL"] == MODEL


def test_named_tasks_replace_task_count():
    config = build_job_config(
        RunSpec(model=MODEL, harnesses=["goose"], task_names=["a", "b"], dataset="swebench")
    )
    assert config["datasets"] == [{"name": "swebench", "task_names": ["a", "b"]}]


def test_unknown_harness_is_rejected():
    with pytest.raises(ValueError, match="Unknown harness"):
        build_job_config(RunSpec(model=MODEL, harnesses=["nope"]))
