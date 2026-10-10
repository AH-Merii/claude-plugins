"""The handoff between reviewer and author, read straight off the PR's reviews and threads."""
from pr_threads.threads import nodes

VERDICTS = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}


def handoff(response, reviews):
    """{"state": pending|changes|approved|pass, "open": unresolved thread count}.

    Each reviewer's latest formal review counts, as on GitHub: COMMENTED and PENDING
    reviews change no one's standing, and a DISMISSED one leaves its reviewer with none.
    """
    latest = {}
    for review in reviews:  # GitHub lists them oldest first
        if review.get("state") in VERDICTS and review.get("submitted_at"):
            latest[review["user"]["login"]] = review["state"]
    open_count = sum(not t["isResolved"] for t in nodes(response))
    standing = set(latest.values())
    if "CHANGES_REQUESTED" in standing:
        state = "changes"
    elif "APPROVED" in standing:
        state = "approved" if open_count else "pass"
    else:
        state = "pending"
    return {"state": state, "open": open_count,
            "changes_requested_by": sorted(k for k, v in latest.items() if v == "CHANGES_REQUESTED"),
            "approved_by": sorted(k for k, v in latest.items() if v == "APPROVED")}


def render(got):
    line = f"{got['state']}: {got['open']} open thread{'' if got['open'] == 1 else 's'}"
    if got["changes_requested_by"]:
        line += "; changes requested by " + ", ".join(got["changes_requested_by"])
    elif got["approved_by"]:
        line += "; approved by " + ", ".join(got["approved_by"])
    return line
