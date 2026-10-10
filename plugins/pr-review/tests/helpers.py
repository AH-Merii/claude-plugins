"""Shared test fixtures: real git repos in temp dirs, and a recording stand-in for `gh`."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap

PLUGIN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PLUGIN)

GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(repo, *args):
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                         check=True, env={**os.environ, **GIT_ENV})
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


FAKE_GH = textwrap.dedent('''\
    #!/usr/bin/env python3
    """Records each call, then answers from a JSON table of argv-substring -> response."""
    import json, os, sys
    stdin = "" if sys.stdin.isatty() else sys.stdin.read()
    with open(os.environ["FAKE_GH_LOG"], "a") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "stdin": stdin,
                            "gh_token": os.environ.get("GH_TOKEN")}) + "\\n")
    table = json.load(open(os.environ["FAKE_GH_TABLE"]))
    joined = " ".join(sys.argv[1:])
    for key, answer in table.items():
        if key in joined:
            sys.stdout.write(answer.get("stdout", ""))
            sys.exit(answer.get("exit", 0))
    sys.stderr.write("fake gh: no answer for " + joined)
    sys.exit(1)
    ''')


class FakeGh:
    """Puts a recording `gh` and a token command on PATH for CLI runs."""

    def __init__(self, repo, table, token=None):
        self.dir = tempfile.mkdtemp()
        self.log = os.path.join(self.dir, "calls.jsonl")
        self.table = os.path.join(self.dir, "table.json")
        self.repo = repo
        with open(self.table, "w") as f:
            json.dump(table, f)
        self._exe("gh", FAKE_GH)
        script = f"#!/bin/sh\necho {token}\n" if token else "#!/bin/sh\nexit 1\n"
        self.token_cmd = self._exe("token", script)

    def _exe(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, 0o755)
        return path

    def set_answer(self, key, stdout="", exit=0):
        table = json.load(open(self.table))
        table[key] = {"stdout": stdout, "exit": exit}
        with open(self.table, "w") as f:
            json.dump(table, f)

    def run(self, *args, check=True, input_text=""):
        env = {**os.environ, **GIT_ENV, "PATH": self.dir + os.pathsep + os.environ["PATH"],
               "FAKE_GH_LOG": self.log, "FAKE_GH_TABLE": self.table,
               "PR_REVIEW_TOKEN_CMD": self.token_cmd, "PYTHONPATH": PLUGIN}
        env.pop("GH_TOKEN", None)
        out = subprocess.run([sys.executable, "-m", "pr_review", *args], cwd=self.repo,
                             capture_output=True, text=True, env=env, input=input_text)
        if check and out.returncode != 0:
            raise AssertionError(f"pr-review {args} failed: {out.stderr}")
        return out

    def calls(self, needle=""):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            rows = [json.loads(line) for line in f]
        return [r for r in rows if needle in " ".join(r["argv"])]


def pr_table(repo, number=5):
    """Answers for the metadata lookups every CLI run makes about PR `number`."""
    meta = {"number": number, "baseRefOid": repo.base, "headRefOid": repo.head,
            "headRefName": "feature"}
    return {
        f"pr view {number}": {"stdout": json.dumps(meta)},
        "repo view": {"stdout": json.dumps({"nameWithOwner": "o/r"})},
        "/reviews": {"stdout": json.dumps({"html_url": "https://github.com/o/r/pull/5"})},
        "graphql": {"stdout": json.dumps({"data": {}})},
    }
