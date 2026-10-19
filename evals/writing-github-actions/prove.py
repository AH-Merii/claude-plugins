"""Prove the outcome checks bite: each must fail on the untouched repo and on sibling
wrong solutions (one bug each), and pass on the reference and on other correct designs.

usage: prove.py  (needs actionlint on PATH, or ACTIONLINT set; scratch goes to $EVAL_OUT/prove)
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

E = Path(__file__).resolve().parent
WORK = Path(os.environ.get("EVAL_OUT") or Path.home() / ".cache/claude-plugins/evals/writing-github-actions") / "prove"
REF = (E / "refs" / "ci.yml").read_text()


def sub(old, new, count=1):
    def f(text):
        assert old in text, f"mutation anchor not found: {old!r}"
        return text.replace(old, new, count)

    return f


def drop_test_line(pattern):
    """Drop the first line matching pattern inside the `test` job only."""

    def f(text):
        head, test = text.split("  test:\n", 1)
        test2 = re.sub(pattern, "", test, count=1, flags=re.MULTILINE)
        assert test2 != test, pattern
        return head + "  test:\n" + test2

    return f


NO_CHANGES_JOB = re.sub(r"  changes:\n.*?\n\n  test:\n", "  test:\n", REF, flags=re.DOTALL)
NO_CHANGES_JOB = NO_CHANGES_JOB.replace("    needs: changes\n", "").replace(
    "    if: ${{ !cancelled() && needs.changes.outputs.code != 'false' }}\n", ""
)

STEP_GATE = NO_CHANGES_JOB.replace(
    "      - run: pip install -r requirements-dev.txt\n      - run: pytest\n",
    """      - id: diff
        run: echo code=true >>"$GITHUB_OUTPUT"
      - if: steps.diff.outputs.code == 'true'
        run: pip install -r requirements-dev.txt
      - if: steps.diff.outputs.code == 'true'
        run: pytest
""",
).replace(
    "persist-credentials: false\n      - uses: actions/setup",
    "persist-credentials: false\n          fetch-depth: 2\n      - uses: actions/setup",
)

AGGREGATOR = (
    REF.replace(
        "  test:\n    name: test\n",
        "  shards:\n    name: shard ${{ matrix.shard }}\n    strategy:\n      matrix:\n        shard: [1, 2]\n",
    ).replace("      - run: pytest\n", "      - run: pytest\n")
    + """
  test:
    name: test
    needs: [changes, shards]
    if: ${{ !cancelled() }}
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    permissions: {}
    steps:
      - env:
          RESULTS: ${{ join(needs.*.result, ' ') }}
        run: |
          for r in $RESULTS; do [ "$r" = success ] || [ "$r" = skipped ] || exit 1; done
"""
)
AGG_NO_ALWAYS = AGGREGATOR.replace(
    "    needs: [changes, shards]\n    if: ${{ !cancelled() }}\n", "    needs: [changes, shards]\n"
)
AGG_NO_ALWAYS_SHARDS_GATED = AGG_NO_ALWAYS  # same bug, named for the report

DISK = sub(
    "      - uses: actions/setup-python",
    "      - name: Free disk space\n        run: sudo rm -rf /usr/share/dotnet /opt/ghc\n      - uses: actions/setup-python",
)

# (name, scenarios it applies to, workflow text or mutation, check expected to fail or None)
VARIANTS = [
    ("reference", "add-ci fix-pending speed-up", REF, None),
    ("alt_step_gate", "add-ci fix-pending", STEP_GATE, None),
    ("alt_aggregator", "add-ci fix-pending speed-up", AGGREGATOR, None),
    (
        "paths_ignore",
        "add-ci fix-pending speed-up",
        sub("  pull_request:\n", "  pull_request:\n    paths-ignore: ['docs/**']\n"),
        "reports",
    ),
    (
        "paths_only",
        "add-ci fix-pending",
        sub("  pull_request:\n", "  pull_request:\n    paths: ['src/**', 'tests/**']\n"),
        "reports",
    ),
    (
        "matrix_test",
        "add-ci speed-up",
        sub("    needs: changes\n", "    needs: changes\n    strategy:\n      matrix:\n        py: ['3.11', '3.12']\n"),
        "reports",
    ),
    (
        "if_fail_open",
        "add-ci fix-pending",
        sub(
            "${{ !cancelled() && needs.changes.outputs.code != 'false' }}",
            "${{ needs.changes.outputs.code == 'true' }}",
        ),
        "fail_closed",
    ),
    (
        "if_always_eq_true",
        "add-ci fix-pending",
        sub(
            "${{ !cancelled() && needs.changes.outputs.code != 'false' }}",
            "${{ always() && needs.changes.outputs.code == 'true' }}",
        ),
        "fail_closed",
    ),
    ("aggregator_no_always", "add-ci speed-up", AGG_NO_ALWAYS, "fail_closed"),
    ("no_skip", "add-ci fix-pending", NO_CHANGES_JOB, "skips_docs"),
    (
        "tag_pin",
        "add-ci",
        sub("actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0", "actions/setup-python@v7"),
        "pinned",
    ),
    (
        "write_scope",
        "add-ci",
        sub(
            "    timeout-minutes: 15\n    permissions:\n      contents: read\n",
            "    timeout-minutes: 15\n    permissions:\n      contents: write\n",
        ),
        "least_privilege",
    ),
    (
        "default_token",
        "add-ci",
        lambda t: drop_test_line(r"^    permissions:\n      contents: read\n")(t.replace("permissions: {}\n\n", "")),
        "least_privilege",
    ),
    ("no_timeout", "add-ci", drop_test_line(r"^    timeout-minutes: 15\n"), "timeouts"),
    (
        "persisted_token",
        "add-ci",
        drop_test_line(r"^        with:\n          persist-credentials: false\n"),
        "no_persisted_token",
    ),
    (
        "injection",
        "add-ci",
        sub("      - run: pytest\n", '      - run: pytest\n      - run: echo "tested ${{ github.head_ref }}"\n'),
        "no_injection",
    ),
    (
        "no_cancel",
        "add-ci speed-up",
        sub("  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n", ""),
        "concurrency",
    ),
    ("invalid", "add-ci fix-pending speed-up", sub("    needs: changes\n", "    needs: change\n"), "valid"),
    ("disk_cleanup", "speed-up", DISK, "no_disk_cleanup"),
    ("no_dep_cache", "speed-up", sub("          cache: pip\n", ""), "dep_cache"),
]


def seed_repo(d, scenario):
    """The scenario's starting repo; fixture workflows are stored as _github/."""
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(E / "seed" / "base", d)
    shutil.copytree(E / "scenarios" / scenario / "overlay", d, dirs_exist_ok=True)
    if (d / "_github").is_dir():
        (d / "_github").rename(d / ".github")


def build(scenario, workflow):
    d = WORK / scenario
    seed_repo(d, scenario)
    if workflow is not None:
        (d / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        (d / ".github" / "workflows" / "ci.yml").write_text(workflow)
    return d


def seed_for(scenario):
    d = WORK / f"{scenario}-seed"
    seed_repo(d, scenario)
    return d


def check(scenario, repo, seed):
    r = subprocess.run(
        [sys.executable, str(E / "check.py"), scenario, str(repo), str(seed)],
        capture_output=True,
        text=True,
        check=False,
    )
    fails = {ln.split()[1].rstrip(":") for ln in r.stdout.splitlines() if ln.startswith("FAIL ")}
    return r.returncode, fails, r.stdout


def main():
    bad = 0
    for scenario in ("add-ci", "fix-pending", "speed-up"):
        seed = seed_for(scenario)
        rc, fails, out = check(scenario, build(scenario, None), seed)
        ok = rc != 0
        print(f"{'ok ' if ok else 'BAD'} {scenario:12} untouched           -> fails {sorted(fails)}")
        bad += not ok
        for name, where, wf, expect in VARIANTS:
            if scenario not in where.split():
                continue
            text = wf if isinstance(wf, str) else wf(REF)
            rc, fails, out = check(scenario, build(scenario, text), seed)
            if expect is None:
                ok = rc == 0
            else:
                ok = rc != 0 and expect in fails
            print(
                f"{'ok ' if ok else 'BAD'} {scenario:12} {name:20}-> {'pass' if rc == 0 else 'fails ' + str(sorted(fails))}"
            )
            if not ok:
                bad += 1
                print(out)
        # Gate: an edited test fails the cell even with a correct workflow.
        d = build(scenario, REF)
        (d / "tests" / "test_count.py").write_text("def test_nothing():\n    pass\n")
        rc, fails, _ = check(scenario, d, seed)
        ok = rc != 0 and "gate:tests_untouched" in fails
        print(f"{'ok ' if ok else 'BAD'} {scenario:12} tests_edited        -> fails {sorted(fails)}")
        bad += not ok
    print("PROVE", "PASS" if bad == 0 else f"FAIL ({bad})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
