#!/usr/bin/env python3
"""SessionStart hook: keep the GitButler `but` skill in step with the installed `but` CLI.

`but` generates its skill and stamps it with the CLI version, so the skill is never vendored
here. When the copy in this Claude config's skills folder is missing or its version differs
from `but --version`, reinstall it from the CLI. Does nothing when `but` is not installed.
"""
import os
import re
import shutil
import subprocess
import sys


def cli_version(but):
    out = subprocess.run([but, "--version"], capture_output=True, text=True, timeout=10)
    match = re.search(r"\d+\.\d+\.\d+\S*", out.stdout)
    return match.group(0) if match else None


def skill_version(skill_md):
    try:
        with open(skill_md, encoding="utf-8") as f:
            text = f.read(4096)
    except OSError:
        return None
    match = re.search(r"^---\n.*?^version:\s*\"?([^\s\"]+)", text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else None


def main():
    but = shutil.which("but")
    if not but:
        return 0
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    target = os.path.join(config_dir, "skills", "gitbutler")
    try:
        want = cli_version(but)
        have = skill_version(os.path.join(target, "SKILL.md"))
        if not want or want == have:
            return 0
        result = subprocess.run(
            [but, "skill", "install", "--path", target],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if result.returncode == 0:
        action = f"updated from {have}" if have else "installed"
        print(f"gitbutler-guard: GitButler skill {action} to {want} at {target}.")
    else:
        print(f"gitbutler-guard: `but skill install --path {target}` failed: {result.stderr.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
