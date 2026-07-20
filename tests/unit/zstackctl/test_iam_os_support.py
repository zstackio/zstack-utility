import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
INSTALL_SH = REPO_ROOT / "installation" / "install.sh"


def test_region_manager_installs_java21_on_kylin_sp3_2403():
    install_sh = INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(r'^REGION_MANAGER_OS="([^"]+)"', install_sh, re.MULTILINE)

    assert match is not None
    assert "ky10sp3.2403" in match.group(1).split()
