"""
Centralised subprocess compatibility shim.

Python < 3.3 stdlib subprocess lacks communicate(timeout=...),
wait(timeout=...) and TimeoutExpired.  subprocess32 back-ports them.

Usage::

    from zstacklib.utils.compat import subprocess

The sys.modules patch below is a safety net: even if someone writes
a bare ``import subprocess``, they still get the right implementation.
"""

import sys

if sys.version_info < (3, 3):
    import subprocess32 as subprocess  # type: ignore
    sys.modules['subprocess'] = subprocess
else:
    import subprocess
