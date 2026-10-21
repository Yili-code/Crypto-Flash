"""Codex startup sync. Standard library only; never commits, pushes or stashes."""
import json
import os
from pathlib import Path
import subprocess
import sys


def git(cwd, *args, timeout=15):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, env=env)
    if proc.returncode:
        # Do not echo stderr: remote URLs can contain credentials.
        raise RuntimeError("git " + args[0] + " failed; inspect locally without exposing credentials")
    return proc.stdout.strip()


def sync(cwd):
    root = Path(git(cwd, "rev-parse", "--show-toplevel"))
    common = Path(git(root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = root / common
    lock = common / "codex-session-sync.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return "SYNC BUSY: another check holds the repository lock. Retry before editing. Do not delete a live lock."
    try:
        os.close(fd)
        branch = git(root, "branch", "--show-current")
        if not branch:
            return "DETACHED HEAD: no automatic sync. Read AGENTS.md and project handoffs; confirm intended branch."
        remote = git(root, "config", "--get", "branch." + branch + ".remote")
        if not remote or remote == ".":
            return "NO REMOTE UPSTREAM: configure tracking explicitly; no automatic sync performed."
        git(root, "fetch", "--quiet", remote, timeout=25)
        ahead, behind = map(int, git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}").split())
        dirty = bool(git(root, "status", "--porcelain"))
        if ahead and behind:
            state = "DIVERGED: preserve both histories; reconcile before implementation."
        elif behind and dirty:
            state = "BLOCKED: local changes exist and remote is newer. Preserve local work; reconcile before implementation."
        elif behind:
            # Git also refuses concurrent/index conflicts. Never force or auto-stash.
            git(root, "merge", "--ff-only", "@{upstream}")
            state = "FAST-FORWARDED to upstream. Re-read AGENTS.md because files may have changed."
        elif ahead:
            state = "LOCAL AHEAD: commits are not yet shared. Inspect before any push."
        else:
            state = "COMMIT HISTORY CURRENT" + ("; uncommitted local work is NOT shared." if dirty else "; clean working tree.")
        head = git(root, "rev-parse", "--short", "HEAD")
        return (f"{state}\nBranch={branch}; HEAD={head}; before sync: ahead={ahead}, behind={behind}.\n"
                "Read PROJECT_STATUS.md, relevant docs/handoffs/*.md and actual changed files. "
                "Old conversations and dated summaries are not proof of current implementation. "
                "Before ending a turn with material work, update your own handoff with decisions, evidence and next steps. "
                "Never claim another machine is synchronized without verification. "
                "This lock serializes sync checks only; it does not lock other agents' edits.")
    finally:
        lock.unlink(missing_ok=True)


def main():
    payload = {}
    if "--manual" not in sys.argv:
        try:
            payload = json.load(sys.stdin)
        except (ValueError, OSError):
            pass
    try:
        message = sync(payload.get("cwd") or os.getcwd())
    except Exception as exc:
        message = ("SYNC NOT VERIFIED: " + type(exc).__name__ + ". "
                   "Inspect Git tracking, network and permissions. Do not assume current remote state or overwrite local work. "
                   "Read AGENTS.md and relevant handoffs before continuing.")
    event = payload.get("hook_event_name", "SessionStart")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                             "additionalContext": message}}, ensure_ascii=True))


if __name__ == "__main__":
    main()
