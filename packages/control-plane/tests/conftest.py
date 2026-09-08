"""Shared pytest hooks for the control-plane test suite."""

import os

import pytest


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip specific tests if the correct env vars are not set"""
    if "postgres" in item.keywords and not os.environ.get("FABERON_DATABASE_URL"):
        pytest.skip("set FABERON_DATABASE_URL to a Postgres instance")
    if "slurm" in item.keywords:
        if not os.environ.get("FABERON_SLURM_INTEGRATION"):
            pytest.skip("set FABERON_SLURM_INTEGRATION=1 to run on-cluster Slurm tests")
        if not os.environ.get("FABERON_SLURM_ACCOUNT"):
            pytest.skip(
                "set FABERON_SLURM_ACCOUNT to the Slurm account to bill jobs to"
            )
