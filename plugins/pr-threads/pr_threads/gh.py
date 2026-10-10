"""The only place pr-threads talks to GitHub: gh, the bot's token command and the upload command.

Reads and the author's writes go out as the user's own gh login. The reviewer's writes
(submit, resolve) carry the bot's token in GH_TOKEN.
"""
import json
import os
import shlex
import subprocess

from pr_threads import Refusal

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TOKEN_CMD = os.path.join(PLUGIN, "bin", "reviewer-token")


class GhError(Refusal):
    pass


def gh(*args, token=None, stdin=None):
    env = dict(os.environ, GH_TOKEN=token) if token else None
    out = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, env=env)
    if out.returncode:
        raise GhError(out.stderr.strip() or f"gh {' '.join(args[:2])} failed")
    return out.stdout


def graphql(query, token=None, jq=None, **variables):
    args = ["api", "graphql", "-f", f"query={query}"]
    for name, value in variables.items():
        if value is not None:
            args += ["-F" if isinstance(value, int) else "-f", f"{name}={value}"]
    if jq:
        args += ["--jq", jq]
    out = gh(*args, token=token)
    return out.strip() if jq else json.loads(out)


def _command(env_name, default=None):
    cmd = os.environ.get(env_name) or default
    return shlex.split(cmd) if cmd else None


def bot_token(repo):
    """A short-lived token for the reviewer bot on `repo`, or a Refusal saying how to set it up."""
    out = subprocess.run([*_command("PR_THREADS_TOKEN_CMD", DEFAULT_TOKEN_CMD), repo],
                         capture_output=True, text=True)
    token = out.stdout.strip()
    if out.returncode or not token:
        raise Refusal("the reviewer bot can't act on this repo, so nothing was sent.\n"
                      + (out.stderr.strip() or "its token command printed no token"))
    return token


def upload(path):
    """Upload an image as the user and return its asset URL."""
    cmd = _command("PR_THREADS_UPLOAD_CMD")
    if not cmd:
        raise Refusal("--attach needs PR_THREADS_UPLOAD_CMD: a command that takes a file path, "
                      "uploads it with your GitHub login and prints the asset URL")
    out = subprocess.run([*cmd, path], capture_output=True, text=True)
    url = out.stdout.strip()
    if out.returncode or not url:
        raise Refusal(f"uploading {path} failed: {out.stderr.strip()}")
    return url


def repo():
    return gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner").strip()


def pull_request(number=None):
    """The PR's number, base and head commits and head branch (the current branch's PR by default)."""
    which = [str(number)] if number else []
    return json.loads(gh("pr", "view", *which, "--json",
                         "number,baseRefOid,headRefOid,headRefName"))


def submit_review(repo, number, review, token):
    return gh("api", "-X", "POST", f"repos/{repo}/pulls/{number}/reviews", "--input", "-",
              "--jq", ".html_url", token=token, stdin=json.dumps(review)).strip()


def reviews(repo, number):
    """Every submitted review on the PR, oldest first."""
    return json.loads(gh("api", f"repos/{repo}/pulls/{number}/reviews", "--paginate") or "[]")


THREADS = """query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { %s }
      }
    }
  }
}"""


def review_threads(repo, number, fields):
    """Every review thread of the PR with `fields` selected, as one reviewThreads response."""
    owner, name = repo.split("/")
    nodes, after = [], None
    while True:
        page = graphql(THREADS % fields, owner=owner, name=name, number=int(number), after=after)
        conn = page["data"]["repository"]["pullRequest"]["reviewThreads"]
        nodes += conn["nodes"]
        if not conn["pageInfo"]["hasNextPage"]:
            conn["nodes"] = nodes
            return page
        after = conn["pageInfo"]["endCursor"]


REPLY = """mutation($thread: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $thread, body: $body}) {
    comment { url }
  }
}"""


def reply(thread, body):
    return graphql(REPLY, thread=thread, body=body,
                   jq=".data.addPullRequestReviewThreadReply.comment.url")


def resolve(threads, token):
    """Resolve every thread in one request, each under its own alias."""
    params = ", ".join(f"$t{i}: ID!" for i in range(len(threads)))
    fields = "\n".join(f"  t{i}: resolveReviewThread(input: {{threadId: $t{i}}}) {{ thread {{ id }} }}"
                       for i in range(len(threads)))
    graphql(f"mutation({params}) {{\n{fields}\n}}", token=token,
            **{f"t{i}": t for i, t in enumerate(threads)})


def post(number, body, attach=()):
    """A general comment on issue or PR `number` as the user; gh uploads each --attach itself."""
    args = ["issue", "comment", str(number), "--body-file", "-"]
    for item in attach:
        args += ["--attach", item]
    return gh(*args, stdin=body).strip()
