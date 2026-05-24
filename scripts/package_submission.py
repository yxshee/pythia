#!/usr/bin/env python3
"""Create the final hackathon submission zip, guarded by validation.

The script deliberately refuses to package while the live-only submission gate
fails. That prevents stale fixture feeds, private paid traces, local env files,
or build/dependency artifacts from slipping into the final archive.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT_FILES = {
    ".env.example",
    ".gitignore",
    ".gitmodules",
    "README.md",
    "STATUS.md",
    "VERIFY.md",
}
ROOT_DIRS = {
    ".github",
    "agent",
    "bot",
    "contracts",
    "docs",
    "scripts",
    "traces",
    "verify",
    "web",
}
EXCLUDED_PARTS = {
    ".git",
    ".private",
    ".venv",
    ".next",
    ".vercel",
    ".claude",
    ".vscode",
    "__pycache__",
    "node_modules",
    "cache",
    "out",
    "broadcast",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
EXCLUDED_NAMES = {
    ".env",
    ".env.local",
    ".blob-url",
    "next-env.d.ts",
    "tsconfig.tsbuildinfo",
    "submission.zip",
}


def should_exclude(rel: Path, *, is_dir: bool) -> bool:
    parts = rel.parts
    rel_posix = rel.as_posix()
    name = rel.name

    if not parts:
        return True
    if any(part in EXCLUDED_PARTS for part in parts):
        return True
    if name in EXCLUDED_NAMES:
        return True
    if name.endswith((".pyc", ".pyo", ".log")):
        return True
    if name.startswith(".DS_Store"):
        return True
    if rel_posix.startswith("web/data/picks-full"):
        return True
    if rel_posix.startswith("contracts/lib/"):
        return True
    if len(parts) == 2 and parts[0] == "traces" and name.startswith("trace-") and name.endswith(".json"):
        return True
    if parts[0] not in ROOT_FILES and parts[0] not in ROOT_DIRS:
        return True
    if is_dir and parts[0] in ROOT_FILES:
        return True
    return False


def iter_package_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*"):
        rel = path.relative_to(repo_root)
        if should_exclude(rel, is_dir=path.is_dir()):
            if path.is_dir():
                continue
            continue
        if path.is_file():
            files.append(rel)
    return sorted(files, key=lambda p: p.as_posix())


def validate_repo(repo_root: Path) -> list[str]:
    sys.path.insert(0, str(repo_root / "agent"))
    from pythia.scripts.validate_submission import validate_repo as validate

    # The packager produces the public submission zip; it must not contain
    # the paid bundle, so validate in package mode.
    return validate(repo_root, mode="package")


def create_zip(repo_root: Path, out_path: Path) -> None:
    files = iter_package_files(repo_root)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            zf.write(repo_root / rel, rel.as_posix())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("submission.zip"),
        help="Output zip path, relative to repo root unless absolute.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    out = args.out if args.out.is_absolute() else repo_root / args.out

    failures = validate_repo(repo_root)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        print("Refusing to create submission.zip until validation passes.", file=sys.stderr)
        return 1

    if out.exists():
        out.unlink()
    create_zip(repo_root, out)
    print(f"wrote {out.relative_to(repo_root)} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
