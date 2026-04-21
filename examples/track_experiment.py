"""Track a small example experiment with exprag."""

from __future__ import annotations

import math
import platform
import subprocess
import sys

from exprag import Experiment


def uv_pip_freeze() -> str:
    try:
        result = subprocess.run(
            ["uv", "pip", "freeze"],
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError as error:
        return f"uv pip freeze failed: {error}"

    output = result.stdout.strip()
    error = result.stderr.strip()
    if result.returncode != 0:
        return f"uv pip freeze failed with exit code {result.returncode}: {error or output}"
    return output


def main() -> None:
    exp = Experiment(
        "example training run",
        metadata={
            "python": sys.version,
            "platform": platform.platform(),
            "uv_pip_freeze": uv_pip_freeze(),
            "hparams": {
                "lr": 0.03,
                "epochs": 5,
                "batch_size": 32,
            },
        },
    )

    for step in range(5):
        loss = math.exp(-0.6 * step)
        acc = 0.55 + 0.09 * step

        exp.track({"step": step, "metrics": {"loss": loss, "acc": acc}})


if __name__ == "__main__":
    main()
