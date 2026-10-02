# tenki-harness-evals

Run one model across many coding-agent harnesses (Claude Code, OpenCode, Goose,
mini-swe-agent, Qwen Code, Terminus) on a graded benchmark, with every trial in its
own [Tenki](https://tenki.cloud) VM. Get back a report of where the model works,
where it fails the task, and where the harness can't talk to your API at all.

Built on [Harbor](https://github.com/harbor-framework/harbor), the framework behind
Terminal-Bench, and [tenki-harbor](https://github.com/LuxorLabs/tenki-harbor).

## Setup

You need [uv](https://docs.astral.sh/uv/), access to the private
`LuxorLabs/tenki-harbor` repo over SSH, a Tenki API key, and your model endpoint.

```bash
git clone git@github.com:LuxorLabs/tenki-harness-evals.git
cd tenki-harness-evals
uv sync
cp .env.example .env            # fill in your Tenki key and model endpoint
uv run tenki-harbor prepare     # once: put the printed snapshot id in .env
```

`prepare` builds a Tenki snapshot with Docker installed, which saves about 10 s on
every trial. It's optional.

## Run

```bash
uv run evals models                                        # what your endpoint serves
uv run evals run --model primalabs-ai/DeepSeek-V4-Flash-0731
```

That runs the default harnesses on the first 10 Terminal-Bench 2.0 tasks, 16 trials
at a time, then prints the report and saves it as `jobs/<job>/report.md`.

| Option | Default | |
|---|---|---|
| `--harnesses` | all defaults (see below) | Comma-separated, e.g. `--harnesses goose,claude-code` |
| `--tasks N` | `10` | First N tasks of the dataset |
| `--task NAME` | | A specific task; repeat for more |
| `--dataset` | `terminal-bench@2.0` | Any dataset in Harbor's registry (`uv run harbor datasets list`) |
| `--attempts` | `1` | Runs per harness × task; raise it to measure variance |
| `--concurrency` | `16` | VMs running at once |
| `--dry-run` | | Print the generated Harbor job config and stop |

The generated config is saved under `runs/`, so a run can be repeated exactly with
`uv run harbor run -c runs/<job>.yaml`.

## Read the results

```bash
uv run evals report             # latest job; or pass a job directory
uv run harbor view jobs         # every trajectory, step by step
```

Every trial lands in one bucket:

| Outcome | Meaning |
|---|---|
| Passed | The task's tests passed. |
| Failed | The harness finished and the tests failed: a model quality signal. |
| API errors | The endpoint rejected or broke one of the harness's requests. Fix these on the endpoint side. |
| Timeouts | The agent ran out of the task's time budget. |
| Harness errors | The harness crashed for another reason. |
| Infra errors | The VM or the task's verifier failed; not the model's fault. |

API errors are grouped by cause, with an example trial to open in `harbor view`.

### Example

`primalabs-ai/DeepSeek-V4-Flash-0731`, 6 harnesses × 10 Terminal-Bench 2.0 tasks,
60 trials on Tenki in 57 minutes:

| Harness | Pass rate | Passed | Failed | API errors | Timeouts |
|---|---|---|---|---|---|
| goose | 80% | 8 | 1 | 0 | 1 |
| terminus-2 | 80% | 8 | 1 | 0 | 1 |
| mini-swe-agent | 70% | 7 | 1 | 0 | 2 |
| claude-code | 20% | 2 | 0 | 7 | 1 |
| opencode | 0% | 0 | 0 | 10 | 0 |
| qwen-coder | 0% | 0 | 0 | 10 | 0 |

| Harness | Trials | API error |
|---|---|---|
| claude-code | 8 | malformed streaming response |
| opencode | 10 | request rejected: Responses API `input` not accepted (`ResponseInput`) |
| qwen-coder | 10 | request rejected: tool definition missing `parameters` |

The model is capable (80% with three harnesses), but half the harnesses can't use
it because of how the endpoint handles their requests.

## Harnesses

```bash
uv run evals harnesses
```

| Harness | API it uses | Notes |
|---|---|---|
| `terminus-2` | OpenAI Chat Completions | Harbor's reference harness |
| `mini-swe-agent` | OpenAI Chat Completions | |
| `goose` | OpenAI Chat Completions | |
| `opencode` | OpenAI Responses | |
| `qwen-coder` | OpenAI Chat Completions | |
| `claude-code` | Anthropic Messages | Reads `ANTHROPIC_BASE_URL` (no `/v1`) |
| `codex` | OpenAI Responses | Not in the defaults: Harbor 0.23 sends `org/model` as `model`. Works for model ids without a `/`. |

## Comparing models

Run the same command once per model and compare the reports. Use `--attempts 3`
when differences are small; single runs of agentic tasks are noisy.

## Cleanup and cost

Each trial is one Tenki VM sized to the task, deleted when the trial ends. If a
run is killed, its VMs stop on their own after two hours, or immediately with:

```bash
uv run tenki-harbor sessions    # list Harbor VMs still running
uv run tenki-harbor cleanup     # terminate them
```

## Development

```bash
uv run pytest
uv run ruff check . && uv run ruff format .
```
