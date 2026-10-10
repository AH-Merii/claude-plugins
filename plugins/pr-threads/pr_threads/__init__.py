"""pr-threads: review a GitHub PR as threads pinned to local path:line."""


class Refusal(Exception):
    """A request pr-threads turns down before (or instead of) touching GitHub; str() says why."""
