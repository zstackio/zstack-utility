import ast
from pathlib import Path


def _releasever_mapping():
    script = (
        Path(__file__).resolve().parents[3]
        / "imagestorebackupstorage"
        / "ansible"
        / "imagestorebackupstorage.py"
    )
    tree = ast.parse(script.read_text())

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "releasever_mapping"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)

    raise AssertionError("releasever_mapping not found")


def test_centos_7_installs_collectd_disk_for_imagestore_monitoring():
    mapping = _releasever_mapping()

    for releasever in ("c76", "c79"):
        assert "collectd-disk" in mapping[releasever].split()
