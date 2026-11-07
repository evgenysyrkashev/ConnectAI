"""Final checks 18.6 that do not need git: no secrets or personal data in our files; required README sections exist."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".venv", "__pycache__", "outputs", ".pytest_cache", ".ruff_cache", ".idea", "node_modules"}
SECRET_PATTERNS = [
    r"refresh_token\s*=\s*[\"'][^\"']{8,}",
    r"BEGIN (RSA |EC )?PRIVATE",
    r"client_secret\s*=\s*[\"'][^\"']{8,}",
    r"EAA[A-Za-z0-9]{20,}",
]
PLACEHOLDER_OK = {
    ".env.example",
    "infra/env.staging.example.yaml",
}  # phone numbers / gmail addresses only as placeholders here


def _files():
    for p in ROOT.rglob("*"):
        if (
            p.is_file()
            and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS)
            and p.suffix not in {".js", ".pyc", ".parquet"}
        ):
            yield p


def test_no_secrets_in_tracked_files():
    hits = []
    for p in _files():
        rel = p.relative_to(ROOT).as_posix()
        if rel == "tests/unit/test_repo_hygiene.py":
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for pat in SECRET_PATTERNS:
            if re.search(pat, text):
                hits.append((rel, pat))
        if (
            rel not in PLACEHOLDER_OK
            and not rel.startswith("tests/")
            and re.search(r"\+358[0-9]{6,}|[\w.+-]+@gmail\.com", text)
        ):
            hits.append((rel, "phone or gmail address"))
    assert not hits, hits


def test_secret_files_are_gitignored():
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    for needed in (
        ".env",
        ".env.*",
        "infra/env.staging.yaml",
        "mock_api/state.json",
        "*-key.json",
        "credentials*.json",
    ):
        assert needed in ignored, needed


def test_readme_has_the_kit_sections_and_no_gpl():
    readme = (ROOT.parent / "README.md").read_text(encoding="utf-8")
    for h in (
        "## Run it",
        "## The five steps",
        "## Data sources that mattered most",
        "## What we tried that didn't work",
        "## Customer with no history",
        "## Final customer messages",
        "## Bonus: live source",
        "## Third-party code, data and licences",
    ):
        assert h in readme, h
    assert "No GPL/AGPL components" in readme or "**No GPL/AGPL components.**" in readme
    reqs = (ROOT / "requirements-app.txt").read_text().lower()
    assert "html2text" not in reqs


def test_final_message_doc_has_all_languages():
    msgs = (ROOT / "docs" / "MESSAGES.md").read_text(encoding="utf-8")
    for lang in ("(fi)", "(sv)", "(nb)", "(en)"):
        assert lang in msgs
    assert "Follow-up – applied" in msgs and "Follow-up – declined" in msgs
