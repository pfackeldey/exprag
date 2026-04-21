# exprag

[![PyPI version][pypi-version]][pypi-link]
<!--[![Conda-Forge][conda-badge]][conda-link]-->
[![PyPI platforms][pypi-platforms]][pypi-link]

`exprag` is an experiment memory for coding agents with zero dependencies.

It is intentionally small: one JSONL file per run, plus enough structured
context for an agent to answer questions about past experiments, compare runs,
and recover the exact code state that produced a result.

This is not trying to be another ML dashboard. The main interface is your
agent.

Ask things like:

> "Which run had the best validation accuracy?"

> "Compare the latest two runs and explain what changed."

> "Find the best run, inspect the code that produced it, and tell me why it won."

> "Restore the repository to the code state from the run with the lowest loss."

Every run records git state at startup: commit, branch, dirty status, status
output, and the working-tree diff. That means an agent can reconstruct not only
the checked-in commit, but also the uncommitted edits that existed when the run
was made.

The result is a lightweight loop:

1. Run experiments from normal Python.
2. Track structured values with short semantic notes.
3. Let an agent inspect `.exprag/runs/*.jsonl`.
4. Ask the agent to compare, explain, or roll code back to any run.

## Install For Local Development

```bash
uv pip install -e . --group=dev
```

## Create Agent-Readable Experiment Memory

```python
from exprag import Experiment

exp = Experiment(
    "training my neural network",
    # this metadata is captured only once at the experiment start
    metadata={
        "hparams": {
            "learning_rate": 0.03,
            "batch_size": 32,
        }
    },
)

for step in range(5):
    loss = 1.0 / (step + 1)
    acc = 0.6 + step * 0.05

    exp.track(
        {"step": step, "metrics": {"loss": loss, "acc": acc}},
        note="training metrics after each step",
    )
```

Run:

```bash
python examples/track_experiment.py
```

The runs are written to:

```text
.exprag/runs/<run_id>.jsonl
```

Each run starts with a `run_start` record containing process, host, metadata,
and git state. Each `track` record contains your structured value, wall-clock
time, monotonic `elapsed_ms`, and optional `note` context for the agent.

## Give Your Agent the Exprag Skill

Write the SKILL.md to the appropriate place so your agent finds it:

```bash
exprag-skill --write .claude/skills/exprag/SKILL.md
```

```bash
exprag-skill --write .agents/skills/exprag/SKILL.md
```

```bash
exprag-skill --write .opencode/skills/exprag/SKILL.md
```

Then ask your agent questions in terms of outcomes, not files:

> "Which run in the last two weeks has the highest accuracy?"

> "Which learning rates result in accuracies above 90%?"

> "Compare the best run against the latest run."

> "Show the metric history for the run where batch size was 32."

> "Restore the code back to the run that achieved the highest accuracy."

## Code-State Rollback

The powerful part is that exprag captures git context per run.

A `run_start` record includes enough information for an agent to reason about
the source tree at experiment time:

- current commit
- current branch
- whether the worktree was dirty
- `git status --porcelain`
- `git diff --no-ext-diff HEAD`
- process cwd and argv

That lets an agent perform a workflow like:

1. Find the run with the best metric.
2. Read its `run_start` git state.
3. Check out the recorded commit.
4. Reapply the recorded dirty diff if needed.
5. Verify that the repository matches the code that produced the run.

So a prompt like this is meaningful:

> "Find the run with the best validation accuracy, reconstruct the code from
> that run, and show me the exact changes compared with my current checkout."


<!--[conda-badge]: https://img.shields.io/conda/vn/conda-forge/exprag
[conda-link]: https://github.com/conda-forge/exprag-feedstock-->
[pypi-link]: https://pypi.org/project/exprag/
[pypi-platforms]: https://img.shields.io/pypi/pyversions/exprag
[pypi-version]: https://badge.fury.io/py/exprag.svg
