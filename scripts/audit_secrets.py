"""Search the whole git history for keys and secret files before the repo goes public (STU-D05-BE).

The plan's checklist: "No keys, passwords or personal data in code, history, video or project
page." Deleting a key in a later commit doesn't remove it: every old commit stays readable once
the repo is public, so this reads every commit on every branch.

    uv run python scripts/audit_secrets.py

Exit code 1 if a key-shaped string or a secret file is found. Matches are printed masked
(first 4 characters and the length), so running this never puts a key on screen.
"""

import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger("audit_secrets")

# Shapes of real secrets. Each is specific enough that normal code doesn't match.
KEY_PATTERNS = {
    "OpenAI key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
# A name like api_key / X-API-Key / SECRET / token followed by = or : and a long literal value.
# Our own API_KEY (from secrets.token_urlsafe) has no fixed shape, so this is how it would show
# up: API_KEY=..., "X-API-Key": "...", -H "X-API-Key: ...", api_key = "...". (?i) = any case.
ASSIGNMENT = re.compile(
    r"(?i)\b[\w-]*(?:api[_-]?key|secret|token|password)\b[\"']?\s*[=:]\s*[\"']?"
    r"([^\s\"'#,)}]{8,})"
)
# Values that look like an assignment but are known to be harmless.
SAFE_VALUES = {
    "your_api_key_here",  # the placeholder in .env.example
    "ci-only-throwaway-key",  # the CI server's test key (.github/workflows/ci.yml)
}
# File names that should never be committed (.env.example is the safe template).
# secrets.toml is Streamlit's secrets file (git-ignored here, .streamlit/secrets.toml).
SECRET_FILE = re.compile(
    r"(^|/)(\.env(\.[^/]+)?|id_rsa[^/]*|[^/]+\.pem|[^/]+\.key|secrets\.toml)$"
)


@dataclass(frozen=True)
class Finding:
    commit: str
    kind: str
    masked: str  # never the full value


def mask(value: str) -> str:
    return f"{value[:4]}… ({len(value)} characters)"


def scan_line(commit: str, line: str) -> list[Finding]:
    """Key-shaped strings in one added line of a diff ("+..."); [] = nothing found."""
    findings = []
    for kind, pattern in KEY_PATTERNS.items():
        findings += [
            Finding(commit, kind, mask(m.group(0))) for m in pattern.finditer(line)
        ]
    for match in ASSIGNMENT.finditer(line):
        value = match.group(1)
        # Skip code that reads a setting (os.getenv(...), a variable name). Generated keys
        # contain digits, so a value with none is treated as code. A heuristic: a digit-free
        # password would be missed, which the KEY_PATTERNS above don't cover either.
        if (
            value in SAFE_VALUES
            or not re.search(r"[0-9]", value)
            or value.startswith("os.")
        ):
            continue
        findings.append(Finding(commit, "assigned secret", mask(value)))
    return findings


def scan_history(log_text: str) -> list[Finding]:
    """Scan `git log -p` output; only added lines can bring a secret into the history."""
    findings: list[Finding] = []
    commit = "?"
    for line in log_text.splitlines():
        if line.startswith("COMMIT "):
            commit = line.split()[1]
        elif line.startswith("+") and not line.startswith("+++"):
            findings += scan_line(commit, line)
    return sorted(set(findings), key=lambda f: (f.commit, f.kind, f.masked))


def secret_files(paths: list[str]) -> list[str]:
    """Paths that look like a secret file; [] = none."""
    return sorted(
        {p for p in paths if SECRET_FILE.search(p) and not p.endswith(".env.example")}
    )


def public_emails(emails: set[str]) -> set[str]:
    """Commit emails that are a person's real address (shown publicly with the history)."""
    # users.noreply.github.com = a person's private GitHub address. noreply@github.com = GitHub
    # itself, as the committer of merges made on the website.
    return {
        e
        for e in emails
        if not e.endswith("@users.noreply.github.com") and e != "noreply@github.com"
    }


def git(*args: str) -> str:
    # check=True: if git fails, stop with its error instead of reporting "nothing found".
    # errors="replace": a file in another encoding (e.g. a Windows CSV) shows odd characters
    # instead of crashing the whole audit. Key shapes are plain ASCII, so they still match.
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
    commits = git("rev-list", "--all").split()
    # --all = every local branch and every fetched remote ref (docs/release-checklist.md says
    # how to fetch GitHub's pull request refs too, which become public with the repo).
    logger.info("Scanning %d commits on every local and fetched ref", len(commits))

    # --diff-merges=remerge: a merge commit's own changes (e.g. a conflict fixed by hand) show
    # as normal "+" lines. Plain `git log -p` shows no diff for merges at all.
    findings = scan_history(
        git(
            "log",
            "--all",
            "-p",
            "--diff-merges=remerge",
            "--no-color",
            "--format=COMMIT %h",
        )
    )
    for f in findings:
        logger.error("KEY   %s  %s  %s", f.commit, f.kind, f.masked)

    # Every path that ever existed: added, renamed (git mv notes.txt .env) or changed in a
    # merge (-m). splitlines, not split: a file name can contain a space.
    paths = git("log", "--all", "-m", "--name-only", "--format=").splitlines()
    files = secret_files([path for path in paths if path])
    for path in files:
        logger.error("FILE  %s was committed at some point", path)

    # git -p skips binary files, so a key inside a .docx or .pdf can't be seen here.
    binaries = sorted(
        {
            line.split("\t")[2]
            for line in git("log", "--all", "--numstat", "--format=").splitlines()
            if line.startswith("-\t-\t")
        }
    )
    for path in binaries:
        logger.warning("CHECK %s is binary: open it and check it by hand", path)

    # Commit emails become public with the repo. Counted, never printed.
    emails = set(git("log", "--all", "--format=%ae%n%ce").split())
    public = public_emails(emails)
    if public:
        logger.warning(
            "NOTE  %d commit email(s) are not GitHub noreply addresses and will be public",
            len(public),
        )

    if findings or files:
        logger.error("FAIL: rotate any real key first, then remove it from the history")
        return 1
    logger.info("No key-shaped strings or secret files in the history")
    return 0


if __name__ == "__main__":
    sys.exit(main())
