"""The only place pr-threads talks to GitHub: gh, the bot's token command and the upload command.

Reads, the author's writes and resolve go out as the user's own gh login. The bot's
writes (submit, verify, withdraw, dispute) carry its token in GH_TOKEN.
"""
import functools
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


IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}


def upload(path):
    """Upload an image with the user's gh login and return its asset URL.

    PR_THREADS_UPLOAD_CMD, given the path, replaces this. The default does what gh's own
    --attach does (cli/cli internal/attachments/client.go): one POST of the file to
    uploads.github.com/user-attachments/assets, an endpoint GitHub doesn't document, which
    answers with the asset URL and posts nothing. It needs write access to the repo, and an
    asset can't be deleted, so callers upload only once nothing else can refuse the request.
    """
    cmd = _command("PR_THREADS_UPLOAD_CMD")
    if cmd:
        out = subprocess.run([*cmd, path], capture_output=True, text=True)
        url = out.stdout.strip()
        if out.returncode or not url:
            raise Refusal(f"uploading {path} failed: {out.stderr.strip()}")
        return url
    kind = IMAGE_TYPES.get(os.path.splitext(path)[1].lower())
    if kind is None:
        raise Refusal(f"--attach {path}: only {', '.join(IMAGE_TYPES)} images can be attached")
    try:
        return gh("api", "-X", "POST", "https://uploads.github.com/user-attachments/assets",
                  "--input", path, "-H", "Content-Type: application/octet-stream",
                  "-H", "Accept: application/vnd.github+json", "-f", f"name={os.path.basename(path)}",
                  "-f", f"content_type={kind}", "-f", f"repository_id={repo_id()}",
                  "--jq", ".url").strip()
    except GhError as e:
        raise Refusal(f"uploading {path} failed (it needs write access to the repo): {e}") from None


@functools.cache
def repo_id():
    """The current repo's numeric REST id, which the upload endpoint files assets under."""
    return gh("api", "repos/{owner}/{repo}", "--jq", ".id").strip()


def repo():
    return gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner").strip()


def pull_request(number=None):
    """The PR's number, base and head commits and head branch (the current branch's PR by default)."""
    which = [str(number)] if number else []
    try:
        return json.loads(gh("pr", "view", *which, "--json",
                             "number,baseRefOid,headRefOid,headRefName"))
    except GhError as e:
        if number:
            raise
        # a GitButler workspace is always on gitbutler/workspace, which has no PR
        raise Refusal(f"{e}\nthe current branch has no PR: pass its number with --pr N") from None


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


def reply(thread, body, token=None):
    return graphql(REPLY, token=token, thread=thread, body=body,
                   jq=".data.addPullRequestReviewThreadReply.comment.url")


def resolve(threads):
    """Resolve every thread in one request, each under its own alias, as the user.

    Not as the bot: GitHub refuses resolveReviewThread from an app without contents:write.
    """
    params = ", ".join(f"$t{i}: ID!" for i in range(len(threads)))
    fields = "\n".join(f"  t{i}: resolveReviewThread(input: {{threadId: $t{i}}}) {{ thread {{ id }} }}"
                       for i in range(len(threads)))
    graphql(f"mutation({params}) {{\n{fields}\n}}",
            **{f"t{i}": t for i, t in enumerate(threads)})


def post(number, body, attach=()):
    """A general comment on issue or PR `number` as the user; gh uploads each --attach itself."""
    args = ["issue", "comment", str(number), "--body-file", "-"]
    for item in attach:
        args += ["--attach", item]
    return gh(*args, stdin=body).strip()
