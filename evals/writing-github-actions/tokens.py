"""Token use of one `claude -p --output-format stream-json --verbose` run.

Sums usage over assistant messages deduplicated by message.id (a message streamed in
several events carries the same usage each time), and reports the result event's cost.
Prints JSON: input, cache_creation, cache_read, output, total, cost_usd, turns, skills.
"""

import json
import sys

seen, totals, skills = set(), {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0}, []
cost, turns = None, None
with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
    lines = f.readlines()
for line in lines:
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if ev.get("type") == "assistant":
        msg = ev.get("message") or {}
        for block in msg.get("content") or []:
            if block.get("type") == "tool_use" and block.get("name") == "Skill":
                skills.append((block.get("input") or {}).get("skill"))
        mid = msg.get("id")
        if mid in seen:
            continue
        seen.add(mid)
        u = msg.get("usage") or {}
        totals["input"] += u.get("input_tokens", 0) or 0
        totals["cache_creation"] += u.get("cache_creation_input_tokens", 0) or 0
        totals["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
        totals["output"] += u.get("output_tokens", 0) or 0
    elif ev.get("type") == "result":
        cost, turns = ev.get("total_cost_usd"), ev.get("num_turns")
totals["total"] = sum(totals.values())
print(json.dumps({**totals, "cost_usd": cost, "turns": turns, "messages": len(seen), "skills": skills}))
