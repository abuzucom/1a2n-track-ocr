#!/usr/bin/env python3
"""Block obviously destructive Bash commands via a Claude Code PreToolUse hook.

Not part of AGENTS.md, which stays tool-agnostic and is synced to non-Claude
tools verbatim. This is a Claude-Code-specific example under hooks/, opt-in
only, wired via a project or user `settings.json` (see
hooks/claude-code-settings.example.json). Reads the PreToolUse JSON payload
from stdin, checks only Bash tool calls, and exits 2 (blocking, per Claude
Code's PreToolUse contract) with a reason on stderr when the command matches
`rm -rf` targeting `/`, `~`, or `$HOME`, a bare `git push --force`/`-f`, or
`git reset --hard`.

A heuristic, not a sandbox: broad on purpose, since a false positive here is
far cheaper than a missed destructive command. It does not parse the shell,
so a command hidden behind a variable, alias, or wrapper script is invisible
to it.
"""
import json
import re
import sys


def _has_flag(command: str, letter: str, long_name: str) -> bool:
    """Return True if a short flag token containing `letter` or `long_name` appears."""
    if re.search(rf"(?<!\S)-[a-zA-Z]*{re.escape(letter)}[a-zA-Z]*(?!\S)", command):
        return True
    return long_name in command


def find_reason(command: str) -> str:
    """Return why `command` is destructive, or an empty string if it is not."""
    if re.search(r"\brm\b", command):
        has_recursive = _has_flag(command, "r", "--recursive")
        has_force = _has_flag(command, "f", "--force")
        has_root_target = re.search(r"(?:^|\s)(/|~|\$HOME)(?:\s|/|$)", command)
        if has_recursive and has_force and has_root_target:
            return "rm -rf targeting / or the home directory"
    if re.search(r"\bgit\s+push\b", command) and re.search(r"(?<!\S)(--force|-f)(?!\S)", command):
        return "git push --force"
    if re.search(r"\bgit\s+reset\s+--hard\b", command):
        return "git reset --hard"
    return ""


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    reason = find_reason(command)
    if reason:
        print(f"blocked by hooks/block_destructive_bash.py: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
