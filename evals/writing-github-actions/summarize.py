"""Summarise one round: pass count, median tokens and cost per scenario and arm.

usage: summarize.py <round dir>
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

cells = defaultdict(list)
for d in sorted(Path(sys.argv[1]).glob("*-*-*")):
    if not (d / "tokens.json").exists():
        continue
    arm, rest = d.name.split("-", 1)
    scenario = rest.rsplit("-", 1)[0]
    tokens = json.loads((d / "tokens.json").read_text())
    check = (d / "check.txt").read_text().splitlines()
    fails = [line.split()[1].rstrip(":") for line in check if line.startswith("FAIL ")]
    cells[(scenario, arm)].append((check[-1] == "RESULT PASS", tokens, fails))

print("scenario     arm      pass  median tokens  median output  cost (all runs)  failed checks")
for (scenario, arm), runs in sorted(cells.items()):
    passed = sum(ok for ok, _, _ in runs)
    total = statistics.median(t["total"] for _, t, _ in runs)
    output = statistics.median(t["output"] for _, t, _ in runs)
    cost = sum(t["cost_usd"] or 0 for _, t, _ in runs)
    fails = sorted({f for _, _, fs in runs for f in fs})
    print(
        f"{scenario:12} {arm:8} {passed}/{len(runs)}  {total:>13,.0f}  {output:>13,.0f}"
        f"  ${cost:>14.3f}  {', '.join(fails) or '-'}"
    )
