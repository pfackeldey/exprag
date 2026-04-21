from pathlib import Path

from exprag.agent.skills import (
    main,
    render_skill_markdown,
    write_skill_markdown,
)


def test_skill_markdown_renders_frontmatter() -> None:
    markdown = render_skill_markdown()

    assert markdown.startswith("---\n")
    assert "name: exprag-jsonl" in markdown
    assert "description: Use when an agent needs to inspect exprag JSONL" in markdown
    assert "import exprag.agent.skills as exprag" in markdown
    assert "exprag.describe_value_paths(records" in markdown
    assert "returns records, not runs" in markdown
    assert "reconstruct the run's code" in markdown
    assert "top-level `note`" in markdown
    assert "elapsed_ms" in markdown
    assert "within-run timing" in markdown


def test_skill_cli_prints_markdown(capsys) -> None:
    assert main([]) == 0

    captured = capsys.readouterr()
    assert captured.out == render_skill_markdown()
    assert captured.err == ""


def test_skill_cli_writes_markdown(tmp_path: Path, capsys) -> None:
    target = tmp_path / "SKILL.md"

    assert main(["--write", str(target)]) == 0

    captured = capsys.readouterr()
    assert captured.out == f"{target}\n"
    assert target.read_text(encoding="utf-8") == render_skill_markdown()


def test_skill_cli_requires_write_path(capsys) -> None:
    try:
        main(["--write"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("main(['--write']) should require PATH")

    captured = capsys.readouterr()
    assert "expected one argument" in captured.err


def test_write_skill_markdown_writes_explicit_path(tmp_path: Path) -> None:
    target = tmp_path / "skill.md"

    assert write_skill_markdown(str(target)) == target
    assert target.read_text(encoding="utf-8") == render_skill_markdown()
