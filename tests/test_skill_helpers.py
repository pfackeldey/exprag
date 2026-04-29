from exprag.agent.skills import (
    describe_git_states,
    describe_latest_runs,
    describe_runs,
    describe_value_paths,
    discover_value_paths,
    get_path,
    git_checkout_command,
    git_diff_between_runs,
    latest_runs,
    run_start_records,
    select_values,
    summarize_runs,
    track_records,
)


def test_kind_helpers_split_run_start_and_track_records() -> None:
    records = [
        {"kind": "run_start", "run_id": "run-a", "value": {"host": {"os": "macos"}}},
        {"kind": "track", "run_id": "run-a", "value": {"metrics": {"accuracy": 0.9}}},
        {"kind": "track", "run_id": "run-a", "value": {"metrics": {"loss": 0.1}}},
    ]

    assert len(run_start_records(records)) == 1
    assert len(track_records(records)) == 2


def test_summarize_runs_uses_stable_record_count_field() -> None:
    records = [
        {
            "run_id": "run-a",
            "experiment_name": "demo",
            "created_at": "2026-04-20T10:00:00+00:00",
            "value": {"metrics": {"accuracy": 0.8}},
            "_source_path": ".exprag/runs/run-a.jsonl",
        },
        {
            "run_id": "run-a",
            "experiment_name": "demo",
            "created_at": "2026-04-20T10:01:00+00:00",
            "value": {"metrics": {"accuracy": 0.9}},
            "_source_path": ".exprag/runs/run-a.jsonl",
        },
    ]

    summary = summarize_runs(records)

    assert summary[0]["record_count"] == 2
    assert "records" not in summary[0]
    assert summary[0]["value_keys"] == ["metrics"]


def test_describe_runs_is_blind_runnable() -> None:
    records = [
        {
            "run_id": "run-a",
            "experiment_name": "demo",
            "created_at": "2026-04-20T10:00:00+00:00",
            "value": {"metrics": {"accuracy": 0.8}},
            "_source_path": ".exprag/runs/run-a.jsonl",
        }
    ]

    table = describe_runs(records)

    assert table.splitlines()[0].startswith("experiment_name\trun_id\trecord_count")
    assert "demo\trun-a\t1\t" in table


def test_latest_runs_returns_run_summaries_not_records() -> None:
    records = [
        {
            "run_id": "run-a",
            "experiment_name": "old",
            "created_at": "2026-04-20T10:00:00+00:00",
            "kind": "track",
            "value": {"metrics": {"accuracy": 0.8}},
        },
        {
            "run_id": "run-b",
            "experiment_name": "new",
            "created_at": "2026-04-20T11:00:00+00:00",
            "kind": "track",
            "value": {"metrics": {"accuracy": 0.9}},
        },
    ]

    latest = latest_runs(records, n=1)

    assert len(latest) == 1
    assert latest[0]["run_id"] == "run-b"
    assert latest[0]["record_count"] == 1


def test_describe_latest_runs_is_blind_runnable() -> None:
    records = [
        {
            "run_id": "run-a",
            "experiment_name": "old",
            "created_at": "2026-04-20T10:00:00+00:00",
            "kind": "track",
            "value": {"metrics": {"accuracy": 0.8}},
        },
        {
            "run_id": "run-b",
            "experiment_name": "new",
            "created_at": "2026-04-20T11:00:00+00:00",
            "kind": "track",
            "value": {"metrics": {"accuracy": 0.9}},
        },
    ]

    table = describe_latest_runs(records, n=1)

    assert "new\trun-b\t1\t" in table
    assert "old\trun-a" not in table


def test_discover_value_paths_defaults_to_track_records() -> None:
    records = [
        {"kind": "run_start", "run_id": "run-a", "value": {"host": {"os": "macos"}}},
        {
            "kind": "track",
            "run_id": "run-a",
            "value": {"metrics": {"accuracy": 0.9}},
            "note": "validation accuracy",
        },
    ]

    paths = {item["path"]: item for item in discover_value_paths(records)}

    assert "value.metrics.accuracy" in paths
    assert "value.host.os" not in paths
    assert "note" not in paths


def test_discover_value_paths_can_scan_all_record_kinds() -> None:
    records = [
        {"kind": "run_start", "run_id": "run-a", "value": {"host": {"os": "macos"}}},
        {"kind": "track", "run_id": "run-a", "value": {"metrics": {"accuracy": 0.9}}},
    ]

    paths = {item["path"]: item for item in discover_value_paths(records, kinds=None)}

    assert "value.metrics.accuracy" in paths
    assert "value.host.os" in paths


def test_discover_value_paths_reports_counts_types_and_examples() -> None:
    records = [
        {
            "kind": "track",
            "run_id": "run-a",
            "value": {
                "metrics": {"loss": 0.5, "accuracy": 0.8},
                "history": [{"loss": 0.7}, {"loss": 0.5}],
                "tags": ["baseline", "small"],
            },
        },
        {
            "kind": "track",
            "run_id": "run-a",
            "value": {
                "metrics": {"loss": 0.4, "accuracy": 0.85},
                "history": [{"loss": 0.4}],
                "done": True,
            },
        },
    ]

    paths = {item["path"]: item for item in discover_value_paths(records)}

    assert paths["value.metrics.loss"] == {
        "path": "value.metrics.loss",
        "count": 2,
        "examples": [0.5, 0.4],
        "is_numeric": True,
        "types": ["float"],
    }
    assert paths["value.metrics.accuracy"]["count"] == 2
    assert paths["value.history.[].loss"]["count"] == 3
    assert paths["value.tags.[]"]["examples"] == ["baseline", "small"]
    assert paths["value.done"]["is_numeric"] is False


def test_discover_value_paths_supports_is_numeric_field() -> None:
    records = [{"kind": "track", "run_id": "run-a", "value": {"accuracy": 0.9}}]

    paths = discover_value_paths(records)

    assert paths[0]["path"] == "value.accuracy"
    assert paths[0]["is_numeric"] is True
    assert "numeric" not in paths[0]


def test_describe_value_paths_is_blind_runnable() -> None:
    records = [
        {
            "kind": "track",
            "run_id": "run-a",
            "value": {"metrics": {"accuracy": 0.9, "loss": 0.1}, "tag": "demo"},
        }
    ]

    table = describe_value_paths(records, contains="acc", is_numeric=True)

    assert table.splitlines()[0] == "path\tcount\tis_numeric\ttypes\texamples"
    assert "value.metrics.accuracy\t1\tTrue\tfloat\t0.9" in table
    assert "value.metrics.loss" not in table


def test_git_helpers_extract_state_and_build_commands() -> None:
    records = [
        {
            "kind": "run_start",
            "run_id": "run-clean",
            "experiment_name": "clean",
            "value": {
                "git": {
                    "commit": "abc123",
                    "branch": "main",
                    "dirty": False,
                    "run_commit": None,
                    "run_branch": None,
                }
            },
        },
        {
            "kind": "run_start",
            "run_id": "run-dirty",
            "experiment_name": "dirty",
            "value": {
                "git": {
                    "commit": "abc123",
                    "branch": "main",
                    "dirty": True,
                    "run_commit": "def789",
                    "run_branch": "run/uuid-1",
                }
            },
        },
    ]

    # --- describe_git_states ---
    table = describe_git_states(records)
    assert "run_id\texperiment_name\tcommit\tbranch\tdirty\tsnapshot_branch" in table
    assert "run-clean\tclean\tabc123\tmain\tFalse" in table
    assert "run-dirty\tdirty\tabc123\tmain\tTrue\trun/uuid-1" in table

    # --- git_checkout_command (clean) ---
    cmd = git_checkout_command("run-clean", records)
    assert "git checkout abc123" in cmd
    assert "clean" in cmd

    # --- git_checkout_command (dirty, prefers snapshot) ---
    cmd = git_checkout_command("run-dirty", records)
    assert "git checkout run/uuid-1" in cmd
    assert "# Snapshot includes uncommitted changes" in cmd

    # --- git_diff_between_runs ---
    diff = git_diff_between_runs("run-clean", "run-dirty", records)
    assert diff.startswith("git diff ")
    assert "run/uuid-1" in diff

    log = git_diff_between_runs("run-clean", "run-dirty", records, mode="log")
    assert log.startswith("git log --oneline ")

    # --- missing run ---
    assert git_checkout_command("nonexistent", records).startswith("Run 'nonexistent'")
    assert git_diff_between_runs("nonexistent", "run-clean", records).startswith(
        "Run 'nonexistent'"
    )
