'''

@author: Frank
'''
from setting import zstacksetting
from zstacklib.utils import shell
import os
import argparse
import string

class PuppetFacadeSetting(zstacksetting.SettingPlugin):
    DEBIAN_HOSTNAME = '/etc/hostname'
    REDHAT_HOSTNAME = '/etc/sysconfig/network'
    
    ARG_HOSTNAME = 'hostname'
    ARG_PUPPET_CONF = 'puppetconf'
    
    PUPPET_BACKUP_SUB_DIR = 'puppet'
    PUPPET_RESOURCE_DIR = 'puppet'
    
    def _set_puppet(self, args):
        puppet_conf = vars(args)[self.ARG_PUPPET_CONF]
        if not os.path.exists(puppet_conf):
            raise zstacksetting.SettingError('cannot find %s' % puppet_conf)
        
        hostname = shell.call('hostname')
        resource_tmpt = zstacksetting.get_resource_file('puppet.conf', self.PUPPET_RESOURCE_DIR)
        with open(resource_tmpt, 'r') as fd:
            content = fd.read()
            
        zstacksetting.backup_file(puppet_conf, self.PUPPET_BACKUP_SUB_DIR)
        tmpt = string.Template(content)
        d = {'server_host_name' : hostname}
        content = tmpt.safe_substitute(d)
        with open(puppet_conf, 'w') as fd:
            fd.write(content)
        zstacksetting.report_system_change(puppet_conf)
        
        puppet_dir = os.path.dirname(puppet_conf)
        autosign = os.path.join(puppet_dir, 'autosign.conf')
        if os.path.exists(autosign):
            zstacksetting.backup_file(autosign, self.PUPPET_BACKUP_SUB_DIR)
        with open(autosign, 'w') as fd:
            fd.write('*')
        zstacksetting.report_system_change(autosign)
        
    def _set_redhat_hostname(self, hostname):
        new = []
        with open(self.REDHAT_HOSTNAME, 'r') as fd:
            for l in fd.readlines():
                if 'HOSTNAME' in l:
                    continue
                new.append(l)
            new.append('HOSTNAME=%s\n' % hostname)
            
        zstacksetting.backup_file(self.REDHAT_HOSTNAME, self.PUPPET_BACKUP_SUB_DIR)
        
        with open(self.REDHAT_HOSTNAME, 'w') as fd:
            fd.write(''.join(new))
        
        zstacksetting.report_system_change(self.REDHAT_HOSTNAME)
    
    def _set_debian_hostname(self, hostname):
        zstacksetting.backup_file(self.DEBIAN_HOSTNAME, self.PUPPET_BACKUP_SUB_DIR)
        with open(self.DEBIAN_HOSTNAME, 'w') as fd:
            fd.write(hostname)
            
        zstacksetting.report_system_change('changed %s' % self.DEBIAN_HOSTNAME)
        
    def _set_hostname(self, args):
        hostname = vars(args)[self.ARG_HOSTNAME]
        if os.path.exists(self.DEBIAN_HOSTNAME):
            self._set_debian_hostname(hostname)
        elif os.path.exists(self.REDHAT_HOSTNAME):
            self._set_redhat_hostname(hostname)
        else:
            raise zstacksetting.SettingError("cannot find %s and %s, the system is neither debian based nor redhat based" % (self.REDHAT_HOSTNAME, self.DEBIAN_HOSTNAME))
        
        shell.call('hostname %s' % hostname)
        print 'set hostname to %s' % hostname
    
    def add_subcommand(self, subcommand_parser):
        hostname_cmd = subcommand_parser.add_parser('setHostName', help=("set hostname of machine"),
                                                    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        hostname_cmd.add_argument('--hostname', required=True, help=("hostname for this machine"), dest=self.ARG_HOSTNAME)
        hostname_cmd.set_defaults(func=self._set_hostname)
        
        puppet_cmd = subcommand_parser.add_parser('configPuppet', formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                                  help='configure puppet')
        puppet_cmd.add_argument('--puppetConf', default='/etc/puppet/puppet.conf', dest=self.ARG_PUPPET_CONF,
                                help=("puppet configuration file path. the directory of this file is assumed as puppet's "
                                      "configuration directory. for example, /etc/puppet/puppet.conf means /etc/puppet is configuration "
                                      "directory, zstack-setting will create necessary files in the configuration directory"))
        puppet_cmd.set_defaults(func=self._set_puppet)
    
    def _check_hostname(self):
        hostname = shell.call('hostname')
        if 'localhost' in hostname:
            raise zstacksetting.SettingError(("this machine has not been configured with a meaningful hostname, "
                                              "current hostname[%s] will confuse puppet agent when zstack management "
                                              "deploying its agents. you can either use 'zstack-setting setHostName' or "
                                              "manually change it to a name without 'localhost' in" % hostname))
    def check_system(self):
        self._check_hostname()
    
    def finalize(self):
        pass