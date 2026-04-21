from __future__ import annotations

import re
import sys
from pathlib import Path


def read_version(path: str, section: str) -> str:
    in_section = False
    section_header = f"[{section}]"
    version_pattern = re.compile(r'^version\s*=\s*"([^"]+)"\s*$')

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == section_header
            continue
        if not in_section:
            continue
        match = version_pattern.match(stripped)
        if match:
            return match.group(1)

    raise ValueError(f"{path}: missing version in {section_header}")


def main() -> int:
    pyproject_version = read_version("pyproject.toml", "project")
    cargo_version = read_version("Cargo.toml", "package")

    if pyproject_version != cargo_version:
        print(
            "version mismatch: "
            f"pyproject.toml={pyproject_version}, Cargo.toml={cargo_version}",
            file=sys.stderr,
        )
        return 1

    print(f"version ok: {pyproject_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
