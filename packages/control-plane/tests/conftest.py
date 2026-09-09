"""Shared pytest hooks for the control-plane test suite."""

import os

import psycopg
import pytest


def _postgres_is_reachable(url: str) -> bool:
    try:
        conn = psycopg.connect(url, connect_timeout=2)
        conn.close()
        return True
    except psycopg.OperationalError:
        return False


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip specific tests if the correct env vars are not set."""
    if "postgres" in item.keywords:
        url = os.environ.get("FABERON_DATABASE_URL")
        if not url:
            pytest.skip("set FABERON_DATABASE_URL to a Postgres instance")
        if not _postgres_is_reachable(url):
            pytest.skip(f"Postgres is not running at {url}.")
    if "slurm" in item.keywords:
        if not os.environ.get("FABERON_SLURM_INTEGRATION"):
            pytest.skip("set FABERON_SLURM_INTEGRATION=1 to run on-cluster Slurm tests")
        if not os.environ.get("FABERON_SLURM_ACCOUNT"):
            pytest.skip(
                "set FABERON_SLURM_ACCOUNT to the Slurm account to bill jobs to"
            )
