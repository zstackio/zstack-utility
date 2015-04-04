'''

@author: YYK
'''

import shell
import ssh
import os.path
import log
import subprocess
import lock
import time
import json

logger = log.get_logger(__name__)

class SaltError(Exception):
    '''salt error'''
    
def prepare_salt_state(state_path, salt_state_path='/srv/salt'):
    try:
        subprocess.call(['salt', '--version'])
    except Exception as e:
        print "Execute `salt --version` failed. Probably there isn't salt installed"
        raise e

    if not os.path.exists(salt_state_path):
        os.makedirs(salt_state_path, 0755)

    shell.call('rm -rf %s' % os.path.join(salt_state_path, os.path.basename(state_path)))
    shell.call('cp -r %s %s' % (state_path, salt_state_path))

def is_salt_failed(salt_json_output):
    json_data = json.loads(salt_json_output)
    if isinstance(json_data, list):
        return True

    if isinstance(json_data, dict):
        for value in json_data.values():
            if isinstance(value, dict):
                for item in value.values():
                    if item.has_key('result'):
                        if item['result'] == False:
                            return True
            elif value == False:
                return True
            elif isinstance(value, list):
                return True

    return False

def execute_salt_state(hostname, username, password, state_name, master_name, machine_id=None):
    with lock.FileLock(hostname):
        ssh.execute('''ip=`env | grep SSH_CLIENT | cut -d '=' -f 2 | cut -d ' ' -f 1`; [ $ip == ::1 ] && ip=127.0.0.1; sed -i "/%s/d" /etc/hosts; sed -i "/$ip/d" /etc/hosts; echo "$ip %s" >> /etc/hosts''' % (master_name, master_name), hostname, username, password)
        if not machine_id:
            (retcode, machine_id, err) = ssh.execute('cat /sys/class/dmi/id/product_uuid', hostname, username, password, exception_if_error=False)
            if not machine_id:
                raise SaltError("Can't find machine-id on %s" % hostname)

            machine_id = machine_id.strip()

        if not wait_for_salt_minion_daemon(machine_id, 1, False):
            ssh.execute('which salt-minion; [ $? -ne 0 ] && curl -L http://bootstrap.saltstack.org | sudo sh ;sed -i "^id/d" /etc/salt/minion; sed -i "^master/d" /etc/salt/minion; echo "id: %s" >>/etc/salt/minion; echo "master: %s" >> /etc/salt/minion; rm -f /etc/salt/pki/minion/minion_master.pub ; service salt-minion restart' % (machine_id, master_name), hostname, username, password, exception_if_error=False)
            wait_for_salt_minion_daemon(machine_id)

        print 'salt %s %s' % (machine_id, state_name)
        output = shell.call('salt --out=json %s %s' % (machine_id, state_name))
        if not is_salt_failed(output):
            print '%s' % output
            print "salt has deployed %s" % state_name
        else:
            raise SaltError('salt execution failure: %s' % output)

#need wait for a while for salt_minion to register into master, after its service is restarted.
def wait_for_salt_minion_daemon(salt_minion_id, timeout_times=10, exception=True):
    def _salt_ping():
        cmd = shell.ShellCmd('salt -t 1 --out=json %s test.ping' % salt_minion_id)
        cmd(False)
        return cmd.return_code == 0 and cmd.stdout != ''

    import time
    while timeout_times > 0:
        if _salt_ping():
            return True
        time.sleep(1)
        timeout_times -= 1
        print 'Wait for salt minion: %s registration to master' % salt_minion_id
    else:
        print 'Command fail: `salt %s test.ping`' % salt_minion_id
        if exception:
            raise SaltError('Salt minion daemon: %s failed to register to master, after trying %s times.' % (salt_minion_id, timeout_times))
        else:
            return False

