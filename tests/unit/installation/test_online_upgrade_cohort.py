"""Standard online installer path; cohort-specific tests are archived separately."""
import re
import subprocess
from pathlib import Path


INSTALLER = Path(__file__).resolve().parents[3] / 'installation/online_install.sh'


def _function(name):
    source = INSTALLER.read_text()
    match = re.search(r'(?ms)^' + re.escape(name) + r'\(\) \{.*?^\}', source)
    assert match, 'missing shell function: ' + name
    return match.group(0)


def _bash(body):
    return subprocess.run(['bash', '-c', body], text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)


def test_standard_upgrade_db_command_preserves_default_and_force():
    runner = _function('run_online_upgrade_db')
    prefix = 'zstack-ctl() { printf "[%s]" "$@"; printf "\\n"; }\n'
    result = _bash(prefix + runner + '\nFORCE=n; run_online_upgrade_db\nFORCE=y; run_online_upgrade_db')
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ['[upgrade_db]', '[upgrade_db][--force]']


def test_installer_does_not_advertise_or_forward_cohort_choice():
    source = INSTALLER.read_text()
    assert 'memory-migration-cohort' not in source
    assert 'MEMORY_MIGRATION_COHORT' not in source
    assert 'run_online_upgrade_db' in source
    assert source.count('run_online_upgrade_db') >= 3
