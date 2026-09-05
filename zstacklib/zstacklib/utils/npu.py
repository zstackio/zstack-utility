# -*- coding: utf-8 -*-
"""NPU command discovery shared by KVM Agent components."""

import os

from zstacklib.utils.bash import bash_roe


NPU_SMI_FALLBACK_PATH = "/usr/local/sbin/npu-smi"


def get_npu_smi_path():
    """Resolve npu-smi from PATH, then the 910C driver location only."""
    r, output, _ = bash_roe("which npu-smi")
    if r == 0 and output.strip():
        return output.strip().splitlines()[0]

    if os.path.isfile(NPU_SMI_FALLBACK_PATH) and os.access(
            NPU_SMI_FALLBACK_PATH, os.X_OK):
        return NPU_SMI_FALLBACK_PATH
    return None
