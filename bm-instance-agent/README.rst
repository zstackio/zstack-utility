Build the Linux installer
=========================

Use a manylinux2014 container for the target architecture (glibc 2.17).
From the ``bm-instance-agent`` directory, run::

    python3.11 -m pip install 'tox==3.28.0'
    python3.11 -m tox -e package

The resulting ``zstack-bm-agent-<arch>-<version>.bin`` includes Python
and the native helpers for that architecture. It can run offline.
