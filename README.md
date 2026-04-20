# exprag

`exprag` is a tiny experiment tracker for Python programs.
`exprag` is short for `Experiment + RAG`, although currently it's 
not a full fledged RAG system, it works similarly.

It writes one JSONL file per run, captures a small amount of run context
automatically, and ships helper functions that make it easy for an LLM
or a human to inspect and interact with it.

Automatically tracks enough information to reconstruct the code back to 
the state of a specific run. Just ask an LLM to do it for you...

## Install For Local Development

```bash
uv pip install -e .
```

## Track A Run

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

    # track some metrics to ask the LLM about later
    exp.track({"step": step, "metrics": {"loss": loss, "acc": acc}})
```

Run:

```bash
python examples/track_experiment.py
```

The runs are written to:

```text
.exprag/runs/<run_id>.jsonl
```

## Enhance a LLM with a SKILL to Ask Questions About Runs

Write the SKILL.md to the appropriate place so your agent finds it:

```bash
exprag-skill --write .claude/skills/exprag/SKILL.md  # Claude
```

```bash
exprag-skill --write .agents/skills/exprag/SKILL.md  # codex
```

```bash
exprag-skill --write .opencode/skills/exprag/SKILL.md  # opencode
```

Then load this skill in your agent to ask questions about your runs, e.g.:

> "Which run in the last two weeks has the highest accuracy?"

> "Which learning rates result in accuracies above 90%?"

> "Please restore the code back to the run which achieved the highest accuracy"
