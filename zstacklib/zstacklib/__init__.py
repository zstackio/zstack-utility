# Ensure subprocess32 replaces stdlib subprocess on Python < 3.3
# before any other module imports subprocess.
# See zstacklib/utils/compat.py for details.
import zstacklib.utils.compat  # noqa: F401
