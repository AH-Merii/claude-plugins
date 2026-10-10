#!/usr/bin/env python3
"""Stands in for gh: records each request by what it means, answers from a routing table.

Routes: "pr view <n>", "repo view", "<METHOD> <endpoint part>" for REST, and
"graphql <field>" for GraphQL. Known review mutations are answered with their real
shape, so a reply or resolve never gets a thread listing back. GraphQL that GitHub
would reject (conflicting response names, a thread under the wrong input key) fails,
and so does a canned GraphQL answer holding a field the query doesn't select. A canned
reviewThreads list is served a page at a time, by the query's `first` and `after`, like
GitHub's connections. A key whose endpoint part ends in "$" only matches that exact endpoint.
An answer may carry stderr, printed as gh prints its errors.

Like real gh it expands {owner}/{repo} in api endpoints, builds nested payloads from
`key[sub]=v` and `key[]=v` fields, applies simple `.a.b` paths given to --jq/-q
(anything else fails loudly), and treats `gh issue comment N` as the POST to
issues/N/comments it is: it uploads any --attach as the user, puts the image in the
body, and prints the comment URL.
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

def fail(message, code=1):
    sys.stderr.write("fake gh: " + message + "\n")
    sys.exit(code)

def typed(value):
    """-F's magic conversion: @file (or @- for stdin), true/false/null, integers, {owner}/{repo}."""
    if value.startswith("@"):
        return sys.stdin.read() if value == "@-" else read(value[1:])
    if value in ("true", "false", "null"):
        return {"true": True, "false": False, "null": None}[value]
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    return value.replace("{owner}", OWNER).replace("{repo}", REPO)

def nest(fields):
    """Build the payload from (text, magic) fields the way gh's parseFields does.

    `key[sub]=v` nests an object, `key[]=v` appends to an array, `key[]` alone is an
    empty array, and `key[][sub]=v` starts a new array element once the last one already
    has `sub`. Setting a plain key twice is an error, as in gh.
    """
    params = {}
    for text, magic in fields:
        keystack, start, value_at = [], 0, 0
        for i, ch in enumerate(text):
            if ch == "[":
                if start == 0:
                    keystack.append(text[:i])
                start = i + 1
            elif ch == "]":
                keystack.append(text[start:i])
            elif ch == "=":
                if start == 0:
                    keystack.append(text[:i])
                value_at = i + 1
                break
        if not keystack:
            fail(f"invalid key: {text!r}")
        value = None
        if value_at == 0:
            if keystack[-1] != "":
                fail(f"field {text!r} requires a value separated by an '=' sign")
        else:
            value = text[value_at:]
            if magic:
                value = typed(value)
        dest, is_array, subkey = params, False, ""
        for k in keystack:
            if k == "":
                is_array = True
                continue
            if subkey:
                if is_array:
                    items = dest.setdefault(subkey, [])
                    if not isinstance(items, list):
                        fail(f"expected array type under {subkey!r}")
                    last = items[-1] if items else None
                    if isinstance(last, dict) and (k not in last or isinstance(last[k], list)):
                        dest = last
                    else:
                        dest = {}
                        items.append(dest)
                    is_array = False
                else:
                    child = dest.setdefault(subkey, {})
                    if not isinstance(child, dict):
                        fail(f"expected map type under {subkey!r}")
                    dest = child
            subkey = k
        if is_array:
            if value is None:
                dest[subkey] = []
            else:
                items = dest.setdefault(subkey, [])
                if not isinstance(items, list):
                    fail(f"expected array type under {subkey!r}")
                items.append(value)
        elif subkey in dest:
            fail(f"unexpected override existing field under {subkey!r}")
        else:
            dest[subkey] = value
    return params

def option(args, *names):
    for i, arg in enumerate(args[:-1]):
        if arg in names:
            return args[i + 1]
    return None

def jq(data, path):
    """The subset of jq the fake understands: `.` and `.a.b` field paths."""
    if path != "." and not re.fullmatch(r"(\.[A-Za-z_]\w*)+", path):
        sys.stderr.write("fake gh: unsupported --jq " + path)
        sys.exit(3)
    for key in [p for p in path.split(".") if p]:
        data = data[key]
    return data if isinstance(data, str) else json.dumps(data)

def parse(args):
    """Split gh args into (positionals, method, body).

    Takes options as `-X POST`, `-XPOST` or `--method=POST`, like gh's flag parser.
    """
    positionals, method, raw_fields, magic_fields, raw = [], None, [], [], None
    i = 0
    while i < len(args):
        arg, value, step = args[i], None, 1
        if arg in VALUE_OPTS and i + 1 < len(args):
            value, step = args[i + 1], 2
        elif arg.startswith("--") and arg.partition("=")[0] in VALUE_OPTS:
            arg, _, value = arg.partition("=")
        elif not arg.startswith("--") and arg[:2] in VALUE_OPTS and len(arg) > 2:
            arg, value = arg[:2], arg[2:]
        if value is not None:
            if arg in ("-X", "--method"):
                method = value.upper()
            elif arg in ("-f", "--raw-field"):
                raw_fields.append((value, False))
            elif arg in ("-F", "--field"):
                magic_fields.append((value, True))
            elif arg == "--input":
                raw = sys.stdin.read() if value == "-" else read(value)
        elif arg.startswith("-"):
            pass
        else:
            positionals.append(arg)
        i += step
    # gh adds every -f field before any -F field
    fields = nest(raw_fields + magic_fields)
    body = json.loads(raw) if raw else (fields or None)
    return positionals, method or ("POST" if body is not None else "GET"), body

def top_fields(query):
    """(alias, field, args text) for each top-level selection of the operation."""
    text = query[query.index("{") + 1:]
    found, depth, i = [], 0, 0
    name = re.compile(r"\s*(?:(\w+)\s*:\s*)?(\w+)")
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

# the input key GitHub's schema gives each review-thread mutation for the thread
THREAD_INPUT = {"resolveReviewThread": "threadId", "unresolveReviewThread": "threadId",
                "addPullRequestReviewThreadReply": "pullRequestReviewThreadId"}

def selections(query, variables):
    """Top-level selections, merged and checked the way GitHub validates them.

    Two selections with one response name (the alias, else the field name) are merged
    only when they are the same field with the same arguments; anything else is the
    fieldConflict GitHub rejects. Review-thread mutations must name their thread under
    the input key the schema gives them, as a literal or a $variable.
    """
    merged = {}
    for alias, field, field_args in top_fields(query):
        same = (field, " ".join(field_args.split()))
        if alias in merged and merged[alias][:2] != same:
            fail(f"Field '{alias}' has a field or argument conflict")
        merged[alias] = same + (field_args,)
    found = []
    for alias, (field, _, field_args) in merged.items():
        tid = thread_input(field, field_args, variables) if field in THREAD_INPUT else None
        found.append((alias, field, tid))
    return found

def thread_input(field, field_args, variables):
    key = THREAD_INPUT[field]
    whole = re.search(r"\binput\s*:\s*\$(\w+)", field_args)
    if whole:
        given = variables.get(whole.group(1))
        value = given.get(key) if isinstance(given, dict) else None
    else:
        m = re.search(r"\b" + key + r'\s*:\s*(?:"((?:[^"\\]|\\.)*)"|\$(\w+))', field_args)
        value = None if m is None else m.group(1) if m.group(1) is not None \
            else variables.get(m.group(2))
    if not isinstance(value, str) or not value:
        fail(f"{field} needs its thread as input.{key}")
    return value

MAX_PAGE = 100


def connection_args(query, field, variables):
    """(first, after) given to `field` in the query, as literals or $variables."""
    m = re.search(r"\b" + field + r"\s*\(([^)]*)\)", query)
    text = m.group(1) if m else ""

    def arg(name):
        found = re.search(r"\b" + name + r'\s*:\s*(?:"([^"]*)"|\$(\w+)|(\w+))', text)
        if not found:
            return None
        literal, var, bare = found.groups()
        value = variables.get(var) if var else literal if literal is not None else bare
        return None if value in (None, "null") else value

    return arg("first"), arg("after")


def page_threads(answer, query, variables):
    """Cut the canned reviewThreads down to the page the query asked for, as GitHub does.

    GitHub requires `first` (at most 100) and answers `after` an endCursor with the next
    page; pageInfo says whether more remain. Cursors here are "cursor:<index>".
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "reviewThreads" and isinstance(v, dict) and "nodes" in v:
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(answer.get("data"))
    for conn in found:
        first, after = connection_args(query, "reviewThreads", variables)
        if first is None:
            fail("You must provide a `first` or `last` value to properly paginate "
                 "the `reviewThreads` connection.")
        first = int(first)
        if not 0 <= first <= MAX_PAGE:
            fail(f"Requesting {first} records on the `reviewThreads` connection exceeds "
                 f"the `first` limit of {MAX_PAGE} records.")
        start = 0
        if after is not None:
            if not re.fullmatch(r"cursor:\d+", str(after)):
                fail(f"`{after}` does not appear to be a valid cursor.")
            start = int(after.split(":")[1])
        nodes = conn["nodes"]
        end = min(start + first, len(nodes))
        conn["nodes"] = nodes[start:end]
        conn["pageInfo"] = {"hasNextPage": end < len(nodes),
                            "endCursor": f"cursor:{end}" if end > start else None}


def mutation_answer(field, tid):
    if field == "resolveReviewThread":
        return {"thread": {"id": tid, "isResolved": True}}
    if field == "unresolveReviewThread":
        return {"thread": {"id": tid, "isResolved": False}}
    if field == "addPullRequestReviewThreadReply":
        return {"comment": {"id": "C_new", "url": "https://github.com/o/r/pull/5#discussion_rC_new"}}
    return None


def upload(path):
    """Upload an image as whoever the token says: logs the upload, returns the asset URL.

    gh issue comment --attach and the CLI's own upload command (PR_THREADS_UPLOAD_CMD)
    both come here, so they record and fail the same way.
    """
    with open(os.environ["FAKE_UPLOAD_LOG"], "a") as f:
        f.write(json.dumps({"file": path, "gh_token": token()}) + "\n")
    if os.path.exists(os.environ["FAKE_UPLOAD_LOG"] + ".fail"):
        fail(f"failed to upload {path}")
    return "https://github.com/user-attachments/assets/" + os.path.basename(path)


def main(args):
    if args[:2] == ["issue", "comment"]:
        positionals, method, text, attach, i = [], "POST", None, [], 2
        while i < len(args):
            arg, _, value = args[i].partition("=") if args[i].startswith("--") else (args[i], "", "")
            if arg in ("-b", "--body", "-F", "--body-file", "--attach", "-R", "--repo") and not value:
                value, i = args[i + 1], i + 1
            if arg in ("-b", "--body"):
                text = value
            elif arg in ("-F", "--body-file"):
                text = sys.stdin.read() if value == "-" else read(value)
            elif arg == "--attach":
                attach.append(value)
            elif not arg.startswith("-"):
                positionals.append(arg)
            i += 1
        text = text or ""
        # gh uploads each --attach as the user first, then rewrites a reference to it in
        # the body or appends the image; a failed upload means nothing is posted
        for item in attach:
            path, _, alt = item.partition("#")
            if not os.path.isfile(path):
                fail(f"{path}: no such file")
            url = upload(path)
            if f"]({path})" in text:
                text = text.replace(f"]({path})", f"]({url})")
            else:
                text += f"\n\n![{alt or os.path.basename(path)}]({url})"
        body = {"body": text}
    else:
        positionals, method, body = parse(args[1:] if args[:1] == ["api"] else args)
    if args[:1] == ["api"] and positionals:
        positionals[0] = positionals[0].replace("{owner}", OWNER).replace("{repo}", REPO)
    record = {"argv": args, "method": None, "endpoint": None, "body": body, "fields": [],
              "threads": [], "gh_token": token()}
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
        # with --input the body is the request itself; otherwise gh sends fields as variables
        if option(args, "--input") is not None:
            variables = (body or {}).get("variables") or {}
        else:
            variables = {k: v for k, v in (body or {}).items() if k not in ("query", "operationName")}
    elif args[:1] == ["api"] and positionals:
        record.update(method=method, endpoint=positionals[0])
        route = f"{method} {positionals[0]}"
    else:
        route = " ".join(args)
    record["route"] = route

    def log(**extra):
        with open(os.environ["FAKE_GH_LOG"], "a") as f:
            f.write(json.dumps({**record, **extra}) + "\n")

    picked = []
    if record["endpoint"] == "graphql" and "{" in query:
        try:
            picked = selections(query, variables)
        except SystemExit:
            log(rejected=True)
            raise
        # which thread each review-thread mutation named, under the schema's own key
        record["threads"] = [tid for _, field, tid in picked if field in THREAD_INPUT]
    log()

    def rest_match(key):
        verb, _, part = key.partition(" ")
        if not route.startswith(verb + " "):
            return False
        if part.endswith("$"):
            return route.rstrip("/").endswith(part[:-1])
        return part in route

    def unselected(answer, query):
        """Keys of a canned GraphQL answer that the query never selects.

        GitHub only returns what a query asks for, so a test can only rely on a fixture
        key (isOutdated, originalStartLine, oid, pageInfo, ...) the query names.
        """
        missing = set()
        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if not re.search(r"\b" + re.escape(k) + r"\b", query):
                        missing.add(k)
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(answer.get("data"))
        return sorted(missing)

    def answer_with(stdout, code):
        path = option(args, "--jq", "-q")
        if path is not None and code == 0 and stdout:
            stdout = jq(json.loads(stdout), path) + "\n"
        sys.stdout.write(stdout)
        sys.exit(code)

    def answer_pages(pages):
        """A paginated REST answer, one JSON array per page, oldest items first.

        Without --paginate gh gets page 1 only. With it gh fetches every page and joins
        the arrays into one, prints each page through --jq, or wraps them with --slurp.
        """
        if "--paginate" not in args:
            answer_with(pages[0], 0)
        path = option(args, "--jq", "-q")
        if path is not None:
            sys.stdout.write("".join(jq(json.loads(page), path) + "\n" for page in pages))
        elif "--slurp" in args:
            sys.stdout.write(json.dumps([json.loads(page) for page in pages]))
        else:
            sys.stdout.write(json.dumps([item for page in pages for item in json.loads(page)]))
        sys.exit(0)

    with open(os.environ["FAKE_GH_TABLE"]) as f:
        table = json.load(f)
    for key, answer in table.items():
        if key == route or (key.startswith(("GET ", "POST ", "PATCH ", "PUT ", "DELETE "))
                            and rest_match(key)) \
                or (key.startswith("graphql ") and record["endpoint"] == "graphql"
                    and re.search(r"\b" + re.escape(key[8:]) + r"\b", (body or {}).get("query", ""))):
            if "pages" in answer:
                answer_pages(answer["pages"])
            stdout, code = answer.get("stdout", ""), answer.get("exit", 0)
            sys.stderr.write(answer.get("stderr", ""))
            if args[:2] == ["issue", "comment"]:
                # gh issue comment prints the new comment's URL, not the API's JSON
                stdout = json.loads(stdout)["html_url"] + "\n" if code == 0 and stdout else ""
            if record["endpoint"] == "graphql" and code == 0 and stdout:
                paged = json.loads(stdout)
                page_threads(paged, query, variables)
                stdout = json.dumps(paged)
                missing = unselected(paged, query)
                if missing:
                    fail("the query never selects " + ", ".join(missing))
            answer_with(stdout, code)
    if record["endpoint"] == "graphql":
        data = {}
        for alias, field, tid in picked:
            answer = mutation_answer(field, tid)
            if answer is None:
                break
            data[alias] = answer
        else:
            if data:
                answer_with(json.dumps({"data": data}), 0)
    sys.stderr.write("fake gh: no answer for " + route)
    sys.exit(1)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--upload"]:
        # the stand-in for PR_THREADS_UPLOAD_CMD: `upload <path>` prints the asset URL
        print(upload(sys.argv[2]))
    else:
        main(sys.argv[1:])
