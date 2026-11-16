"""Tests for the git-history secret audit (STU-D05-BE), using made-up fake keys only."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

# scripts/ is not a package, so load the script from its file.
_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_secrets.py"
_SPEC = importlib.util.spec_from_file_location("audit_secrets", _PATH)
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)

# Built from parts so this test file itself never contains a key-shaped string.
FAKE_OPENAI_KEY = "sk-" + "proj-" + "FAKE0fake1FAKE2fake3FAKE4"


def test_openai_key_in_an_added_line_is_found():
    log = f"COMMIT abc1234\n+OPENAI_API_KEY={FAKE_OPENAI_KEY}\n"
    kinds = {f.kind for f in audit.scan_history(log)}
    assert "OpenAI key" in kinds


def test_finding_is_masked():
    log = f"COMMIT abc1234\n+key = '{FAKE_OPENAI_KEY}'\n"
    finding = audit.scan_history(log)[0]
    assert FAKE_OPENAI_KEY not in finding.masked
    assert finding.masked.startswith("sk-p")


def test_removed_line_is_ignored():
    # "-" = a line deleted in that commit; it was already scanned in the commit that added it.
    assert audit.scan_history(f"COMMIT abc1234\n-x = '{FAKE_OPENAI_KEY}'\n") == []


def test_placeholder_and_ci_key_are_not_findings():
    log = "COMMIT abc1234\n+OPENAI_API_KEY=your_api_key_here\n+API_KEY: ci-only-throwaway-key\n"
    assert audit.scan_history(log) == []


def test_code_reading_a_setting_is_not_a_finding():
    log = "COMMIT abc1234\n+API_KEY = os.getenv('API_KEY', '')\n"
    assert audit.scan_history(log) == []


def test_committed_env_file_is_found_but_the_example_is_not():
    paths = [".env", "app/.env.local", ".env.example", "src/student_workflow/api.py"]
    assert audit.secret_files(paths) == [".env", "app/.env.local"]


def test_github_noreply_addresses_are_not_public_emails():
    emails = {
        "123+someone@users.noreply.github.com",
        "noreply@github.com",
        "person@example.com",
    }
    assert audit.public_emails(emails) == {"person@example.com"}


# A random key with no fixed shape, like the one docs/deploy.md tells us to generate.
FAKE_RANDOM_KEY = "Zq3" + "x9LmP0aB7" + "kT2wR5"


@pytest.mark.parametrize(
    "line",
    [
        f'+curl -H "X-API-Key: {FAKE_RANDOM_KEY}" https://example.com',
        f'+headers = {{"X-API-Key": "{FAKE_RANDOM_KEY}"}}',
        f'+api_key = "{FAKE_RANDOM_KEY}"',
        f"+API_KEY={FAKE_RANDOM_KEY}",
    ],
)
def test_our_own_api_key_is_found_in_the_shapes_it_would_leak_in(line):
    assert audit.scan_history(f"COMMIT abc1234\n{line}\n")


def test_streamlit_secrets_file_is_a_secret_file():
    assert audit.secret_files([".streamlit/secrets.toml"]) == [
        ".streamlit/secrets.toml"
    ]


def git_in(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_main_finds_a_key_typed_into_a_merge_and_a_file_renamed_to_env(
    tmp_path, monkeypatch
):
    # Plain `git log -p` shows neither: merges have no diff, and a rename isn't an "add".
    git_in(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    git_in(tmp_path, "add", ".")
    git_in(tmp_path, "commit", "-q", "-m", "first")
    git_in(tmp_path, "switch", "-q", "-c", "side")
    (tmp_path / "side.txt").write_text("side\n", encoding="utf-8")
    git_in(tmp_path, "add", ".")
    git_in(tmp_path, "commit", "-q", "-m", "side")
    git_in(tmp_path, "switch", "-q", "main")
    git_in(tmp_path, "merge", "-q", "--no-ff", "--no-commit", "side")
    (tmp_path / "side.txt").write_text(
        f"api_key = '{FAKE_RANDOM_KEY}'\n", encoding="utf-8"
    )
    git_in(tmp_path, "add", ".")
    git_in(tmp_path, "commit", "-q", "-m", "merge with a hand edit")
    git_in(tmp_path, "mv", "notes.txt", ".env")
    git_in(tmp_path, "commit", "-q", "-m", "rename")

    monkeypatch.chdir(tmp_path)
    assert audit.main() == 1
    log_text = audit.git(
        "log", "--all", "-p", "--diff-merges=remerge", "--format=COMMIT %h"
    )
    assert audit.scan_history(log_text)  # the merge's key
    paths = audit.git("log", "--all", "-m", "--name-only", "--format=").splitlines()
    assert audit.secret_files(paths) == [".env"]  # the rename
