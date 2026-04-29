"""Helpers and runtime skill renderer for inspecting exprag JSONL runs.

This file is the source of truth for the local exprag agent skill.

Render the skill Markdown with:

    exprag-skill

or from a checkout:

    python3 python/exprag/agent/skills.py
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from collections import defaultdict
from collections.abc import Mapping as MappingABC
from collections.abc import Sequence as SequenceABC
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Union,
)


SKILL_NAME = "exprag-jsonl"
SKILL_DESCRIPTION = (
    "Use when an agent needs to inspect exprag JSONL experiment runs under "
    ".exprag/runs, answer questions about tracked values, compare runs, or "
    "reconstruct what happened in a program."
)

HELPER_NAMES = [
    "runs_dir",
    "discover_run_files",
    "iter_records",
    "load_records",
    "run_start_records",
    "track_records",
    "summarize_runs",
    "describe_runs",
    "latest_runs",
    "describe_latest_runs",
    "parse_time",
    "records_between",
    "discover_value_paths",
    "describe_value_paths",
    "get_path",
    "select_values",
    "latest_records",
    "describe_git_states",
    "git_checkout_command",
    "git_diff_between_runs",
]


def runs_dir(root: Optional[str] = None) -> Path:
    """Return the exprag runs directory.

    By default this follows exprag itself: use EXPRAG_DIR if set, otherwise
    .exprag, then append runs. Passing a path ending in runs is also accepted.
    """

    base = Path(root or os.environ.get("EXPRAG_DIR", ".exprag"))
    if base.name == "runs":
        return base
    return base / "runs"


def discover_run_files(root: Optional[str] = None) -> List[Path]:
    """Return sorted JSONL run files from the exprag runs directory."""

    directory = runs_dir(root)
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.jsonl") if path.is_file())


def iter_records(
    root: Optional[str] = None,
    files: Optional[Iterable[Path]] = None,
) -> Iterator[Dict[str, Any]]:
    """Yield exprag records with _source_path and _line_number fields added.

    The source fields make answers auditable: cite them when explaining where a
    conclusion came from. Invalid JSONL raises ValueError with file and line.
    """

    paths = list(files) if files is not None else discover_run_files(root)
    for path in paths:
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"{path}:{line_number}: invalid JSONL: {error}"
                    ) from error
                if not isinstance(record, dict):
                    raise ValueError(f"{path}:{line_number}: expected a JSON object")
                record["_source_path"] = str(path)
                record["_line_number"] = line_number
                yield record


def load_records(
    root: Optional[str] = None,
    files: Optional[Iterable[Path]] = None,
) -> List[Dict[str, Any]]:
    """Load all exprag records into a list."""

    return list(iter_records(root=root, files=files))


def run_start_records(records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Return records with kind == "run_start"."""

    return [dict(record) for record in records if record.get("kind") == "run_start"]


def track_records(records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Return records with kind == "track"."""

    return [dict(record) for record in records if record.get("kind") == "track"]


def summarize_runs(records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Summarize records by run_id for quick run comparison.

    Each summary includes experiment_name, record_count, first/last timestamps,
    top-level keys seen under value objects, and source files.
    """

    grouped: Dict[str, Dict[str, Any]] = {}
    value_keys = defaultdict(set)
    source_paths = defaultdict(set)

    for record in records:
        run_id = str(record.get("run_id") or "<missing>")
        summary = grouped.setdefault(
            run_id,
            {
                "run_id": run_id,
                "experiment_name": record.get("experiment_name"),
                "record_count": 0,
                "first_created_at": None,
                "last_created_at": None,
            },
        )
        summary["record_count"] += 1

        created_at = record.get("created_at")
        if isinstance(created_at, str):
            if (
                summary["first_created_at"] is None
                or created_at < summary["first_created_at"]
            ):
                summary["first_created_at"] = created_at
            if (
                summary["last_created_at"] is None
                or created_at > summary["last_created_at"]
            ):
                summary["last_created_at"] = created_at

        value = record.get("value")
        if isinstance(value, MappingABC):
            value_keys[run_id].update(str(key) for key in value.keys())

        source_path = record.get("_source_path")
        if source_path:
            source_paths[run_id].add(str(source_path))

    results = []
    for run_id, summary in grouped.items():
        item = dict(summary)
        item["value_keys"] = sorted(value_keys[run_id])
        item["source_paths"] = sorted(source_paths[run_id])
        results.append(item)
    return sorted(results, key=lambda item: item.get("last_created_at") or "")


def describe_runs(records: Iterable[Mapping[str, Any]]) -> str:
    """Return a stable tab-separated run summary for direct printing.

    Use this when an agent needs an overview and should not rely on dictionary
    field guesses.
    """

    return _describe_run_summaries(summarize_runs(records))


def _describe_run_summaries(summaries: Sequence[Mapping[str, Any]]) -> str:
    if not summaries:
        return "No exprag runs found."

    lines = [
        "experiment_name\trun_id\trecord_count\tfirst_created_at\tlast_created_at\tvalue_keys\tsource_paths"
    ]
    for item in summaries:
        lines.append(
            "\t".join(
                [
                    _format_cell(item.get("experiment_name")),
                    _format_cell(item.get("run_id")),
                    _format_cell(item.get("record_count")),
                    _format_cell(item.get("first_created_at")),
                    _format_cell(item.get("last_created_at")),
                    _format_cell(item.get("value_keys")),
                    _format_cell(item.get("source_paths")),
                ]
            )
        )
    return "\n".join(lines)


def latest_runs(
    records: Iterable[Mapping[str, Any]], n: int = 5
) -> List[Dict[str, Any]]:
    """Return the latest n run summaries sorted by last_created_at."""

    if n < 0:
        raise ValueError("n must be non-negative")
    return summarize_runs(records)[-n:] if n else []


def describe_latest_runs(records: Iterable[Mapping[str, Any]], n: int = 5) -> str:
    """Return a stable tab-separated summary of the latest n runs."""

    return _describe_run_summaries(latest_runs(records, n=n))


def parse_time(value: Union[str, datetime]) -> datetime:
    """Parse an exprag timestamp or datetime into a timezone-aware datetime."""

    if isinstance(value, datetime):
        parsed = value
    else:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def records_between(
    records: Iterable[Mapping[str, Any]],
    since: Optional[Union[str, datetime]] = None,
    until: Optional[Union[str, datetime]] = None,
) -> List[Dict[str, Any]]:
    """Return records with created_at inside an optional inclusive time window.

    Use this for questions like "last week" after converting the user's date
    range into concrete ISO timestamps or datetime objects.
    """

    since_time = parse_time(since) if since is not None else None
    until_time = parse_time(until) if until is not None else None
    selected = []

    for record in records:
        created_at = record.get("created_at")
        if not isinstance(created_at, str):
            continue
        record_time = parse_time(created_at)
        if since_time is not None and record_time < since_time:
            continue
        if until_time is not None and record_time > until_time:
            continue
        selected.append(dict(record))

    return selected


def discover_value_paths(
    records: Iterable[Mapping[str, Any]],
    max_examples: int = 3,
    kinds: Optional[Sequence[str]] = ("track",),
) -> List[Dict[str, Any]]:
    """Discover leaf JSON paths under each record's value field.

    Returns dictionaries with stable fields: path, count, examples, types, and
    is_numeric. Use this before selecting metrics when you do not know the
    user's tracked JSON shape. List elements are represented with [] so
    repeated arrays share one path, for example value.history.[].loss. By
    default only kind == "track" records are scanned; pass kinds=None to scan
    all records.
    """

    discovered: Dict[str, Dict[str, Any]] = {}

    def visit(value: Any, path: List[str]) -> None:
        if isinstance(value, MappingABC):
            if not value:
                add_path(path, value)
                return
            for key, nested in value.items():
                visit(nested, [*path, str(key)])
            return

        if isinstance(value, SequenceABC) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            if not value:
                add_path(path, value)
                return
            for nested in value:
                visit(nested, [*path, "[]"])
            return

        add_path(path, value)

    def add_path(path: List[str], value: Any) -> None:
        path_text = ".".join(path)
        item = discovered.setdefault(
            path_text,
            {
                "path": path_text,
                "count": 0,
                "examples": [],
                "is_numeric": True,
                "types": set(),
            },
        )
        item["count"] += 1
        item["types"].add(type(value).__name__)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            item["is_numeric"] = False
        if len(item["examples"]) < max_examples and value not in item["examples"]:
            item["examples"].append(value)

    for record in records:
        if not _kind_matches(record, kinds):
            continue
        if "value" in record:
            visit(record["value"], ["value"])

    results = []
    for item in discovered.values():
        result = dict(item)
        result["types"] = sorted(result["types"])
        results.append(result)
    return sorted(results, key=lambda item: (-item["count"], item["path"]))


def describe_value_paths(
    records: Iterable[Mapping[str, Any]],
    contains: Optional[str] = None,
    is_numeric: Optional[bool] = None,
    max_examples: int = 3,
    limit: Optional[int] = None,
    kinds: Optional[Sequence[str]] = ("track",),
) -> str:
    """Return stable tab-separated discovered value paths for direct printing.

    Optional filters let an agent inspect likely metric paths without touching
    dictionary fields: contains="acc" filters paths by substring, and
    is_numeric=True keeps only numeric paths. By default only kind == "track"
    records are scanned; pass kinds=None to scan all records.
    """

    paths = discover_value_paths(records, max_examples=max_examples, kinds=kinds)
    if contains is not None:
        needle = contains.lower()
        paths = [item for item in paths if needle in item["path"].lower()]
    if is_numeric is not None:
        paths = [item for item in paths if item["is_numeric"] is is_numeric]
    if limit is not None:
        paths = paths[:limit]
    if not paths:
        return "No exprag value paths found."

    lines = ["path\tcount\tis_numeric\ttypes\texamples"]
    for item in paths:
        lines.append(
            "\t".join(
                [
                    _format_cell(item.get("path")),
                    _format_cell(item.get("count")),
                    _format_cell(item.get("is_numeric")),
                    _format_cell(item.get("types")),
                    _format_cell(item.get("examples")),
                ]
            )
        )
    return "\n".join(lines)


def get_path(value: Any, path: Union[Sequence[Any], str], default: Any = None) -> Any:
    """Read a nested value by dotted path or path parts.

    Examples: get_path(record, "value.metrics.accuracy") or
    get_path(record, ["value", "history", 0, "loss"]). Use [] as a list
    wildcard, for example get_path(record, "value.history.[].loss").
    """

    parts: Sequence[Any]
    if isinstance(path, str):
        parts = [part for part in path.split(".") if part]
    else:
        parts = path

    missing = object()

    def resolve(current: Any, remaining: Sequence[Any]) -> Any:
        if not remaining:
            return current

        part = remaining[0]
        tail = remaining[1:]

        if isinstance(current, MappingABC):
            if part not in current:
                return missing
            return resolve(current[part], tail)

        if isinstance(current, SequenceABC) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            if part == "[]":
                values = []
                for item in current:
                    resolved = resolve(item, tail)
                    if resolved is not missing:
                        values.append(resolved)
                return values if values else missing
            try:
                index = int(part)
            except (TypeError, ValueError):
                return missing
            if index < 0 or index >= len(current):
                return missing
            return resolve(current[index], tail)

        return missing

    result = resolve(value, parts)
    if result is missing:
        return default
    return result


def select_values(
    records: Iterable[Mapping[str, Any]],
    path: Union[Sequence[Any], str],
) -> List[Dict[str, Any]]:
    """Return non-missing values at path with run_id, timestamp, and source.

    If path contains the [] list wildcard, each matching list item is returned
    as a separate row.
    """

    selected = []
    missing = object()
    for record in records:
        value = get_path(record, path, default=missing)
        if value is missing:
            continue
        values = (
            value if _path_has_wildcard(path) and isinstance(value, list) else [value]
        )
        for item in values:
            if item is missing:
                continue
            selected.append(
                {
                    "run_id": record.get("run_id"),
                    "experiment_name": record.get("experiment_name"),
                    "created_at": record.get("created_at"),
                    "value": item,
                    "_source_path": record.get("_source_path"),
                    "_line_number": record.get("_line_number"),
                }
            )
    return selected


def _path_has_wildcard(path: Union[Sequence[Any], str]) -> bool:
    if isinstance(path, str):
        return "[]" in path.split(".")
    return "[]" in path


def _kind_matches(record: Mapping[str, Any], kinds: Optional[Sequence[str]]) -> bool:
    if kinds is None:
        return True
    return record.get("kind") in kinds


def latest_records(
    records: Iterable[Mapping[str, Any]],
    n: int = 20,
) -> List[Dict[str, Any]]:
    """Return the latest n records sorted by created_at."""

    return sorted(
        (dict(record) for record in records),
        key=lambda item: item.get("created_at") or "",
    )[-n:]


def _get_git_info(records: Iterable[Mapping[str, Any]], run_id: str) -> Dict[str, Any]:
    """Extract git state from a run's run_start record."""

    for record in records:
        if record.get("run_id") == run_id and record.get("kind") == "run_start":
            git = record.get("value", {}).get("git") or {}
            if git and git != "null" and isinstance(git, dict):
                return dict(git)
    return {}


def describe_git_states(records: Iterable[Mapping[str, Any]]) -> str:
    """Return a stable tab-separated summary of git state for every run.

    Columns: run_id, experiment_name, commit, branch, dirty, snapshot_branch.
    Use this first when the user asks about code versions, reproducibility,
    or which runs have snapshot branches available.
    """

    seen: set = set()
    rows = []
    for record in records:
        if record.get("kind") != "run_start":
            continue
        run_id = str(record.get("run_id") or "<missing>")
        if run_id in seen:
            continue
        seen.add(run_id)

        git = record.get("value", {}).get("git") or {}
        if not git or git == "null" or not isinstance(git, dict):
            continue

        rows.append(
            {
                "run_id": run_id,
                "experiment_name": record.get("experiment_name", ""),
                "commit": git.get("commit") or "",
                "branch": git.get("branch") or "",
                "dirty": git.get("dirty", False),
                "snapshot_branch": git.get("run_branch") or "",
            }
        )

    if not rows:
        return "No git state found in run_start records."

    lines = ["run_id\texperiment_name\tcommit\tbranch\tdirty\tsnapshot_branch"]
    for row in rows:
        lines.append(
            "\t".join(
                [
                    _format_cell(row["run_id"]),
                    _format_cell(row["experiment_name"]),
                    _format_cell(row["commit"]),
                    _format_cell(row["branch"]),
                    _format_cell(row["dirty"]),
                    _format_cell(row["snapshot_branch"]),
                ]
            )
        )
    return "\n".join(lines)


def git_checkout_command(run_id: str, records: Iterable[Mapping[str, Any]]) -> str:
    """Return the exact git command to recreate a run's code state.

    Prefers the snapshot branch (run/<uuid>) when dirty=true, falling back to
    the base commit hash otherwise. Use this when the user wants to switch
    their repo to a run's exact code state.
    """

    git = _get_git_info(records, run_id)
    if not git:
        return f"Run '{run_id}' has no git state recorded."

    snapshot = git.get("run_branch")
    commit = git.get("commit")

    if snapshot:
        return f"git checkout {snapshot}\n# Snapshot includes uncommitted changes from the original run."

    if commit:
        return f"git checkout {commit}\n# Run was clean; this is the exact commit that was checked out."

    return f"Run '{run_id}' has no recoverable git reference."


def git_diff_between_runs(
    from_run_id: str,
    to_run_id: str,
    records: Iterable[Mapping[str, Any]],
    mode: str = "diff",
) -> str:
    """Return a git command to compare code between two runs.

    mode="diff" produces `git diff` (shows file-level changes).
    mode="log" produces `git log --oneline` (shows commit history between).
    Use this when the user asks "what changed between run A and run B?"

    Snapshot branches (run/*) are always preferred when available; they
    include uncommitted changes from the original machine.
    """

    from_git = _get_git_info(records, from_run_id)
    to_git = _get_git_info(records, to_run_id)

    if not from_git:
        return f"Run '{from_run_id}' has no git state recorded."
    if not to_git:
        return f"Run '{to_run_id}' has no git state recorded."

    from_ref = from_git.get("run_branch") or from_git.get("commit", "")
    to_ref = to_git.get("run_branch") or to_git.get("commit", "")

    if not from_ref or not to_ref:
        return "One or both runs lack a recoverable git reference."

    if mode == "log":
        return f"git log --oneline {from_ref}..{to_ref}"

    return f"git diff {from_ref}..{to_ref}"


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ",".join(
            str(item).replace("\t", " ").replace("\n", " ") for item in value
        )
    if isinstance(value, MappingABC):
        text = json.dumps(value, sort_keys=True)
    else:
        text = str(value)
    return text.replace("\t", " ").replace("\n", " ")


def render_skill_markdown() -> str:
    """Render skill Markdown from this module's metadata and helper docstrings."""

    lines = [
        "---",
        f"name: {SKILL_NAME}",
        f"description: {SKILL_DESCRIPTION}",
        "---",
        "",
        "# Exprag JSONL Inspection",
        "",
        "Use this skill to answer questions about exprag experiment traces stored as JSONL.",
        "The source of truth is `exprag.agent.skills`; render this Markdown with `exprag-skill`.",
        'Records include `schema_version`, wall-clock `created_at`, and monotonic per-run `elapsed_ms`. Records with `kind == "run_start"` contain one-time run metadata such as git state, host/process context, and optional user metadata under `value.metadata`; records with `kind == "track"` contain user-tracked JSON values and may include a top-level `note` with semantic context from the user.',
        "",
        "## Workflow",
        "",
        "1. Import the module as `import exprag.agent.skills as exprag`; avoid partial helper imports in one-off scripts.",
        "2. Load records with `exprag.load_records()`; this reads `EXPRAG_DIR/runs/*.jsonl` or `.exprag/runs/*.jsonl`.",
        "3. Print `exprag.describe_runs(records)` first to understand which runs exist.",
        "4. Use `exprag.describe_latest_runs(records, n=2)` when the user asks for the latest runs; `latest_records` returns records, not runs.",
        '5. Print `exprag.describe_value_paths(records)` or `exprag.describe_value_paths(records, contains="acc")` to inspect tracked JSON fields from `kind == "track"` records.',
        "6. Print `exprag.describe_git_states(records)` when the user asks about code versions, reproducibility, or wants to reconstruct a run's state.",
        "7. Use `exprag.git_checkout_command(run_id, records)` to get the exact `git checkout` command for a run's code state (prefers snapshot branches when dirty).",
        '8. Use `exprag.git_diff_between_runs(from_id, to_id, records)` when the user asks "what changed between run A and run B?"',
        "9. When helpful, inspect the `run_start` git state directly and reconstruct the run's code; clearly label code-derived details as inferred context.",
        "10. Read top-level `note` on `track` records as user-provided semantic context, such as metric meaning, split, unit, or aggregation; do not treat it as a JSON value path.",
        "11. Use `elapsed_ms` for within-run timing and ordering; use `created_at` for wall-clock comparisons across runs.",
        "12. Use `exprag.select_values(records, path)` only after choosing an exact path from `describe_value_paths`.",
        "13. Use `exprag.track_records(records)` and `exprag.run_start_records(records)` instead of hand-written kind filters.",
        "14. Use plain Python plus `exprag.records_between`, `exprag.get_path`, `exprag.select_values`, and `exprag.latest_records` to answer the user's specific question.",
        "15. Cite `_source_path` and `_line_number` when making claims about a run.",
        "",
        "## Example",
        "",
        "```python",
        "import exprag.agent.skills as exprag",
        "",
        "records = exprag.load_records()",
        "print(exprag.describe_runs(records))",
        "print(exprag.describe_value_paths(records, contains='acc'))",
        "print(exprag.select_values(records, 'value.metrics.accuracy'))",
        "```",
        "",
        "## Helpers",
        "",
    ]

    namespace = globals()
    for name in HELPER_NAMES:
        helper = namespace[name]
        signature = inspect.signature(helper)
        doc = inspect.getdoc(helper) or ""
        lines.extend(
            [
                f"### `{name}{signature}`",
                "",
                doc,
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_skill_markdown(path: Union[str, Path]) -> Path:
    """Write the rendered SKILL.md file and return its path."""

    target = Path(path)
    target.write_text(render_skill_markdown(), encoding="utf-8")
    return target


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Render the exprag skill Markdown.

    By default this prints Markdown to stdout. Use --write PATH to materialize
    a SKILL.md file for systems that require one on disk.
    """

    parser = argparse.ArgumentParser(
        description="Render the exprag JSONL inspection skill."
    )
    parser.add_argument(
        "--write",
        metavar="PATH",
        help="write the rendered skill Markdown to PATH",
    )
    args = parser.parse_args(argv)

    if args.write:
        path = write_skill_markdown(args.write)
        print(path)
        return 0

    sys.stdout.write(render_skill_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
