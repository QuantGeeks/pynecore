"""qg/tools/check_fork_md.py: every carried commit has a FORK.md row with a filed upstream issue."""
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "check_fork_md.py"
HEAD = "# Fork\n\n## Carried patches\n\n| Commit | Why (spec) | Upstream issue | Status |\n|---|---|---|---|\n"
ROW = "| feat(math): window re-sum mode for math.sum | §9.2 E1 | https://github.com/PyneSys/pynecore/issues/101 | carried, default off |\n"
TAIL = "\n## Engine findings without a patch\n\n| feat(core): per-runner state | x | y | z |\n"


def __test_helper_repo(tmp_path: Path, subjects: list[str], fork_md: str, version: str = "6.10.10+qg.1") -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    def g(*a: str) -> None:
        subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True)
    g("init", "-q", "-b", "qg/main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (r / "pyproject.toml").write_text(f'[project]\nname = "pynesys-pynecore"\nversion = "{version}"\n')
    g("add", "."); g("commit", "-qm", "upstream base"); g("tag", "v6.10.10")
    for s in subjects:
        (r / "f.txt").write_text(s); g("add", "."); g("commit", "-qm", s)
    (r / "FORK.md").write_text(fork_md)
    return r


def __test_helper_run(r: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(TOOL), "--repo", str(r), "--base", "v6.10.10", *extra],
                          capture_output=True, text=True)


def __test_every_carried_commit_has_a_row__(tmp_path):
    r = __test_helper_repo(tmp_path, ["qg: fork policy", "feat(math): window re-sum mode for math.sum"], HEAD + ROW)
    p = __test_helper_run(r)
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.strip() == "FORK.md OK: 1 carried commit(s), 1 fork-only commit(s)"


def __test_not_filed_row_passes__(tmp_path):
    nf = ROW.replace("https://github.com/PyneSys/pynecore/issues/101", "not filed (sev, 2026-10-31)")
    r = __test_helper_repo(tmp_path, ["qg: fork policy", "feat(math): window re-sum mode for math.sum"], HEAD + nf)
    p = __test_helper_run(r)
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.strip() == "FORK.md OK: 1 carried commit(s), 1 fork-only commit(s)"


def __test_missing_row_is_refused_and_other_tables_do_not_count__(tmp_path):
    r = __test_helper_repo(tmp_path, ["feat(core): per-runner state"], HEAD + ROW + TAIL)
    p = __test_helper_run(r)
    assert p.returncode == 1
    assert "FORK.md MISSING ROW: feat(core): per-runner state" in p.stdout


def __test_pending_issue_is_refused__(tmp_path):
    pend = ROW.replace("https://github.com/PyneSys/pynecore/issues/101", "pending: qg/upstream/e1-window-resum.md")
    r = __test_helper_repo(tmp_path, ["feat(math): window re-sum mode for math.sum"], HEAD + pend)
    p = __test_helper_run(r)
    assert p.returncode == 1
    assert "FORK.md PENDING ISSUE: feat(math): window re-sum mode for math.sum" in p.stdout


def __test_release_tag_must_match_the_package_version__(tmp_path):
    r = __test_helper_repo(tmp_path, ["feat(math): window re-sum mode for math.sum"], HEAD + ROW, version="6.10.10+qg.2")
    assert __test_helper_run(r).returncode == 0
    p = __test_helper_run(r, "--release", "6.10.10-qg.1")
    assert p.returncode == 1
    assert "VERSION MISMATCH: pyproject 6.10.10+qg.2, tag 6.10.10-qg.1 wants 6.10.10+qg.1" in p.stdout
