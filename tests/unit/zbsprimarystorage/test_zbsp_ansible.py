import ast
from pathlib import Path


def test_zbsp_installs_management_callback_probe():
    script_path = Path(__file__).parents[3] / "zbsprimarystorage" / "ansible" / "zbsp.py"
    tree = ast.parse(script_path.read_text())
    assignment = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "install_rpm_list" for target in node.targets)
    )
    packages = set(ast.literal_eval(assignment.value).split())

    assert "nmap" in packages, "MDS callback connectivity checks require nmap"
