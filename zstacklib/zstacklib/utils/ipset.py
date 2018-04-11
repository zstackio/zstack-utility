'''

@author: MaJin
'''
import os
import tempfile

from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import ordered_set
from pyparsing import *

logger = log.get_logger(__name__)


class IPSetError(Exception):
    '''ipset error'''


'''
only support hash:net now
legal format of match_ip or nomatch_ip:
127.0.0.1
127.0.0.0/24
ipset also support like 127.0.0.1-127.0.0.5,
but yet we didn't resove some problems such as
del_ip(ip) or add_ip(ip)
'''


class IPSet(object):
    def __init__(self, name, set_type, ip_version):
        self.name = name
        self.ip_version = ip_version
        self.type = set_type
        self.match_ip = []
        self.nomatch_ip = []

    def set_match_ip(self, ips):
        if ips:
            self.match_ip = ips

    def set_nomatch_ip(self, ips):
        if ips:
            self.match_ip = ips

    def add_match_ip(self, ip):
        if not isinstance(self.match_ip, list):
            self.match_ip = []
        # TODO: add ip list and remove duplication
        # if isinstance(ip, list):
        if ip not in self.match_ip:
            self.match_ip.append(ip)

    def add_nomatch_ip(self, ip):
        if not isinstance(self.nomatch_ip, list):
            self.nomatch_ip = []
        if ip not in self.nomatch_ip:
            self.nomatch_ip.append(ip)

    def del_match_ip(self, ip):
        # TODO:IP format is different
        if ip in self.match_ip:
            self.match_ip.remove(ip)

    def del_nomatch_ip(self, ip):
        if ip in self.nomatch_ip:
            self.nomatch_ip.remove(ip)

    def clear_match_ip(self):
        self.match_ip = []

    def clear_nomatch_ip(self):
        self.nomatch_ip = []

    def transform_cmd(self, is_exist=True):
        create_cmd_constant = self._create_set_cmd(is_exist)
        flush_cmd_constant = 'flush %s' % self.name
        ip_cmd_constant = '\n'.join(self._add_ip_cmd_list(is_exist))
        constant = '%s\n%s\n%s\n' % (create_cmd_constant, flush_cmd_constant, ip_cmd_constant)
        return constant

    def _create_set_cmd(self, is_exist=True):
        option = ['', '--exist'][is_exist]
        return 'create %s %s family %s %s' % (self.name, self.type, self.ip_version, option)

    def _add_ip_cmd_list(self, is_exist=True):
        option = ['', '--exist'][is_exist]
        match_cmd = ['add %s %s %s' % (self.name, ip, option) for ip in self.match_ip]
        nomatch_cmd = ['add %s %s %s nomatch' % (self.name, ip, option) for ip in self.nomatch_ip]
        cmd = match_cmd
        cmd.extend(nomatch_cmd)
        return cmd


class IPSetManager(object):
    LIST_SET = 'list:set'
    HASH_NET_IFACE = 'hash:net,iface'
    HASH_NET_PORT = 'hash:net,port'
    HASH_NET = 'hash:net'
    HASH_IP_PORT_NET = 'hash:ip,port,net'
    HASH_IP_PORT_IP = 'hash:ip,port,ip'
    HASH_IP_PORT = 'hash:ip,port'
    HASH_IP = 'hash:ip'
    BITMAP_PORT = 'bitmap:port'
    BITMAP_IP_MAC = 'bitmap:ip,mac'
    BITMAP_IP = 'bitmap:ip'

    DEFAULT_NAME = 'default-sg'
    DEFAULT_TYPE = HASH_NET
    DEFAULT_IP_VERSION = 'inet'

    def __init__(self, namespace=None):
        self.namespace = namespace
        self.sets = {}
        self._parser = None

    def create_set(self, match_ips=None, nomatch_ips=None, name=DEFAULT_NAME, set_type=DEFAULT_TYPE,
                   ip_version=DEFAULT_IP_VERSION):
        self.sets[name] = IPSet(name, set_type, ip_version)
        self.sets[name].set_match_ip(match_ips)
        self.sets[name].set_nomatch_ip(nomatch_ips)

    def destroy_set(self, name):
        del self.sets[name]

    def flush_sets(self, name):
        self.sets[name].clear_match_ip()
        self.sets[name].clear_nomatch_ip()

    def reset(self):
        self.sets.clear()
        self.namespace = None

    def ipset_save(self):
        o = shell.call('ipset save')
        self._from_ipset_save(o)

    def cleanup_other_ipset(self, validate, used_ipset=None):
        if used_ipset:
            used_sets = used_ipset
        else:
            used_sets = self.sets.keys()

        logger.debug('start cleanup other ipsets')
        set_list = shell.call("ipset list -n").splitlines()
        to_del_set_list = [x for x in set_list if validate(x) and x not in used_sets]
        self.clean_ipsets(to_del_set_list)

    @staticmethod
    def clean_ipsets(ipset_names):
        destroy_cmds = ['destroy %s' % set_name for set_name in ipset_names]
        tmp = linux.write_to_temp_file('\n'.join(destroy_cmds))
        o = shell.ShellCmd('ipset restore -f %s' % tmp)
        o(False)
        if o.return_code != 0:
            logger.warn('fail to cleanup ipsets, %s' % o.stderr)
        else:
            logger.debug('success cleanup ipsets')
        os.remove(tmp)

    def refresh_my_ipsets(self):
        (tmp_fd, tmp_path) = tempfile.mkstemp()
        tmp_fd = os.fdopen(tmp_fd, 'w')
        for name, ipset in self.sets.items():
            tmp_fd.write(ipset.transform_cmd())
        tmp_fd.close()

        execns = ''
        if self.namespace:
            execns = 'ip netns exec %s ' % self.namespace

        o = shell.ShellCmd(execns + 'ipset restore -f %s' % tmp_path)
        o(False)
        os.remove(tmp_path)
        if o.return_code != 0:
            raise IPSetError('ipset restore failed, because %s' % o.stderr)
        logger.debug('success restore ipset')

    def _parse_set_action(self, tokens):
        set_name = tokens[1]
        set_type = '%s:%s' % (tokens[2], tokens[4])
        ip_version = tokens[6]
        self.create_set(name=set_name, set_type=set_type, ip_version=ip_version)

    def _parse_entry_action(self, tokens):
        set_name = tokens[1]
        ip = tokens[2]
        if set_name not in self.sets.keys():
            self.create_set(name=set_name)
        self.sets[set_name].add_match_ip(ip)

    def _construct_pyparsing(self):
        if self._parser:
            return

        set_name = Word(printables)
        set_type = Word(alphas) + Word(':') + Word(alphas + ',')

        sets = Literal('create') + set_name + set_type + Literal('family') + Word(alphanums) + restOfLine
        sets.setParseAction(self._parse_set_action)

        entry = Literal('add') + set_name + Word(nums + './')
        entry.setParseAction(self._parse_entry_action)

        self._parser = sets | entry

    def _from_ipset_save(self, txt):
        self.reset()
        self._construct_pyparsing()
        for l in txt.splitlines():
            l = l.strip('\n').strip('\r').strip('\t').strip()
            if not l:
                continue
            self._parser.parseString(l)

def from_ipset_save():
    logger.debug('start load ipset ...')
    ipset = IPSetManager()
    ipset.ipset_save()
    logger.debug('success load ipset ...')
    return ipset
