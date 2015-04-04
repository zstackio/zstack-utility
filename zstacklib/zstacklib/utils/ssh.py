'''

@author: Frank
'''

import paramiko
import os.path
import log

logger = log.get_logger(__name__)

logcmd = False

class SshError(Exception):
    '''ssh error'''

# credit to http://ginstrom.com/scribbles/2009/09/14/easy-sftp-uploading-with-paramiko/
class Sftp(object):
    """
    Wraps paramiko for super-simple SFTP uploading and downloading.
    """

    def __init__(self, username, password, host, port=22):
        self.host = host
        self.transport = paramiko.Transport((host, port))
        self.transport.connect(username=username, password=password)
        self.sftp = paramiko.SFTPClient.from_transport(self.transport)

    def upload(self, local, remote, is_remote_dir=True):
        if is_remote_dir:
            remote_dir = remote
        else:
            remote_dir = os.path.dirname(remote)
            
        try:
            self.sftp.mkdir(remote_dir)
        except IOError:
            logger.debug('assume dir %s exists on host %s' % (remote_dir, self.host))
        
        self.sftp.put(local, remote)

    def download(self, remote, local):
        self.sftp.get(remote, local)

    def close(self):
        """
        Close the connection if it's active
        """

        if self.transport.is_active():
            self.sftp.close()
            self.transport.close()

    # with-statement support
    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self.close()
        
def scp(src, dst, hostname, username, password, port=22):
    '''
    scp specific file from source to target. Both src and dst are file name, but dst file must be exist.
    '''
    with Sftp(username, password, hostname, port) as server:
        server.upload(src, dst)

def scp_file(src, dst, hostname, username, password, port=22):
    '''
    scp specific file from source file to target file. Both src and dst are 
    file name, but not folder name. The dst file doesn't need to be exist. If 
    the dst's folder is missing, the folder will be created by this API. But it
    won't create dst chained folders. E.g. if dst=/tmp/F1/F2/target_file, if 
    /tmp/F1 is missing, the API will meet failure. If /tmp/F1 is there, but 
    /tmp/F1/F2 is missing, the API will help to create it. 
    '''
    with Sftp(username, password, hostname, port) as server:
        server.upload(src, dst, False)

def ssh_execute_script_file(src, hostname, username, password, port=22):
    '''
    scp a src file to remote host and execute it.
    '''
    temp_file = '/tmp/zstack/tmp_script.sh'
    scp_file(src, temp_file, hostname, username, password, port)
    ssh_cmd = 'sh %s; rm -f %s' % (temp_file, temp_file)
    execute(ssh_cmd, hostname, username, password)

def execute(command, hostname, username, password, exception_if_error=True):
    if logcmd:
        logger.debug('ssh execute[%s]' % command)
        
    ssh = paramiko.SSHClient()
    try:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname, username=username, password=password)
        
        chan = ssh.get_transport().open_session()
        chan.exec_command(command)
        stdout = chan.makefile('rb', -1) 
        stderr = chan.makefile_stderr('rb', -1) 
        retcode = chan.recv_exit_status()
        output = stdout.read()
        erroutput = stderr.read()
        if retcode != 0 and exception_if_error:
            err = 'command[%s] failed on host[%s], stdout: %s, stderr: %s, return code: %s' % (command, hostname, output, erroutput, retcode)
            raise SshError(err)
        return (retcode, output, erroutput)
    finally:
        ssh.close()

def make_ssh_no_password(target, username, password):
    id_rsa = '/root/.ssh/id_rsa'
    id_rsa_pub = '/root/.ssh/id_rsa.pub'
    id_dsa_pub = '/root/.ssh/id_dsa.pub'
    if os.path.exists(id_rsa_pub):
        id_pub = id_rsa_pub
    elif os.path.exists(id_dsa_pub):
        id_pub = id_dsa_pub
    else:
        if os.path.exists(id_rsa):
            err = 'Did not find ssh public key in %s or %s, but private key %s exists. If this private key is copied from other place, the related public key should be copied as well. If not, it is better to delete %s. Then woodpecker will help to generate the paried private key and public key. ' % (id_rsa_pub, id_dsa_pub, id_rsa, id_rsa)
            raise SshError(err)
        os.system("ssh-keygen -t rsa -f %s -N '' " % id_rsa)
        id_pub = id_rsa_pub

    pub_id = open(id_pub).readline().strip()
    mk_ssh_no_passwd="if [ ! -f ~/.ssh/authorized_keys ]; then mkdir -p ~/.ssh/; chmod 700 ~/.ssh/; touch ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys; fi ; grep '%s' ~/.ssh/authorized_keys > /dev/null; if [ $? -ne 0 ]; then echo -e '\n%s\n' >> ~/.ssh/authorized_keys; sed -i '/^$/d' ~/.ssh/authorized_keys;fi;" % (pub_id, pub_id)

    execute(mk_ssh_no_passwd, target, username, password)
