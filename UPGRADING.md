# Upgrading the fork to a new upstream release

Numbered, each step with its command and expected outcome. Steps 5, 7 (staging)
and 9 (production) are operator steps (brief §5); the rebase itself is too
(brief §2: the one sanctioned force-push of the program).

1. **Sync the mirror.** `gh repo sync QuantGeeks/pynecore -b main` → GitHub
   reports the sync; `origin/main` now matches `upstream/main`.

2. **Read upstream's release notes since our base** for state, rolling-sum,
   drawing-registry and `request.security` changes — the method of
   `pynecore-upstream/FINDINGS.md`: every module that owns runner state is
   listed in `runner_state.tracked_names()`; any upstream change to those
   modules is a swap change and re-runs the whole gate suite, not just drift.
   `gh release list -R PyneSys/pynecore` is the index.

3. **Branch and cherry-pick the carried stack.**
   `git -C ~/stocks/apps/pynecore worktree add ~/stocks/worktrees/pynecore-rebase-<v> -b qg/rebase-<v> v<v>`
   then `git cherry-pick` the `FORK.md` "Carried patches" stack in order,
   dropping the rows marked `drop at next rebase (upstream <version>)` —
   upstream shipped their equivalent. The package version becomes
   `<v>+qg.1` (`pyproject.toml`), the release tag `<v>-qg.1` (spec §4.9).

4. **Open the rebase PR** `qg/rebase-<v>` → `qg/main`: `qg-ci` and `qg-gates`
   green on the head; the `gate4` inventory diff **reviewed by a person** and
   `qg/gates/inventory.json` updated in the PR itself (spec §13.1 item 2); and
   `drift` run against the PREVIOUS release (not upstream) as the drift report
   (spec §13.1 item 3) — the previous release is what production runs.

5. **Land it — the one sanctioned force-push of the program (brief §2), an
   operator step for sev, Brian or Fable, never an implementer's:**
   `git push --force-with-lease origin qg/rebase-<v>:qg/main` (old tags keep
   the old history installable), then
   `.venv/bin/python -I qg/tools/check_fork_md.py --repo . --base v<v> --release <v>-qg.1`
   → `FORK.md OK: <n> carried commit(s), <m> fork-only commit(s)`, and
   `git tag -a <v>-qg.1 -m "<v>-qg.1" <merge sha> && git push origin <v>-qg.1`.
   Never a GitHub Release (it triggers upstream's PyPI workflow).

6. **Plan 1's private CI** runs golden, E1 and speed against the new tag over
   the real fixtures (`QuantGeeks/indicator-scripts`).

7. **The service pin, staging first (ruling 15):** bump `pynesys-pynecore==<v>+qg.1`
   and the `[tool.uv.sources]` tag, then deploy with
   `bin/deploy.sh staging indicator --image <registry>/indicator-service:staging-<sha>`
   (from `qg-infra`; `--ref` selects the qg-infra play ref, not the image).
   The worker calls `assert_build` at start and refuses any other build.

8. **Canary:** one full live session on staging compared bit for bit with the
   previous image's session (spec §13.1 item 4). A mismatch stops the upgrade.

9. **Production:** an operator step after the close on sev's go; the previous
   image is kept for rollback (spec §13.1 item 6).

The solo sampler (spec §13.1 item 5) is the service's, not the fork's (Plan 4).
