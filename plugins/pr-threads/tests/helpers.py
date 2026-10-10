"""Shared test fixtures: real git repos in temp dirs, and a recording stand-in for `gh`."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from unittest import mock

PLUGIN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PLUGIN)

GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def isolate_git(test):
    """Give in-process code under test the same git config CI has: none of the developer's."""
    home = tempfile.TemporaryDirectory()
    test.addCleanup(home.cleanup)
    patcher = mock.patch.dict(os.environ, {**GIT_ENV, "HOME": home.name,
                                           "XDG_CONFIG_HOME": os.path.join(home.name, ".config")})
    patcher.start()
    test.addCleanup(patcher.stop)


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
    """Stands in for gh: records each request by what it means, answers from a routing table.

    Routes: "pr view <n>", "repo view", "<METHOD> <endpoint part>" for REST, and
    "graphql <field>" for GraphQL. Known review mutations are answered with their real
    shape, so a reply or resolve never gets a thread listing back. A key whose endpoint
    part ends in "$" only matches that exact endpoint.

    Like real gh it expands {owner}/{repo} in api endpoints, applies simple `.a.b` paths
    given to --jq/-q (anything else fails loudly), and treats `gh issue comment N` as the
    POST to issues/N/comments it is.
    """
    import json, os, re, sys

    OWNER, REPO = "o", "r"

    VALUE_OPTS = {"-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field",
                  "--input", "-q", "--jq", "-t", "--template", "--hostname", "-p", "--preview",
                  "--cache", "--json", "-R", "--repo"}

    def read(path):
        with open(path) as f:
            return f.read()

    def token():
        """The token gh would send to github.com: GH_TOKEN, else GITHUB_TOKEN."""
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def typed(value):
        if value.startswith("@"):
            return read(value[1:])
        if value in ("true", "false", "null"):
            return {"true": True, "false": False, "null": None}[value]
        try:
            return int(value)
        except ValueError:
            return value

    def option(args, *names):
        for i, arg in enumerate(args[:-1]):
            if arg in names:
                return args[i + 1]
        return None

    def jq(data, path):
        """The subset of jq the fake understands: `.` and `.a.b` field paths."""
        if path != "." and not re.fullmatch(r"(\\.[A-Za-z_]\\w*)+", path):
            sys.stderr.write("fake gh: unsupported --jq " + path)
            sys.exit(3)
        for key in [p for p in path.split(".") if p]:
            data = data[key]
        return data if isinstance(data, str) else json.dumps(data)

    def parse(args):
        """Split gh args into (positionals, method, body)."""
        positionals, method, fields, raw = [], None, {}, None
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in VALUE_OPTS and i + 1 < len(args):
                value = args[i + 1]
                if arg in ("-X", "--method"):
                    method = value.upper()
                elif arg in ("-f", "--raw-field"):
                    key, _, val = value.partition("=")
                    fields[key] = val
                elif arg in ("-F", "--field"):
                    key, _, val = value.partition("=")
                    fields[key] = typed(val)
                elif arg == "--input":
                    raw = sys.stdin.read() if value == "-" else read(value)
                i += 2
            elif arg.startswith("-"):
                i += 1
            else:
                positionals.append(arg)
                i += 1
        body = json.loads(raw) if raw else (fields or None)
        return positionals, method or ("POST" if body is not None else "GET"), body

    def top_fields(query):
        """(alias, field, args text) for each top-level selection of the operation."""
        text = query[query.index("{") + 1:]
        found, depth, i = [], 0, 0
        name = re.compile(r"\\s*(?:(\\w+)\\s*:\\s*)?(\\w+)")
        while i < len(text):
            ch = text[i]
            if depth == 0 and ch not in "(){}":
                m = name.match(text, i)
                if m and m.group(2):
                    j = m.end()
                    args = ""
                    k = j
                    while k < len(text) and text[k].isspace():
                        k += 1
                    if k < len(text) and text[k] == "(":
                        level, end = 0, k
                        while end < len(text):
                            level += {"(": 1, ")": -1}.get(text[end], 0)
                            if level == 0:
                                break
                            end += 1
                        args, j = text[k:end + 1], end + 1
                    found.append((m.group(1) or m.group(2), m.group(2), args))
                    i = j
                    continue
            if ch in "({":
                depth += 1
            elif ch in ")}":
                depth -= 1
                if depth < 0:
                    break
            i += 1
        return found

    def mutation_answer(field, args):
        thread = re.search(r'(?:threadId|pullRequestReviewThreadId)\\s*:\\s*"([^"]+)"', args)
        tid = thread.group(1) if thread else None
        if field == "resolveReviewThread":
            return {"thread": {"id": tid, "isResolved": True}}
        if field == "unresolveReviewThread":
            return {"thread": {"id": tid, "isResolved": False}}
        if field == "addPullRequestReviewThreadReply":
            return {"comment": {"id": "C_new", "url": "https://github.com/o/r/pull/5#discussion_rC_new"}}
        return None

    args = sys.argv[1:]
    if args[:2] == ["issue", "comment"]:
        positionals, method, body = [a for a in args[2:3]], "POST", None
        text = option(args, "--body", "-b")
        source = option(args, "--body-file", "-F")
        if source is not None:
            text = sys.stdin.read() if source == "-" else read(source)
        body = {"body": text}
    else:
        positionals, method, body = parse(args[1:] if args[:1] == ["api"] else args)
    if args[:1] == ["api"] and positionals:
        positionals[0] = positionals[0].replace("{owner}", OWNER).replace("{repo}", REPO)
    record = {"argv": args, "method": None, "endpoint": None, "body": body, "fields": [],
              "gh_token": token()}
    if args[:2] == ["issue", "comment"]:
        endpoint = f"repos/{OWNER}/{REPO}/issues/{positionals[0]}/comments"
        record.update(method="POST", endpoint=endpoint)
        route = "POST " + endpoint
    elif args[:2] == ["pr", "view"]:
        route = f"pr view {positionals[2] if len(positionals) > 2 else ''}".strip()
    elif args[:2] == ["repo", "view"]:
        route = "repo view"
    elif args[:1] == ["api"] and positionals and positionals[0] == "graphql":
        query = (body or {}).get("query", "")
        fields = top_fields(query) if "{" in query else []
        record.update(method="POST", endpoint="graphql", fields=[f for _, f, _ in fields])
        route = "graphql " + ",".join(record["fields"])
    elif args[:1] == ["api"] and positionals:
        record.update(method=method, endpoint=positionals[0])
        route = f"{method} {positionals[0]}"
    else:
        route = " ".join(args)
    record["route"] = route
    with open(os.environ["FAKE_GH_LOG"], "a") as f:
        f.write(json.dumps(record) + "\\n")

    def rest_match(key):
        verb, _, part = key.partition(" ")
        if not route.startswith(verb + " "):
            return False
        if part.endswith("$"):
            return route.rstrip("/").endswith(part[:-1])
        return part in route

    def answer_with(stdout, code):
        path = option(args, "--jq", "-q")
        if path is not None and code == 0 and stdout:
            stdout = jq(json.loads(stdout), path) + "\\n"
        sys.stdout.write(stdout)
        sys.exit(code)

    with open(os.environ["FAKE_GH_TABLE"]) as f:
        table = json.load(f)
    for key, answer in table.items():
        if key == route or (key.startswith(("GET ", "POST ", "PATCH ", "PUT ", "DELETE "))
                            and rest_match(key)) \\
                or (key.startswith("graphql ") and record["endpoint"] == "graphql"
                    and re.search(r"\\b" + re.escape(key[8:]) + r"\\b", (body or {}).get("query", ""))):
            answer_with(answer.get("stdout", ""), answer.get("exit", 0))
    if record["endpoint"] == "graphql":
        data = {}
        for alias, field, field_args in top_fields((body or {}).get("query", "")):
            answer = mutation_answer(field, field_args)
            if answer is None:
                break
            data[alias] = answer
        else:
            if data:
                answer_with(json.dumps({"data": data}), 0)
    sys.stderr.write("fake gh: no answer for " + route)
    sys.exit(1)
    ''')


FAKE_UPLOAD = textwrap.dedent('''\
    #!/usr/bin/env python3
    """Stands in for the image upload: records who uploaded what, prints the asset URL."""
    import json, os, sys
    path = sys.argv[1]
    # the token gh would use, so a bot token passed either way is caught
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    with open(os.environ["FAKE_UPLOAD_LOG"], "a") as f:
        f.write(json.dumps({"file": path, "gh_token": token}) + "\\n")
    if os.path.exists(os.environ["FAKE_UPLOAD_LOG"] + ".fail"):
        sys.exit(1)
    print("https://github.com/user-attachments/assets/" + os.path.basename(path))
    ''')


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
        self._exe("gh", FAKE_GH)
        # without a token, fail the way reviewer-token does when the app isn't installed
        script = f"#!/bin/sh\necho {token}\n" if token else (
            "#!/bin/sh\necho 'reviewer-token: bot is not installed on o/r' >&2\n"
            f"echo 'install it: {INSTALL_URL}' >&2\nexit 1\n")
        self.token_cmd = self._exe("token", script)
        self.uploads = os.path.join(self.dir, "uploads.jsonl")
        self.upload_cmd = self._exe("upload", FAKE_UPLOAD)

    def cleanup(self):
        self._tmp.cleanup()

    def _exe(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, 0o755)
        return path

    def _write_table(self, table):
        with open(self.table, "w") as f:
            json.dump(table, f)

    def set_answer(self, key, stdout="", exit=0):
        with open(self.table) as f:
            table = json.load(f)
        table[key] = {"stdout": stdout, "exit": exit}
        self._write_table(table)

    def run(self, *args, check=True, input_text=""):
        isolated = {name: os.path.join(self.home, name.lower()) for name in
                    ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")}
        env = {**os.environ, **GIT_ENV, **isolated, "HOME": self.home,
               "PATH": self.dir + os.pathsep + os.environ["PATH"],
               "FAKE_GH_LOG": self.log, "FAKE_GH_TABLE": self.table,
               "PR_THREADS_TOKEN_CMD": self.token_cmd, "PR_THREADS_UPLOAD_CMD": self.upload_cmd,
               "FAKE_UPLOAD_LOG": self.uploads, "PYTHONPATH": PLUGIN}
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
