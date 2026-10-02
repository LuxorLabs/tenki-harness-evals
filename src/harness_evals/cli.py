"""evals: run one model across many harnesses on Tenki, then report where it breaks."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml
from dotenv import load_dotenv

from harness_evals.config import RunSpec, build_job_config
from harness_evals.harnesses import DEFAULT_HARNESSES, HARNESSES
from harness_evals.report import load_job, render

REQUIRED_ENV = {
    "openai": ["OPENAI_BASE_URL", "OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY"],
}


def _missing_env(harnesses: list[str]) -> list[str]:
    needed = ["TENKI_API_KEY"]
    for name in harnesses:
        needed += REQUIRED_ENV[HARNESSES[name].protocol]
    return [var for var in dict.fromkeys(needed) if not os.environ.get(var)]


def _write_report(job_dir: Path) -> str:
    report = render(load_job(job_dir), job_dir)
    (job_dir / "report.md").write_text(report)
    return report


def cmd_run(args: argparse.Namespace) -> int:
    harnesses = args.harnesses.split(",")
    spec = RunSpec(
        model=args.model,
        harnesses=harnesses,
        dataset=args.dataset,
        n_tasks=args.tasks,
        task_names=args.task or [],
        attempts=args.attempts,
        concurrency=args.concurrency,
        jobs_dir=args.jobs_dir,
    )
    config = build_job_config(spec)
    for name in harnesses:
        if HARNESSES[name].name == "codex" and "/" in args.model:
            print(f"warning: codex: {HARNESSES[name].note}", file=sys.stderr)

    config_path = Path("runs") / f"{config['job_name']}.yaml"
    config_path.parent.mkdir(exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    if args.dry_run:
        print(config_path.read_text())
        return 0

    missing = _missing_env(harnesses)
    if missing:
        print(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
        return 1

    harbor = Path(sys.executable).parent / "harbor"
    print(f"Running {config['job_name']} ({config_path})")
    code = subprocess.call([str(harbor), "run", "-c", str(config_path)])
    job_dir = Path(args.jobs_dir) / config["job_name"]
    if job_dir.is_dir():
        print(_write_report(job_dir))
        print(
            f"Report saved to {job_dir / 'report.md'}. Browse trajectories: "
            f"uv run harbor view {args.jobs_dir}"
        )
    return code


def cmd_report(args: argparse.Namespace) -> int:
    if args.job_dir:
        job_dir = Path(args.job_dir)
    else:
        jobs = sorted(Path(args.jobs_dir).glob("*/"), key=lambda p: p.stat().st_mtime)
        if not jobs:
            print(f"No jobs in {args.jobs_dir}/")
            return 1
        job_dir = jobs[-1]
    print(_write_report(job_dir))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    base_url, key = os.environ.get("OPENAI_BASE_URL"), os.environ.get("OPENAI_API_KEY")
    if not base_url or not key:
        print("Set OPENAI_BASE_URL and OPENAI_API_KEY (see .env.example).")
        return 1
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {key}"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        for model in json.load(response).get("data", []):
            print(model["id"])
    return 0


def cmd_harnesses(args: argparse.Namespace) -> int:
    for harness in HARNESSES.values():
        default = "default" if harness.name in DEFAULT_HARNESSES else ""
        print(f"{harness.name:<16} {harness.protocol:<10} {default:<8} {harness.note}")
    return 0


def main() -> None:
    load_dotenv()
    # The Tenki SDK's gRPC client logs an info line on every subprocess fork.
    os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
    parser = argparse.ArgumentParser(prog="evals", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Run a model across harnesses, then write a report.")
    run.add_argument("--model", required=True, help="Model id as the endpoint names it.")
    run.add_argument("--harnesses", default=",".join(DEFAULT_HARNESSES))
    run.add_argument("--dataset", default="terminal-bench@2.0")
    run.add_argument("--tasks", type=int, default=10, help="First N tasks of the dataset.")
    run.add_argument("--task", action="append", help="Run this task (repeatable).")
    run.add_argument("--attempts", type=int, default=1)
    run.add_argument("--concurrency", type=int, default=16)
    run.add_argument("--jobs-dir", default="jobs")
    run.add_argument("--dry-run", action="store_true", help="Print the job config only.")
    run.set_defaults(handler=cmd_run)

    report = commands.add_parser("report", help="Summarize a finished job.")
    report.add_argument("job_dir", nargs="?", help="Defaults to the latest job.")
    report.add_argument("--jobs-dir", default="jobs")
    report.set_defaults(handler=cmd_report)

    commands.add_parser("models", help="List models the endpoint serves.").set_defaults(
        handler=cmd_models
    )
    commands.add_parser("harnesses", help="List supported harnesses.").set_defaults(
        handler=cmd_harnesses
    )

    args = parser.parse_args()
    raise SystemExit(args.handler(args))
