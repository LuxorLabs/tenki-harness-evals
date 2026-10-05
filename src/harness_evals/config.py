"""Build a Harbor job config: one model, several harnesses, one benchmark, on Tenki."""

import re
from dataclasses import dataclass, field
from datetime import datetime

from harness_evals.harnesses import HARNESSES, agent_config


@dataclass
class RunSpec:
    model: str
    harnesses: list[str]
    dataset: str = "terminal-bench@2.0"
    n_tasks: int | None = 10
    task_names: list[str] = field(default_factory=list)
    attempts: int = 1
    concurrency: int = 16
    jobs_dir: str = "jobs"
    job_name: str | None = None


def default_job_name(model: str, now: datetime | None = None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", model.lower().rsplit("/", 1)[-1]).strip("-")
    return f"{slug}-{(now or datetime.now()).strftime('%Y%m%d-%H%M%S')}"


def build_job_config(spec: RunSpec) -> dict:
    unknown = [h for h in spec.harnesses if h not in HARNESSES]
    if unknown:
        known = ", ".join(HARNESSES)
        raise ValueError(f"Unknown harness(es): {', '.join(unknown)}. Known: {known}")
    name, _, version = spec.dataset.partition("@")
    dataset: dict = {"name": name}
    if version:
        dataset["version"] = version
    if spec.task_names:
        dataset["task_names"] = spec.task_names
    elif spec.n_tasks:
        dataset["n_tasks"] = spec.n_tasks
    return {
        "job_name": spec.job_name or default_job_name(spec.model),
        "jobs_dir": spec.jobs_dir,
        "n_attempts": spec.attempts,
        "n_concurrent_trials": spec.concurrency,
        "environment": {"import_path": "tenki_harbor:TenkiEnvironment", "delete": True},
        "agents": [agent_config(HARNESSES[h], spec.model) for h in spec.harnesses],
        "datasets": [dataset],
    }
