"""Count words and report the most common ones."""

import re
from collections import Counter

WORD = re.compile(r"[a-z']+")


def count(text: str) -> Counter:
    return Counter(WORD.findall(text.lower()))


def top(text: str, n: int = 3) -> list[tuple[str, int]]:
    return sorted(count(text).items(), key=lambda kv: (-kv[1], kv[0]))[:n]
