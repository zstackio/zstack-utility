'''

@author: Frank
'''

import shell
import ssh
import os.path
import log
import lock

logger = log.get_logger(__name__)

class PuppetError(Exception):
    '''puppet error'''
    
def deploy_puppet_module(module_path, node_express=None, node_file_name=None, puppet_node_path='/etc/puppet/manifests/nodes', puppet_module_path='/etc/puppet/modules/'):
    if node_express:
        node_file_path = os.path.join(puppet_node_path, node_file_name)
        with open(node_file_path, 'w') as fd:
            fd.write(node_express)
        
    shell.call('rm -rf %s' % os.path.join(puppet_module_path, os.path.basename(module_path)))
    shell.call('cp -r %s %s' % (module_path, puppet_module_path))

def poke_puppet_agent(hostname, username, password, node_name, master_certname='zstack'):
    with lock.FileLock(hostname):
        ssh.execute('''ip=`env | grep SSH_CLIENT | cut -d '=' -f 2 | cut -d ' ' -f 1`; [ $ip == ::1 ] && ip=127.0.0.1; sed -i "/%s/d" /etc/hosts; echo "$ip %s" >> /etc/hosts''' % (master_certname, master_certname), hostname, username, password)
        (retcode, output, err) = ssh.execute('puppet agent --certname %s --no-daemonize --onetime --waitforcert 60 --server %s --verbose --detailed-exitcodes' % (node_name, master_certname), hostname, username, password, exception_if_error=False)
        if retcode == 4 or retcode == 6 or retcode == 1:
            raise PuppetError('failed to run puppet agent:\nstdout:%s\nstderr:%s\n' % (output, err))
        
        logger.debug(output)
