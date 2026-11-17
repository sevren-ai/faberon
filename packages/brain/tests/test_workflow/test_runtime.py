"""Unit tests for pure logic in faberon.workflow.runtime (no DBOS, no Postgres)."""

import pytest

from faberon.workflow.runtime import _parse_metric, _private_dir


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ("val_bpb: 1.10\nloss: 0.5\n", 1.10),
        ("1.10\n", None),
        ("val_bpb: n/a\n", None),
        ("", None),
    ],
)
def test_parse_metric(stdout: str, expected: float | None) -> None:
    assert _parse_metric(stdout, "val_bpb") == expected


def test_private_dir_is_owner_only(tmp_path) -> None:
    path = tmp_path / "repo" / ".faberon"
    _private_dir(path)
    assert path.stat().st_mode & 0o777 == 0o700


def test_private_dir_tightens_existing_dir(tmp_path) -> None:
    path = tmp_path / ".faberon"
    path.mkdir(mode=0o755)
    _private_dir(path)
    assert path.stat().st_mode & 0o777 == 0o700
