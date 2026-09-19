"""``faberon`` console entry point: start the control plane from anywhere."""

import os

import uvicorn

from .api.app import create_app_slurm

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8000


def main() -> None:
    """Start the Faberon control plane with the Slurm executor.

    Reads host and port from ``FABERON_HOST`` and ``FABERON_PORT`` if set.
    Requires the same env vars as ``create_app_slurm``:
    ``FABERON_DATABASE_URL``, ``FABERON_SLURM_ACCOUNT``, ``FABERON_API_TOKEN``,
    and ``FABERON_MODEL``.
    """
    host = os.environ.get("FABERON_HOST", _DEFAULT_HOST)
    port = int(os.environ.get("FABERON_PORT", str(_DEFAULT_PORT)))
    uvicorn.run(create_app_slurm, host=host, port=port, factory=True)
