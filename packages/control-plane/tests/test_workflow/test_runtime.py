"""Unit tests for pure logic in faberon.workflow.runtime (no DBOS, no Postgres)."""

import pytest

from faberon.workflow.runtime import _parse_metric


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
