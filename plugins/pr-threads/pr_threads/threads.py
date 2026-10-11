"""Review threads as the author works through them: open ones only, at local path:line."""

FIELDS = (
    "id isResolved isOutdated path line startLine originalLine originalStartLine "
    "comments(first: 100) { nodes { author { login } body originalCommit { oid } } }"
)


def nodes(response):
    return response["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]


def open_threads(response):
    """Unresolved threads; an outdated one keeps the lines it had in the reviewed commit."""
    found = []
    for t in nodes(response):
        if t["isResolved"]:
            continue
        old = t["isOutdated"]
        found.append(
            {
                "id": t["id"],
                "path": t["path"],
                "outdated": old,
                "line": t["originalLine"] if old else t["line"],
                "start_line": t["originalStartLine"] if old else t["startLine"],
                "comments": [
                    {"author": (c.get("author") or {}).get("login"), "body": c["body"]} for c in t["comments"]["nodes"]
                ],
            }
        )
    return found


def where(thread):
    start, line = thread["start_line"], thread["line"]
    return f"{thread['path']}:{start}-{line}" if start and start != line else f"{thread['path']}:{line}"


def render(threads):
    if not threads:
        return "no open threads"
    out = []
    for t in threads:
        flag = "  (outdated: line is from the reviewed commit; the code has changed since)" if t["outdated"] else ""
        out.append(f"{t['id']}  {where(t)}{flag}")
        for c in t["comments"]:
            body = c["body"].replace("\r\n", "\n").strip().replace("\n", "\n    ")
            out.append(f"  {c['author']}: {body}")
    return "\n".join(out)
