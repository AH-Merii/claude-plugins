"""Outcome checks for the github-actions skill evals.

usage: check.py <scenario> <repo dir> [<seed dir>]

Prints one `PASS|FAIL <check>: <why>` line per check and a final `RESULT PASS|FAIL`.
Exit 0 only when every check passes. Gates (tests_untouched) fail the whole cell.

Each check states the rule it enforces; none pins a particular way of meeting it
(git diff vs a paths-filter action, one job vs an aggregator, and so on).
"""

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

REQUIRED = "test"
SHA = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
UNTRUSTED = re.compile(r"\$\{\{[^}]*(github\.event\.|github\.head_ref|inputs\.)[^}]*\}\}")
DISK_CLEANUP = re.compile(
    r"rm\s+-rf?[^\n]*(/usr/share/dotnet|/usr/local/lib/android|/opt/ghc|hostedtoolcache)"
    r"|free-disk-space|docker\s+(system|image)\s+prune"
)


# ---------------------------------------------------------------- workflows


def load_workflows(repo: Path) -> list[dict]:
    flows = []
    for path in sorted((repo / ".github" / "workflows").glob("*.y*ml")):
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        # YAML 1.1 reads the `on` key as True.
        if True in data:
            data["on"] = data.pop(True)
        data["_path"] = str(path.relative_to(repo))
        flows.append(data)
    return flows


def triggers(flow: dict) -> dict:
    on = flow.get("on")
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {e: None for e in on}
    return on or {}


def check_name(job_id: str, job: dict) -> str:
    return str(job.get("name") or job_id)


def is_matrix(job: dict) -> bool:
    return bool((job.get("strategy") or {}).get("matrix"))


def steps(job: dict) -> list[dict]:
    return [s for s in job.get("steps") or [] if isinstance(s, dict)]


def runs_pytest(job: dict) -> bool:
    return any(re.search(r"\bpytest\b", str(s.get("run", ""))) for s in steps(job))


def required_jobs(flows):
    """Every (flow, job_id, job) whose check is named like the required check."""
    out = []
    for flow in flows:
        for job_id, job in (flow.get("jobs") or {}).items():
            if isinstance(job, dict) and check_name(job_id, job) == REQUIRED:
                out.append((flow, job_id, job))
    return out


def needs_of(job: dict) -> list[str]:
    n = job.get("needs") or []
    return [n] if isinstance(n, str) else list(n)


# ------------------------------------------------- GitHub expression evaluator
# Enough of https://docs.github.com/en/actions/reference/workflows-and-actions/expressions
# to evaluate a job-level `if:` against simulated `needs` results.

TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>-?\d+(?:\.\d+)?)|(?P<op>==|!=|<=|>=|&&|\|\||[!<>(),\[\]])"
    r"|(?P<id>[A-Za-z_][A-Za-z0-9_\-]*(?:\.(?:[A-Za-z_*][A-Za-z0-9_\-]*|\*))*))"
)


class ExprError(Exception):
    pass


def tokenize(src):
    pos, out = 0, []
    src = src.strip()
    while pos < len(src):
        m = TOKEN.match(src, pos)
        if not m or m.end() == pos:
            raise ExprError(f"can't tokenize at {src[pos:]!r}")
        pos = m.end()
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
    return out


def to_num(v):
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return 0
        try:
            return float(s)
        except ValueError:
            return float("nan")
    return float("nan")


def loose_eq(a, b):
    if type(a) is type(b) or (isinstance(a, str) and isinstance(b, str)):
        if isinstance(a, str):
            return a.lower() == b.lower()
        return a == b
    return to_num(a) == to_num(b)


def truthy(v):
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)):
        return v != 0 and not math.isnan(v)
    if isinstance(v, str):
        return v != ""
    return True


def fn_contains(hay, needle):
    if isinstance(hay, list):
        return any(loose_eq(x, needle) for x in hay)
    return str(needle).lower() in str(hay or "").lower()


def fn_from_json(text):
    try:
        return json.loads(text or "")
    except (ValueError, TypeError) as e:
        raise ExprError("fromJSON of a non-JSON value") from e


STATUS_FUNCTIONS = {
    "always": lambda results: True,
    "cancelled": lambda results: False,
    "success": lambda results: all(r == "success" for r in results),
    "failure": lambda results: any(r == "failure" for r in results),
}
FUNCTIONS = {
    "contains": fn_contains,
    "startswith": lambda a, b: str(a or "").lower().startswith(str(b or "").lower()),
    "endswith": lambda a, b: str(a or "").lower().endswith(str(b or "").lower()),
    "fromjson": fn_from_json,
    "tojson": json.dumps,
    "join": lambda items, sep=",": sep.join(map(str, items or [])),
    "format": lambda fmt, *rest: str(fmt),
}


class Evaluator:
    def __init__(self, ctx, needs_results):
        self.ctx = ctx
        self.needs_results = needs_results
        self.used_status = False

    def evaluate(self, src):
        self.toks, self.i = tokenize(src), 0
        v = self.or_()
        if self.i != len(self.toks):
            raise ExprError(f"trailing tokens in {src!r}")
        return v

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self, val=None):
        tok = self.peek()
        if val is not None and tok[1] != val:
            raise ExprError(f"expected {val!r}, got {tok[1]!r}")
        self.i += 1
        return tok

    def or_(self):
        v = self.and_()
        while self.peek()[1] == "||":
            self.take()
            r = self.and_()
            v = v if truthy(v) else r
        return v

    def and_(self):
        v = self.cmp()
        while self.peek()[1] == "&&":
            self.take()
            r = self.cmp()
            v = r if truthy(v) else v
        return v

    def cmp(self):
        v = self.unary()
        while self.peek()[1] in ("==", "!=", "<", ">", "<=", ">="):
            op = self.take()[1]
            r = self.unary()
            if op == "==":
                v = loose_eq(v, r)
            elif op == "!=":
                v = not loose_eq(v, r)
            else:
                a, b = to_num(v), to_num(r)
                v = {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
        return v

    def unary(self):
        if self.peek()[1] == "!":
            self.take()
            return not truthy(self.unary())
        return self.primary()

    def primary(self):
        kind, val = self.take()
        if val == "(":
            v = self.or_()
            self.take(")")
            return v
        if kind == "str":
            return val[1:-1].replace("''", "'")
        if kind == "num":
            return float(val)
        if kind == "id":
            if val in ("true", "false"):
                return val == "true"
            if val == "null":
                return None
            if self.peek()[1] == "(":
                return self.call(val)
            v = self.lookup(val)
            while self.peek()[1] == "[":
                self.take()
                key = self.or_()
                self.take("]")
                v = v.get(str(key)) if isinstance(v, dict) else None
            return v
        raise ExprError(f"unexpected {val!r}")

    def lookup(self, dotted):
        parts = dotted.split(".")
        cur = self.ctx
        for i, p in enumerate(parts):
            if p == "*":
                rest = parts[i + 1 :]
                vals = list(cur.values()) if isinstance(cur, dict) else []
                for r in rest:
                    vals = [x.get(r) if isinstance(x, dict) else None for x in vals]
                return vals
            cur = cur.get(p) if isinstance(cur, dict) else None
        return cur

    def call(self, name):
        self.take("(")
        args = []
        while self.peek()[1] != ")":
            args.append(self.or_())
            if self.peek()[1] == ",":
                self.take()
        self.take(")")
        n = name.lower()
        if n in STATUS_FUNCTIONS:
            self.used_status = True
            return STATUS_FUNCTIONS[n](list(self.needs_results.values()))
        if n in FUNCTIONS:
            return FUNCTIONS[n](*args)
        raise ExprError(f"unknown function {name}")


def job_runs(job: dict, needs_results: dict, needs_outputs: dict) -> bool:
    """Whether GitHub would start `job` given its needs' results and outputs."""
    cond = job.get("if")
    ctx = {
        "needs": {k: {"result": needs_results[k], "outputs": needs_outputs.get(k, {})} for k in needs_results},
        "github": {"event_name": "pull_request", "ref": "refs/pull/7/merge"},
    }
    if cond is None:
        return all(r == "success" for r in needs_results.values())
    if isinstance(cond, bool):
        cond_src = "true" if cond else "false"
    else:
        cond_src = str(cond).strip()
        m = re.fullmatch(r"\$\{\{(.*)\}\}", cond_src, re.DOTALL)
        if m:
            cond_src = m.group(1)
    ev = Evaluator(ctx, needs_results)
    v = ev.evaluate(cond_src)
    if not ev.used_status:  # GitHub adds an implicit success() &&
        v = truthy(v) and all(r == "success" for r in needs_results.values())
    return truthy(v)


# ------------------------------------------------------------------- checks


def c_valid(repo, flows):
    """The workflows are valid: actionlint (shellcheck off) reports nothing."""
    files = sorted((repo / ".github" / "workflows").glob("*.y*ml"))
    if not files:
        return False, "no workflow files"
    r = subprocess.run(
        [os.environ.get("ACTIONLINT", "actionlint"), "-shellcheck=", "-pyflakes=", *map(str, files)],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.returncode == 0, ((r.stdout + r.stderr).strip().splitlines() or ["actionlint clean"])[0]


def c_reports(repo, flows):
    """Every PR gets the required check: a non-matrix job named `test`, in a workflow
    whose pull_request trigger has no paths/paths-ignore filter (those leave it pending)."""
    jobs = required_jobs(flows)
    if not jobs:
        return False, f"no job reports a check named {REQUIRED!r}"
    for flow, job_id, job in jobs:
        on = triggers(flow)
        if "pull_request" not in on:
            return False, f"{flow['_path']}: {job_id} doesn't run on pull_request"
        pr = on.get("pull_request") or {}
        for key in ("paths", "paths-ignore"):
            if key in pr:
                return False, f"{flow['_path']}: pull_request has {key}, so `test` stays pending"
        if is_matrix(job) and "${{" not in str(job.get("name", "")):
            return False, f"{flow['_path']}: {job_id} is a matrix: its checks are named per leg"
    return True, f"{len(jobs)} job(s) named {REQUIRED!r}, all on unfiltered pull_request"


def c_fail_closed(repo, flows):
    """The required check can't go green when the work behind it failed: if `test` needs
    other jobs, it still runs when one of them fails (a skipped job reports success),
    and a `test` that doesn't run the tests itself must read its needs' results."""
    jobs = required_jobs(flows)
    if not jobs:
        return False, "no `test` job"
    for flow, job_id, job in jobs:
        needs = needs_of(job)
        all_jobs = flow.get("jobs") or {}
        if not runs_pytest(job):
            if not any(runs_pytest(all_jobs.get(n) or {}) for n in needs):
                return False, f"{job_id} neither runs pytest nor needs a job that does"
            text = json.dumps(steps(job)) + str(job.get("if", ""))
            if "needs." not in text:
                return False, f"{job_id} aggregates {needs} but never reads their results"
        for failed in needs:
            res = {n: "success" for n in needs}
            res[failed] = "failure"
            try:
                runs = job_runs(job, res, {})
            except ExprError as e:
                return False, f"can't evaluate {job_id}'s if: {e}"
            if not runs:
                return False, f"when {failed} fails, {job_id} is skipped and reports success"
    return True, "test runs (or fails) whenever a job it needs fails"


def c_skips_docs(repo, flows):
    """Docs-only changes don't run pytest: the job or step that runs it is conditional
    on a changed-files result (job `if:` on needs outputs, a step `if:`, or a guard in
    the script)."""
    for flow in flows:
        if "pull_request" not in triggers(flow):
            continue
        for job_id, job in (flow.get("jobs") or {}).items():
            if not isinstance(job, dict) or not runs_pytest(job):
                continue
            if re.search(r"needs\.[\w-]+\.outputs", str(job.get("if", ""))):
                return True, f"{job_id} is gated on a needs output"
            for s in steps(job):
                run = str(s.get("run", ""))
                if re.search(r"\bpytest\b", run):
                    if re.search(r"(steps|needs)\.[\w-]+\.outputs|env\.", str(s.get("if", ""))):
                        return True, f"{job_id}: the pytest step is gated by its if"
                    if re.search(r"git diff|changed", run) and re.search(r"\bif\b|&&|\|\|", run):
                        return True, f"{job_id}: the pytest script checks the changed files"
    return False, "nothing keeps a docs-only pull request from running pytest"


def all_jobs(flows):
    for flow in flows:
        for job_id, job in (flow.get("jobs") or {}).items():
            if isinstance(job, dict):
                yield flow, job_id, job


def c_pinned(repo, flows):
    """Every action is pinned to a full commit SHA."""
    seen = 0
    for flow, job_id, job in all_jobs(flows):
        uses = [job["uses"]] if "uses" in job else []
        uses += [s["uses"] for s in steps(job) if "uses" in s]
        for u in uses:
            if u.startswith(("./", "docker://")):
                continue
            seen += 1
            if not SHA.match(u):
                return False, f"{flow['_path']}: {u} isn't pinned to a commit SHA"
    return seen > 0, f"{seen} action reference(s) pinned" if seen else "no actions used"


def c_least_privilege(repo, flows):
    """The token is read-only: the workflow sets `permissions` (none or read scopes),
    and no job grants a write scope."""
    if not flows:
        return False, "no workflows"
    for flow in flows:
        p = flow.get("permissions", "MISSING")
        if p == "MISSING":
            jobs = list((flow.get("jobs") or {}).values())
            if not jobs or any("permissions" not in j for j in jobs):
                return False, f"{flow['_path']}: no workflow-level permissions (default may be write)"
        for scope in [p] + [j.get("permissions") for _, _, j in all_jobs([flow])]:
            if scope in ("write-all",) or (isinstance(scope, dict) and "write" in scope.values()):
                return False, f"{flow['_path']}: grants write ({scope})"
    return True, "read-only token everywhere"


def c_timeouts(repo, flows):
    """Every job sets timeout-minutes (the default is 360)."""
    jobs = [(f, i, j) for f, i, j in all_jobs(flows) if "uses" not in j]
    if not jobs:
        return False, "no jobs"
    for flow, job_id, job in jobs:
        if "timeout-minutes" not in job:
            return False, f"{flow['_path']}: {job_id} has no timeout-minutes"
    return True, f"{len(jobs)} job(s) with timeout-minutes"


def c_no_persisted_token(repo, flows):
    """actions/checkout doesn't leave the token in .git/config (persist-credentials: false)."""
    n = 0
    for flow, job_id, job in all_jobs(flows):
        for s in steps(job):
            if str(s.get("uses", "")).startswith("actions/checkout@"):
                n += 1
                if (s.get("with") or {}).get("persist-credentials") not in (False, "false"):
                    return False, f"{flow['_path']}: {job_id}'s checkout persists credentials"
    return n > 0, f"{n} checkout(s) without persisted credentials"


def c_no_injection(repo, flows):
    """No untrusted event data is expanded into a run: script."""
    for flow, job_id, job in all_jobs(flows):
        for s in steps(job):
            m = UNTRUSTED.search(str(s.get("run", "")))
            if m:
                return False, f"{flow['_path']}: {job_id} expands {m.group(0)} in run:"
    return bool(flows), "no untrusted expressions in run:"


def c_concurrency(repo, flows):
    """A pull request's superseded runs are cancelled: the workflow with the required
    check has a concurrency group with cancel-in-progress."""
    jobs = required_jobs(flows)
    if not jobs:
        return False, "no `test` job"
    for flow, job_id, job in jobs:
        conc = flow.get("concurrency") or job.get("concurrency")
        if not isinstance(conc, dict) or not conc.get("group"):
            return False, f"{flow['_path']}: no concurrency group"
        cip = conc.get("cancel-in-progress")
        if cip in (None, False, "false"):
            return False, f"{flow['_path']}: cancel-in-progress is off"
    return True, "superseded runs are cancelled"


def c_no_disk_cleanup(repo, flows):
    """No step deletes runner tool trees for disk space the job doesn't need."""
    for flow, job_id, job in all_jobs(flows):
        for s in steps(job):
            text = str(s.get("run", "")) + " " + str(s.get("uses", ""))
            if DISK_CLEANUP.search(text):
                return False, f"{flow['_path']}: {job_id} still frees disk space ({s.get('name', 'step')})"
    return bool(flows), "no disk cleanup step"


def c_dep_cache(repo, flows):
    """Dependency downloads are cached: setup-python's cache, or actions/cache keyed
    on a hash of the requirement files."""
    for flow, job_id, job in all_jobs(flows):
        if not runs_pytest(job):
            continue
        for s in steps(job):
            uses, w = str(s.get("uses", "")), s.get("with") or {}
            if uses.startswith("actions/setup-python@") and w.get("cache"):
                return True, f"{job_id}: setup-python cache: {w['cache']}"
            keyed = "hashFiles" in str(w.get("key", "")) or w.get("enable-cache") in (True, "true")
            if re.match(r"(actions/cache|astral-sh/setup-uv)", uses) and keyed:
                return True, f"{job_id}: {uses.split('@')[0]}"
    return False, "the job that runs pytest downloads its dependencies uncached"


def g_tests_untouched(repo, seed):
    """Gate: the tests and the code under test are unchanged."""
    if seed is None:
        return True, "no seed given"
    r = subprocess.run(
        ["diff", "-r", "-q", "-x", "__pycache__", str(seed / "tests"), str(repo / "tests")],
        capture_output=True,
        text=True,
        check=False,
    )
    r2 = subprocess.run(
        ["diff", "-r", "-q", "-x", "__pycache__", "-x", "*.egg-info", str(seed / "src"), str(repo / "src")],
        capture_output=True,
        text=True,
        check=False,
    )
    ok = r.returncode == 0 and r2.returncode == 0
    return ok, "unchanged" if ok else (r.stdout + r2.stdout).strip().splitlines()[0]


HARDENING = [c_pinned, c_least_privilege, c_timeouts, c_no_persisted_token, c_no_injection, c_concurrency]
SCENARIOS = {
    "add-ci": [c_valid, c_reports, c_fail_closed, c_skips_docs, *HARDENING],
    "fix-pending": [c_valid, c_reports, c_fail_closed, c_skips_docs],
    "speed-up": [c_valid, c_reports, c_fail_closed, c_no_disk_cleanup, c_dep_cache, c_concurrency],
}


def main(argv):
    scenario, repo = argv[1], Path(argv[2])
    seed = Path(argv[3]) if len(argv) > 3 else None
    flows = load_workflows(repo)
    ok_all = True
    gate_ok, why = g_tests_untouched(repo, seed)
    print(f"{'PASS' if gate_ok else 'FAIL'} gate:tests_untouched: {why}")
    for check in SCENARIOS[scenario]:
        try:
            ok, why = check(repo, flows)
        except (ExprError, KeyError, TypeError, ValueError, AttributeError, IndexError, OSError) as e:
            # A crash in a check is a FAIL, never a pass.
            ok, why = False, f"check crashed: {e!r}"
        ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} {check.__name__[2:]}: {why}")
    result = ok_all and gate_ok
    print(f"RESULT {'PASS' if result else 'FAIL'}")
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
