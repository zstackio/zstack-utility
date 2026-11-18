import json
import os
from pathlib import Path
import subprocess
import sys


def test_mn_resource_control_is_packaged_and_runs_without_zstacklib(tmp_path):
    repo = Path(__file__).resolve().parents[3]
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    (workspace / 'zstack-utility').symlink_to(repo, target_is_directory=True)
    build = tmp_path / 'build'
    for directory in ['salt', 'ansible', 'dist']:
        (build / 'zstacklib' / directory).mkdir(parents=True)
    command = ['ant', '-f', str(repo / 'zstackbuild/build.xml'),
               '-Dzstack_build_root=' + str(workspace), '-Dbuild.dir=' + str(build), 'assemble-zstacklib']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    assert result.returncode == 0, result.stdout

    sources = {path.name: path for path in
               (repo / 'zstacklib/zstacklib/utils').glob('cgroup*resource_control_backend*.py')}
    for name in ['resource_control.py', 'resource_control_utils.py', 'systemd_resource_control_utils.py']:
        sources[name] = repo / 'zstacklib/zstacklib/utils' / name
    sources['resource_control_cli.py'] = repo / 'imagestorebackupstorage/ansible/resource_control_cli.py'
    stage = build / 'zstack-assemble'
    relative = Path('WEB-INF/classes/tools/resource-control')
    packaged = stage / relative
    assert packaged.is_dir(), 'MN tools must be assembled even when ImageStore is not being built'
    assert {path.name for path in packaged.iterdir()} == set(sources), 'Package the complete standalone executor'
    for name, source in sources.items():
        assert (packaged / name).read_bytes() == source.read_bytes(), name

    stale = packaged / 'resource_control.py'
    stale.write_text('raise RuntimeError("stale build output")\n')
    future = stale.stat().st_mtime + 3600
    os.utime(str(stale), (future, future))
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    assert result.returncode == 0, result.stdout
    assert stale.read_bytes() == sources[stale.name].read_bytes(), 'Reassembly must replace newer stale output'

    war = build / 'resource-control-test.war'
    subprocess.run(['jar', 'cf', str(war), '-C', str(stage), '.'], check=True)
    installed = tmp_path / 'mn/apache-tomcat/webapps/zstack'
    (installed / relative).mkdir(parents=True)
    (installed / relative / 'resource_control.py').write_text('raise RuntimeError("old installed version")\n')
    subprocess.run(['unzip', '-oq', str(war), '-d', str(installed)], check=True)
    for name, source in sources.items():
        assert (installed / relative / name).read_bytes() == source.read_bytes(), name

    result = subprocess.run([sys.executable, '-S', str(installed / relative / 'resource_control_cli.py'), 'topology'],
                            input='{}', cwd=str(tmp_path),
                            env=dict(os.environ, PYTHONPATH='', PYTHONDONTWRITEBYTECODE='1'),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response['success'] and response['numa'], 'Installed files must run without site-packages or zstacklib'
