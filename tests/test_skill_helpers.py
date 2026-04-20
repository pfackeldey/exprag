from exprag.agent.skills import (
    describe_runs,
    describe_latest_runs,
    describe_value_paths,
    discover_value_paths,
    get_path,
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
        {"kind": "track", "run_id": "run-a", "value": {"metrics": {"accuracy": 0.9}}},
    ]

    paths = {item["path"]: item for item in discover_value_paths(records)}

    assert "value.metrics.accuracy" in paths
    assert "value.host.os" not in paths


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


def test_select_values_supports_discovered_list_wildcards() -> None:
    records = [
        {
            "run_id": "run-a",
            "experiment_name": "demo",
            "created_at": "2026-04-20T10:00:00+00:00",
            "value": {"history": [{"loss": 0.7}, {"loss": 0.5}]},
            "_source_path": ".exprag/runs/run-a.jsonl",
            "_line_number": 1,
        }
    ]

    assert get_path(records[0], "value.history.[].loss") == [0.7, 0.5]
    assert [
        row["value"] for row in select_values(records, "value.history.[].loss")
    ] == [0.7, 0.5]
