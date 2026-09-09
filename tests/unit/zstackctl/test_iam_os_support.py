import ast
import re
import warnings
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
CTL_PY = REPO_ROOT / "zstackctl" / "zstackctl" / "ctl.py"
INSTALL_SH = REPO_ROOT / "installation" / "install.sh"


def _iam_service_class():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        module = ast.parse(CTL_PY.read_text(encoding="utf-8"))

    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "IamService":
            return node

    raise AssertionError("IamService not found")


def _method_source(class_node, method_name):
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return ast.get_source_segment(CTL_PY.read_text(encoding="utf-8"), node)

    raise AssertionError("%s not found" % method_name)


def test_iam_service_accepts_patch_release_from_supported_os_family():
    iam_service = _iam_service_class()

    matcher = _method_source(iam_service, "is_supported_os")
    validation = _method_source(iam_service, "init_validation")

    assert "startswith" in matcher
    assert '"%s." % supported_os' in matcher
    assert "self.is_supported_os(current_os)" in validation
    assert "current_os not in self.SUPPORTED_OS" not in validation


def test_region_manager_installs_java21_on_kylin_sp3_2403():
    install_sh = INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(r'^REGION_MANAGER_OS="([^"]+)"', install_sh, re.MULTILINE)

    assert match is not None
    assert "ky10sp3.2403" in match.group(1).split()
