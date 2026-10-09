"""Push the current branch to both project remotes and verify their tips."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REMOTES = ("gitee", "github")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)


def sync():
    branch_result = git("symbolic-ref", "--quiet", "--short", "HEAD")
    if branch_result.returncode:
        print("ERROR: Check out a branch before syncing.")
        return 1
    branch = branch_result.stdout.strip()
    head_result = git("rev-parse", "HEAD")
    if head_result.returncode:
        print("ERROR: No committed revision to sync.")
        return 1
    head = head_result.stdout.strip()
    failed = False
    for remote in REMOTES:
        push = git("push", remote, f"HEAD:refs/heads/{branch}", "--follow-tags")
        if push.returncode:
            print(f"FAIL {remote}: {push.stderr.strip()}")
            failed = True
            continue
        check = git("ls-remote", remote, f"refs/heads/{branch}")
        rows = check.stdout.split()
        if check.returncode or not rows or rows[0] != head:
            print(f"FAIL {remote}: Could not verify remote tip matches {head}.")
            failed = True
        else:
            print(f"OK {remote}: {branch} -> {head}")
    if failed:
        print("Sync incomplete. Resolve the failed remote and run this script again.")
        return 1
    print("Both remotes match the local commit. Uncommitted changes are not uploaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(sync())
