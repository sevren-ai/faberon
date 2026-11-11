"""Skip markers for tests that need (or must not have) a specific tool on PATH."""

import shutil

import pytest

SBATCH = shutil.which("sbatch")
PI = shutil.which("pi")
FABERON_CHAT = shutil.which("faberon-chat")

requires_sbatch = pytest.mark.skipif(SBATCH is None, reason="needs sbatch on PATH")
requires_no_sbatch = pytest.mark.skipif(
    SBATCH is not None, reason="needs no sbatch on PATH"
)
requires_pi = pytest.mark.skipif(PI is None, reason="needs pi on PATH")
requires_no_pi = pytest.mark.skipif(PI is not None, reason="needs no pi on PATH")
requires_faberon_chat = pytest.mark.skipif(
    FABERON_CHAT is None, reason="needs faberon-chat on PATH"
)
requires_no_faberon_chat = pytest.mark.skipif(
    FABERON_CHAT is not None, reason="needs no faberon-chat on PATH"
)
