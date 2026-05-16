"""Automated gitignore boundary tests for VAL-CORPUS-002.

Extends manual ``git check-ignore`` coverage with repeatable pytest
assertions that private corpus paths remain git-ignored while the
publishable ``sample/`` subtree stays tracked.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the calibration CLI with Braintrust env stripped."""
    env = os.environ.copy()
    env.pop("BRAINTRUST_API_KEY", None)
    env.pop("BRAINTRUST_ORG_NAME", None)
    return subprocess.run(
        [sys.executable, "-m", "prism_calibration.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _git_check_ignore(path: Path) -> bool:
    """Return True if *path* is ignored by git (within REPO_ROOT)."""
    rel = path.relative_to(REPO_ROOT)
    result = subprocess.run(
        ["git", "check-ignore", str(rel)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    # exit 0 means ignored, exit 1 means not ignored
    return result.returncode == 0


def _git_check_track(path: Path) -> bool:
    """Return True if *path* would be tracked (not ignored) by git."""
    return not _git_check_ignore(path)


# ---- Default-root boundary tests ----


def test_private_row_is_ignored() -> None:
    """A new row under data/calibration/rows/ is ignored by git."""
    private_rows_dir = REPO_ROOT / "data" / "calibration" / "rows"
    probe = private_rows_dir / "val-corp-002-probe-private.json"
    original_existed = probe.exists()
    try:
        probe.write_text('{"probe": true}', encoding="utf-8")
        assert _git_check_ignore(probe), f"{probe.relative_to(REPO_ROOT)} should be git-ignored"
    finally:
        if not original_existed:
            probe.unlink(missing_ok=True)


def test_sample_row_is_tracked() -> None:
    """A new row under data/calibration/sample/rows/ is tracked by git."""
    sample_rows_dir = REPO_ROOT / "data" / "calibration" / "sample" / "rows"
    probe = sample_rows_dir / "val-corp-002-probe-sample.json"
    original_existed = probe.exists()
    try:
        sample_rows_dir.mkdir(parents=True, exist_ok=True)
        probe.write_text('{"probe": true}', encoding="utf-8")
        assert _git_check_track(probe), f"{probe.relative_to(REPO_ROOT)} should be tracked (not ignored)"
    finally:
        if not original_existed:
            probe.unlink(missing_ok=True)


def test_default_root_gitignore_exists() -> None:
    """The default data/calibration/ root contains a .gitignore file."""
    gitignore = REPO_ROOT / "data" / "calibration" / ".gitignore"
    assert gitignore.is_file(), "data/calibration/.gitignore must exist"


def test_default_root_gitignore_ignores_star() -> None:
    """The default .gitignore starts with a blanket ignore rule."""
    gitignore = REPO_ROOT / "data" / "calibration" / ".gitignore"
    content = gitignore.read_text(encoding="utf-8")
    assert "*" in content.splitlines(), ".gitignore must contain a blanket ignore '*' line"


def test_default_root_gitignore_exempts_sample() -> None:
    """The default .gitignore exempts sample/ and sample/**."""
    gitignore = REPO_ROOT / "data" / "calibration" / ".gitignore"
    content = gitignore.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert "!sample/" in lines or "!sample" in lines, ".gitignore must exempt sample/"
    assert "!sample/**" in lines, ".gitignore must exempt sample/**"


# ---- Custom-root .gitignore tests ----


def test_build_custom_root_creates_gitignore(tmp_path: Path) -> None:
    """Building with --root <custom> creates a .gitignore in that root."""
    custom_root = tmp_path / "custom-calibration"
    result = _run_cli("build", "--root", str(custom_root), "--seed", "42")

    assert result.returncode == 0, result.stderr
    gitignore = custom_root / ".gitignore"
    assert gitignore.is_file(), f"bootstrap_corpus_root must create .gitignore at {gitignore}"


def test_custom_root_gitignore_matches_default_rules(tmp_path: Path) -> None:
    """The custom-root .gitignore has the same ignore/exempt pattern as the default root."""
    custom_root = tmp_path / "custom-calibration"
    _run_cli("build", "--root", str(custom_root), "--seed", "42")

    gitignore = custom_root / ".gitignore"
    content = gitignore.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Must contain blanket ignore
    assert "*" in lines, "Custom .gitignore must have a blanket ignore line"
    # Must exempt .gitignore itself
    assert "!.gitignore" in lines, "Custom .gitignore must exempt itself"
    # Must exempt sample subtree
    assert "!sample/" in lines or "!sample" in lines, "Custom .gitignore must exempt sample/"
    assert "!sample/**" in lines, "Custom .gitignore must exempt sample/**"


def test_bootstrap_corpus_root_writes_gitignore(tmp_path: Path) -> None:
    """Direct call to bootstrap_corpus_root also writes .gitignore."""
    from prism_calibration.layout import bootstrap_corpus_root

    custom_root = tmp_path / "direct-bootstrap"
    layout = bootstrap_corpus_root(root=custom_root)

    gitignore = layout.root / ".gitignore"
    assert gitignore.is_file(), "bootstrap_corpus_root must write .gitignore"
    content = gitignore.read_text(encoding="utf-8")
    assert "*" in content.splitlines(), ".gitignore must contain blanket ignore"


def test_bootstrap_corpus_root_gitignore_idempotent(tmp_path: Path) -> None:
    """Re-running bootstrap_corpus_root does not corrupt the .gitignore."""
    from prism_calibration.layout import bootstrap_corpus_root

    custom_root = tmp_path / "idempotent-root"
    bootstrap_corpus_root(root=custom_root)
    first_content = (custom_root / ".gitignore").read_text(encoding="utf-8")

    bootstrap_corpus_root(root=custom_root)
    second_content = (custom_root / ".gitignore").read_text(encoding="utf-8")

    assert first_content == second_content, "Repeated bootstrap must not change .gitignore"


def test_custom_root_private_dir_is_covered_by_gitignore(tmp_path: Path) -> None:
    """Files in custom-root private dirs would be ignored by the .gitignore rules."""
    from prism_calibration.layout import bootstrap_corpus_root

    custom_root = tmp_path / "coverage-root"
    bootstrap_corpus_root(root=custom_root)

    gitignore = custom_root / ".gitignore"
    content = gitignore.read_text(encoding="utf-8")

    # Verify the .gitignore covers private dirs with the blanket '*' rule
    # and exempts sample/ so sample rows would NOT be ignored
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert "*" in lines, "Must have blanket ignore"
    # Check sample exemption is after the blanket ignore
    star_idx = lines.index("*")
    sample_exempt = [i for i, line in enumerate(lines) if line.startswith("!sample")]
    assert sample_exempt, "Must have sample exemption"
    for idx in sample_exempt:
        assert idx > star_idx, "Sample exemption must come after blanket ignore"
