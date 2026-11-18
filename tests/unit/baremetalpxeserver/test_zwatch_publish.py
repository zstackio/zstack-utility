"""Exercise the zwatch publication block without running host deployment."""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.baremetalpxeserver
@pytest.mark.parametrize("available_agent_names", [
    ("zwatch-vm-agent", "zwatch-vm-agent_aarch64"),
    ("zwatch-vm-agent",),
    ("zwatch-vm-agent_aarch64",),
], ids=["both-architectures", "only-x86", "only-arm"])
def test_publish_only_available_linux_agents(tmp_path, available_agent_names):
    script_path = (Path(__file__).resolve().parents[3] / "baremetalpxeserver" /
                   "ansible" / "baremetalpxeserver.py")
    source = script_path.read_text()
    # Only execute the publication block: the rest of this top-level script
    # deploys services and modifies the PXE host.
    start = source.index("# name: copy zwatch-vm-agent")
    end = source.index('copy_arg = CopyArg()\ncopy_arg.src = "%s/agent_version"', start)
    publish_block = source[start:end]

    package_dir = tmp_path / "kvm"
    package_dir.mkdir()
    excluded_names = ("zwatch-vm-agent_mips64el", "zwatch-vm-agent_loongarch64",
                      "zwatch-vm-agent_freebsd_amd64", "zwatch-vm-agent_s390x",
                      "zwatch-vm-agent.md5", "unrelated-package")
    for name in available_agent_names + excluded_names:
        (package_dir / name).write_text(name)
    ftp_root = "/var/lib/zstack/baremetal/ftp"
    copied = []

    def copy(copy_arg, host_post_info):
        copied.append((copy_arg.src, copy_arg.dest))

    namespace = dict(os=os, CopyArg=SimpleNamespace, copy=copy,
                     host_post_info=SimpleNamespace(), kvm_file_root=str(package_dir),
                     VSFTPD_ROOT_PATH=ftp_root)
    exec(compile(publish_block, str(script_path), "exec"), namespace)

    assert sorted(copied) == sorted((str(package_dir / name), ftp_root + "/" + name)
                                    for name in available_agent_names)
