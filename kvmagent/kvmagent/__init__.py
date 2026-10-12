# Ensure subprocess32 replaces stdlib subprocess on Python < 3.3
# before any other module imports subprocess.
import zstacklib.utils.compat  # noqa: F401
