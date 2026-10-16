"""Local pre-push guard: the remote is public.

    python tools/pre_push.py --install      install .git/hooks/pre-push
    python tools/pre_push.py --check-all    scan every commit not on a remote yet
    (as the hook, git passes "<remote> <url>" and ref lines on stdin)

Refuses the push when the commits it sends
  - add or change a file under .github/readme-* other than .github/readme-lofi/
    (the other readme folders are the user's local drafts), or
  - add a line that looks like a credential: a known token shape, a private
    key, a long value assigned to something named key/token/secret/password,
    or any value listed in .git/at-secret-values (one per line; that file
    lives in .git, so it is never committed or pushed).
Findings are printed with file and line but never with the matched value.
"""

import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZERO = "0" * 40
ALLOWED_README = ".github/readme-lofi/"
HOOK = """#!/bin/sh
# installed by tools/pre_push.py --install
exec python "$(git rev-parse --show-toplevel)/tools/pre_push.py" "$@"
"""
PATTERNS = [
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{24,}")),
    ("assigned secret", re.compile(r"(?i)\b[\w-]*(api[_-]?key|secret|token|passw(or)?d)\b[\"']?\s*[:=]\s*[\"']?(?![<{$])[A-Za-z0-9_./+=-]{20,}")),
]


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.decode("utf-8", "replace")


def secret_values():
    path = os.path.join(REPO, ".git", "at-secret-values")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [line.strip() for line in handle if len(line.strip()) >= 8]


def ranges_from_stdin(stdin):
    """Commit ranges git is about to push, as rev-list arguments."""
    ranges = []
    for line in stdin.read().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, _remote_ref, remote_sha = parts
        if local_sha == ZERO:
            continue  # a deletion sends no content
        if remote_sha == ZERO:
            ranges.append([local_sha, "--not", "--remotes"])
        else:
            ranges.append(["%s..%s" % (remote_sha, local_sha)])
    return ranges


def scan(ranges):
    values = secret_values()
    findings = []
    for rev in ranges:
        commits = [c for c in git("rev-list", *rev).split() if c]
        for commit in commits:
            for path in git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit).splitlines():
                if path.startswith(".github/readme-") and not path.startswith(ALLOWED_README):
                    findings.append("%s %s: local README draft folder (only %s may be pushed)" % (commit[:8], path, ALLOWED_README))
            current, line_no = None, 0
            for line in git("show", "--format=", "--unified=0", "--no-color", "--root", commit).splitlines():
                if line.startswith("+++ "):
                    current = line[6:] if line.startswith("+++ b/") else None
                    continue
                if line.startswith("@@"):
                    m = re.search(r"\+(\d+)", line)
                    line_no = int(m.group(1)) if m else 0
                    continue
                if not line.startswith("+") or current is None:
                    continue
                added = line[1:]
                for label, pattern in PATTERNS:
                    if pattern.search(added):
                        findings.append("%s %s:%d: looks like a %s" % (commit[:8], current, line_no, label))
                        break
                else:
                    if any(v in added for v in values):
                        findings.append("%s %s:%d: contains a value from .git/at-secret-values" % (commit[:8], current, line_no))
                line_no += 1
    return findings


def main(argv):
    if "--install" in argv:
        target = os.path.join(REPO, ".git", "hooks", "pre-push")
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(HOOK)
        os.chmod(target, 0o755)
        print("installed %s" % os.path.relpath(target, REPO))
        return 0
    ranges = [["HEAD", "--not", "--remotes"]] if "--check-all" in argv else ranges_from_stdin(sys.stdin)
    findings = scan(ranges)
    if findings:
        sys.stderr.write("pre-push: refused, the remote is public:\n")
        for f in findings:
            sys.stderr.write("  %s\n" % f)
        sys.stderr.write("Fix the commits (or unstage the files) before pushing.\n")
        return 1
    print("pre-push: %d range(s) scanned, nothing found" % len(ranges))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
