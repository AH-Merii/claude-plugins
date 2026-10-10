"""Shared test fixtures: real git repos in temp dirs, and a recording stand-in for `gh`."""
import json
import os
import subprocess
import sys
import shlex
import tempfile
from unittest import mock

PLUGIN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PLUGIN)

GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

# git sets these for hooks; inherited, they point every fixture git at the outer repo
GIT_REPO_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_PREFIX")


def clean_env(**extra):
    """os.environ without the outer repo's GIT_* pointers, with the fixture git config."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_REPO_VARS}
    return {**env, **GIT_ENV, **extra}


def isolate_git(test):
    """Give in-process code under test the same git config CI has: none of the developer's."""
    home = tempfile.TemporaryDirectory()
    test.addCleanup(home.cleanup)
    patcher = mock.patch.dict(os.environ, {**GIT_ENV, "HOME": home.name,
                                           "XDG_CONFIG_HOME": os.path.join(home.name, ".config")})
    patcher.start()
    test.addCleanup(patcher.stop)
    # patch.dict restores the whole environment on stop, these included
    for name in GIT_REPO_VARS:
        os.environ.pop(name, None)


def git(repo, *args):
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                         check=True, env=clean_env())
    return out.stdout.strip()


def numbered(n, start=1):
    return "".join(f"line {i}\n" for i in range(start, start + n))


class Repo:
    """A throwaway repo with a base commit and a head commit on branch `feature`.

    app.py at base: `line 1` .. `line 30`.
    app.py at head: line 10 reads `changed 10`, and `new a`, `new b` are inserted after
    line 20, so head has 32 lines. With git's 3 lines of context the PR diff has two hunks
    on the head side: lines 7-13 and lines 18-25. other.py is identical in both.
    """

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = self._tmp.name
        git(self.path, "init", "-q", "-b", "main")
        self.write("app.py", numbered(30))
        self.write("other.py", numbered(5))
        git(self.path, "add", ".")
        git(self.path, "commit", "-qm", "base")
        self.base = git(self.path, "rev-parse", "HEAD")
        git(self.path, "checkout", "-qb", "feature")
        lines = numbered(30).splitlines(keepends=True)
        lines[9] = "changed 10\n"
        lines[20:20] = ["new a\n", "new b\n"]
        self.write("app.py", "".join(lines))
        git(self.path, "commit", "-qam", "head")
        self.head = git(self.path, "rev-parse", "HEAD")

    def write(self, name, text):
        with open(os.path.join(self.path, name), "w") as f:
            f.write(text)

    def read(self, name):
        with open(os.path.join(self.path, name)) as f:
            return f.read()

    def cleanup(self):
        self._tmp.cleanup()


# the stand-in for gh and for the CLI's upload command, run as a real script
FAKE_GH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_gh.py")


INSTALL_URL = "https://github.com/apps/reviewer/installations/new"


class FakeGh:
    """Puts a recording `gh`, a token command and an upload command on PATH for CLI runs.

    Call cleanup() (or pass it to addCleanup) to remove the temp dir. HOME and XDG dirs
    point into it, so nothing the CLI stores can leak between tests or into the real home.
    """

    def __init__(self, repo, table, token=None):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.home = os.path.join(self.dir, "home")
        os.mkdir(self.home)
        self.log = os.path.join(self.dir, "calls.jsonl")
        self.table = os.path.join(self.dir, "table.json")
        self.repo = repo
        self._write_table(table)
        self._exe("gh", self._python(FAKE_GH))
        # without a token, fail the way reviewer-token does when the app isn't installed
        script = f"#!/bin/sh\necho {token}\n" if token else (
            "#!/bin/sh\necho 'reviewer-token: bot is not installed on o/r' >&2\n"
            f"echo 'install it: {INSTALL_URL}' >&2\nexit 1\n")
        self.token_cmd = self._exe("token", script)
        self.uploads = os.path.join(self.dir, "uploads.jsonl")
        self.upload_cmd = self._exe("upload", self._python(FAKE_GH, "--upload"))

    def cleanup(self):
        self._tmp.cleanup()

    @staticmethod
    def _python(*args):
        """A shell wrapper running this Python on `args` plus whatever it is given."""
        return f"#!/bin/sh\nexec {shlex.join([sys.executable, *args])} \"$@\"\n"

    def _exe(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, 0o755)
        return path

    def _write_table(self, table):
        with open(self.table, "w") as f:
            json.dump(table, f)

    def set_answer(self, key, stdout="", exit=0, pages=None):
        """Answer `key` with stdout and exit, or, for a paginated REST list, with `pages`."""
        with open(self.table) as f:
            table = json.load(f)
        table[key] = {"pages": pages} if pages is not None else {"stdout": stdout, "exit": exit}
        self._write_table(table)

    def run(self, *args, check=True, input_text=""):
        isolated = {name: os.path.join(self.home, name.lower()) for name in
                    ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")}
        env = clean_env(**isolated, HOME=self.home,
                        PATH=self.dir + os.pathsep + os.environ["PATH"],
                        FAKE_GH_LOG=self.log, FAKE_GH_TABLE=self.table,
                        PR_THREADS_TOKEN_CMD=self.token_cmd, PR_THREADS_UPLOAD_CMD=self.upload_cmd,
                        FAKE_UPLOAD_LOG=self.uploads, PYTHONPATH=PLUGIN)
        # gh reads any of these; a token from the developer's shell would hide who posted
        for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
            env.pop(name, None)
        out = subprocess.run([sys.executable, "-m", "pr_threads", *args], cwd=self.repo,
                             capture_output=True, text=True, env=env, input=input_text)
        if check and out.returncode != 0:
            raise AssertionError(f"pr-threads {args} failed: {out.stderr}")
        return out

    def calls(self, needle=""):
        """Recorded requests whose route ("POST repos/o/r/pulls/5/reviews", ...) contains needle."""
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            rows = [json.loads(line) for line in f]
        return [r for r in rows if needle in r["route"]]

    def review_posts(self):
        """Bodies of submitted reviews, however the CLI sent them (stdin, file or fields)."""
        return [c["body"] for c in self.calls() if c["method"] == "POST"
                and (c["endpoint"] or "").rstrip("/").endswith("/reviews")]

    def upload_calls(self):
        if not os.path.exists(self.uploads):
            return []
        with open(self.uploads) as f:
            return [json.loads(line) for line in f]

    def fail_uploads(self):
        open(self.uploads + ".fail", "w").close()


def pages(items, size=30):
    """`items` split into JSON pages the way a REST list returns them: 30 to a page by default."""
    return [json.dumps(items[i:i + size]) for i in range(0, len(items), size)] or ["[]"]


def thread(id, resolved=False, outdated=False, line=10, start=None, comments=(("bot", "hi"),),
           commit=None):
    """One review thread as GitHub's GraphQL API returns it.

    `commit` is the commit the comments were written on (their originalCommit). An outdated
    thread has no current line; only originalLine/originalStartLine in that commit remain.
    """
    nodes = [{"author": {"login": a}, "body": b} for a, b in comments]
    if commit:
        for node in nodes:
            node["originalCommit"] = {"oid": commit}
    return {"id": id, "isResolved": resolved, "isOutdated": outdated, "path": "app.py",
            "line": None if outdated else line, "startLine": None if outdated else start,
            "originalLine": line, "originalStartLine": start,
            "comments": {"nodes": nodes}}


def threads_response(*threads):
    """A reviewThreads query response holding `threads`."""
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {
        "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": list(threads)}}}}}


def pr_table(repo, number=5):
    """Answers for the lookups every CLI run makes about PR `number`."""
    meta = {"number": number, "baseRefOid": repo.base, "headRefOid": repo.head,
            "headRefName": "feature"}
    rest = {"number": number, "base": {"sha": repo.base, "ref": "main"},
            "head": {"sha": repo.head, "ref": "feature"}}
    return {
        f"pr view {number}": {"stdout": json.dumps(meta)},
        f"GET repos/o/r/pulls/{number}$": {"stdout": json.dumps(rest)},
        "repo view": {"stdout": json.dumps({"nameWithOwner": "o/r"})},
        "POST /reviews": {"stdout": json.dumps({"html_url": f"https://github.com/o/r/pull/{number}"})},
        "GET /reviews": {"stdout": "[]"},
        "graphql reviewThreads": {"stdout": json.dumps(threads_response())},
    }
