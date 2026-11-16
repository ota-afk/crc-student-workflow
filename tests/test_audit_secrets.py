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


def test_safe_assignments_inside_a_python_string_are_not_findings():
    # Git sees literal backslash-n characters in this source line, not actual newlines.
    line = (
        r'+log = "COMMIT abc1234\n+OPENAI_API_KEY=your_api_key_here\n'
        r'+API_KEY: ci-only-throwaway-key\n"'
    )
    assert audit.scan_history(f"COMMIT abc1234\n{line}\n") == []


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
FAKE_LETTER_KEY = "AbCdEfGh" + "IjKlMnOpQrStUvWxYz"


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


@pytest.mark.parametrize(
    "line",
    [
        f"+API_KEY={FAKE_LETTER_KEY}",
        f'+api_key = "{FAKE_LETTER_KEY}"',
        f'+password = "{FAKE_LETTER_KEY} with spaces"',
        f'+curl -H "X-API-Key: {FAKE_LETTER_KEY}" https://example.com',
    ],
)
def test_literal_secrets_without_digits_are_found(line):
    findings = audit.scan_history(f"COMMIT abc1234\n{line}\n")
    assert any(f.kind == "assigned secret" for f in findings)
    assert all(FAKE_LETTER_KEY not in f.masked for f in findings)


@pytest.mark.parametrize(
    "value",
    [
        "os.getenv('API_KEY', '')",
        "settings.API_KEY",
        "config.api_key()",
        "${API_KEY}",
        '"{FAKE_RANDOM_KEY}"',
        '"<the shared key>"',
    ],
)
def test_code_references_and_documentation_placeholders_are_not_secrets(value):
    assert audit.scan_history(f"COMMIT abc1234\n+API_KEY={value}\n") == []


def test_quoted_secret_is_not_mistaken_for_a_code_reference():
    value = "os." + FAKE_LETTER_KEY
    assert audit.scan_history(f'COMMIT abc1234\n+API_KEY="{value}"\n')


@pytest.mark.parametrize(
    "key_prefix,value_prefix", [("+", "+"), (" ", "+"), ("+", " ")]
)
def test_yaml_setting_is_checked_when_its_name_or_value_is_added(
    key_prefix, value_prefix
):
    log = (
        "COMMIT abc1234\n"
        f"{key_prefix}  - key: API_KEY\n"
        f'{value_prefix}    value: "{FAKE_LETTER_KEY}"\n'
    )
    findings = audit.scan_history(log)
    assert len(findings) == 1
    assert findings[0].commit == "abc1234"
    assert FAKE_LETTER_KEY not in findings[0].masked


def test_yaml_replacement_value_is_checked_with_an_unchanged_name():
    log = (
        "COMMIT abc1234\n"
        "   - key: API_KEY\n"
        "-    value: your_api_key_here\n"
        f"+    value: {FAKE_LETTER_KEY}\n"
    )
    assert audit.scan_history(log)


def test_yaml_secret_name_does_not_carry_over_to_another_setting():
    log = (
        "COMMIT abc1234\n"
        "+  - key: API_KEY\n"
        "+    sync: false\n"
        "+  - key: API_URL\n"
        "+    value: https://api.example.com\n"
    )
    assert audit.scan_history(log) == []


@pytest.mark.parametrize(
    "boundary", ["COMMIT def5678", "@@ -10,1 +10,1 @@", "diff --git a/a b/b"]
)
def test_yaml_secret_name_does_not_carry_over_to_another_diff_section(boundary):
    log = (
        "COMMIT abc1234\n"
        "+  - key: API_KEY\n"
        f"{boundary}\n"
        "+    value: https://api.example.com\n"
    )
    assert audit.scan_history(log) == []


def test_removed_yaml_secret_is_not_reported_as_a_new_secret():
    log = (
        "COMMIT abc1234\n"
        "-  - key: API_KEY\n"
        f"-    value: {FAKE_LETTER_KEY}\n"
    )
    assert audit.scan_history(log) == []


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
