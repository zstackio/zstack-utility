#
import sys
import os

# BPO-27448: Python 2.7 subprocess.Popen has a race condition between
# gc.isenabled() and gc.disable() in _execute_child(). When multiple threads
# call Popen concurrently, this race can permanently disable GC, causing all
# cyclic-reference objects to leak until OOM.
# Fix: replace subprocess with subprocess32 (Python 3 backport) which does
# not manipulate GC around fork(), eliminating the race entirely.
if os.name == 'posix' and sys.version_info[0] < 3:
    try:
        import subprocess32
        sys.modules['subprocess'] = subprocess32
    except ImportError:
        raise ImportError(
            "Failed to import 'subprocess32'. This package is required on Python 2 "
            "to avoid a GC-disabling race condition in subprocess.Popen (BPO-27448). "
            "Please install it via: pip install subprocess32"
        ) 