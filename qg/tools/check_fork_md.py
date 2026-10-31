#!/usr/bin/env python3
"""Check FORK.md against the carried commits of a QuantGeeks/pynecore branch.

Every commit subject after <base> that does not start with "qg:" (a carried,
upstream-offerable patch) must equal the "Commit" cell of a row in the
"## Carried patches" table of FORK.md, and that row's "Upstream issue" cell
must be a filed https://github.com/PyneSys/pynecore/issues/<n>. With
--release <X-qg.N>, pyproject.toml's version must be X+qg.N (spec 4.9).
"""
import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ISSUE_RE = re.compile(r"https://github\.com/PyneSys/pynecore/issues/\d+")


def carried_rows(fork_md: str) -> list[list[str]]:
    """Data rows of the table under "## Carried patches" (ends at the next "## ")."""
    rows: list[list[str]] = []
    in_section = False
    for line in fork_md.splitlines():
        if line.startswith("## "):
            if in_section:
                break
            in_section = line == "## Carried patches"
        elif in_section and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not cells or cells[0] == "Commit" or all(set(c) <= set("-:") for c in cells):
                continue  # header row or |---| separator
            rows.append(cells)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, type=Path, help="the fork checkout to check")
    ap.add_argument("--base", required=True, help="upstream tag the branch carries, e.g. v6.10.10")
    ap.add_argument("--release", help="release tag to check against pyproject.toml, e.g. 6.10.10-qg.1")
    args = ap.parse_args()

    log = subprocess.run(
        ["git", "-C", str(args.repo), "log", "--no-merges", "--format=%s", f"{args.base}..HEAD"],
        check=True, capture_output=True, text=True)
    subjects = log.stdout.splitlines()

    rows = carried_rows((args.repo / "FORK.md").read_text())

    problems: list[str] = []
    carried = fork_only = 0
    for subject in subjects:
        if subject.startswith("qg:"):
            fork_only += 1
            continue
        carried += 1
        row = next((r for r in rows if r and r[0] == subject), None)
        if row is None:
            problems.append(f"FORK.md MISSING ROW: {subject}")
        elif len(row) < 3 or not ISSUE_RE.fullmatch(row[2]):
            problems.append(f"FORK.md PENDING ISSUE: {subject}")

    if args.release:
        m = re.fullmatch(r"(.+)-qg\.(\d+)", args.release)
        wanted = f"{m.group(1)}+qg.{m.group(2)}" if m else args.release
        with open(args.repo / "pyproject.toml", "rb") as f:
            version = tomllib.load(f)["project"]["version"]
        if version != wanted:
            problems.append(f"VERSION MISMATCH: pyproject {version}, tag {args.release} wants {wanted}")

    if problems:
        print("\n".join(problems))
        return 1
    print(f"FORK.md OK: {carried} carried commit(s), {fork_only} fork-only commit(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
