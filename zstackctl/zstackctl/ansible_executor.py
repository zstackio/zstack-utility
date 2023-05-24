import threading

from ansible import constants as ansible_constants
from ansible import context as ansible_context
from ansible.executor import task_queue_manager as ansible_tqm
from ansible.module_utils.common import collections as ansible_collections
from ansible.inventory import manager as ansible_im
from ansible.parsing import dataloader as ansible_dataloader
from ansible.playbook import play as ansible_play
from ansible.plugins import cache
from ansible.plugins.cache import memory
from ansible.plugins import callback as ansible_callback
from ansible.vars import manager as ansible_vm


ansible_constants.set_constant('HOST_KEY_CHECKING', False)
ansible_constants.set_constant('CACHE_PLUGIN', 'memory')
ansible_constants.set_constant('DEFAULT_GATHERING', 'implicit')
ansible_constants.set_constant('INVENTORY_ENABLED', ['ini'])

_ansible_cache = {}


class MemCache(cache.BaseCacheModule):
    def __init__(self, *args, **kwargs):
        global _ansible_cache
        self._cache = _ansible_cache

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, value):
        self._cache[key] = value

    def keys(self):
        return self._cache.keys()

    def contains(self, key):
        return key in self._cache

    def delete(self, key):
        del self._cache[key]

    def flush(self):
        self._cache = {}

    def copy(self):
        return self._cache.copy()

    def __getstate__(self):
        return self.copy()

    def __setstate__(self, data):
        self._cache = data


# memory.CacheModule = MemCache


class ResultsCollectorJSONCallback(ansible_callback.CallbackBase):
    def __init__(self, *args, **kwargs):
        super(ResultsCollectorJSONCallback, self).__init__(*args, **kwargs)
        self.ret = {}

    def v2_runner_on_unreachable(self, result):
        host = result._host
        r = result._result
        r.update({'failed': True, 'failed_reason': 'unreachable'})
        self.ret[host.get_name()] = r

    def v2_runner_on_ok(self, result):
        host = result._host
        r = result._result
        r.update({'failed': False, 'failed_reason': ''})
        self.ret[host.get_name()] = r

    def v2_runner_on_failed(self, result, *args, **kwargs):
        host = result._host
        r = result._result
        r.update({'failed': True, 'failed_reason': 'failed'})
        self.ret[host.get_name()] = r

    def v2_runner_on_skipped(self, result):
        host = result._host
        r = result._result
        r.update({'failed': False, 'failed_reason': ''})
        self.ret[host.get_name()] = r

    def fetch_result(self):
        return {
            'dark': {},
            'contacted': self.ret
        }


vm_cache = {}

class VM(ansible_vm.VariableManager):
    def __init__(self, loader, inventory, key):
        super(VM, self).__init__(loader, inventory)
        self._key = key

    def get_vars(self, *args, **kwargs):
        global vm_cache
        flag = str(args) + str(kwargs) + self._key
        if flag not in vm_cache:
            vars = super(VM, self).get_vars(*args, **kwargs)
            vm_cache[flag] = vars
        return vm_cache[flag]


ansible_module_cache = {}


class AnsibleModules(object):
    def __init__(self, runner_args):
        self.host_inventory = runner_args.host_post_info.host_inventory
        self.private_key = runner_args.host_post_info.private_key
        self.host = runner_args.host_post_info.host
        self.module_name = runner_args.module_name
        self.module_args = runner_args.module_args
        self.remote_port = runner_args.host_post_info.remote_port
        self.remote_user = runner_args.host_post_info.remote_user
        self.remote_pass = runner_args.host_post_info.remote_pass
        self.become = runner_args.host_post_info.become
        self.become_user = runner_args.host_post_info.become_user
        self.become_pass = runner_args.host_post_info.remote_pass
        self.transport = 'smart'

        global ansible_module_cache
        self.key = '%s-%s' % (self.host, threading.currentThread().ident)
        if self.key not in ansible_module_cache:
            ansible_module_cache[self.key] = {}

    @property
    def _passwords(self):
        return {
            'conn_pass': self.remote_pass,
            'become_pass': self.become_pass
        }

    @property
    def loader(self):
        if not hasattr(self, 'data_loader'):
            self.data_loader = ansible_dataloader.DataLoader()
        return self.data_loader

    @property
    def result_callback(self):
        if not hasattr(self, 'rc'):
            self.rc = ResultsCollectorJSONCallback()
        return self.rc

    @property
    def inventory(self):
        global ansible_module_cache
        if'inventory' not in ansible_module_cache[self.key]:
            inv = ansible_im.InventoryManager(
                loader=self.loader,
                sources=self.host_inventory)
            ansible_module_cache[self.key]['inventory'] = inv
        if not hasattr(self, 'inv'):
            self.inv = ansible_module_cache[self.key]['inventory']
        return self.inv

    @property
    def variable_manager(self):
        global ansible_module_cache
        if'variable_manager' not in ansible_module_cache[self.key]:
            vm = VM(loader=self.inventory._loader,
                    inventory=self.inventory,
                    key=self.key)
            ansible_module_cache[self.key]['variable_manager'] = vm
        if not hasattr(self, 'vm'):
            self.vm = ansible_module_cache[self.key]['variable_manager']
        return self.vm

    @property
    def task_queue_manager(self):
        if not hasattr(self, 'tqm'):
            self.tqm = ansible_tqm.TaskQueueManager(
                inventory=self.inventory,
                variable_manager=self.variable_manager,
                loader=self.inventory._loader,
                passwords=self._passwords,
                stdout_callback=self.result_callback,
                run_additional_callbacks=False)
            self.tqm._callbacks_loaded = True
        return self.tqm


class AnsibleExecutor(object):
    def __init__(self, runner_args):
        self.host_inventory = runner_args.host_post_info.host_inventory
        self.private_key = runner_args.host_post_info.private_key
        self.host = runner_args.host_post_info.host
        self.module_name = runner_args.module_name
        self.module_args = runner_args.module_args
        self.remote_port = runner_args.host_post_info.remote_port
        self.remote_user = runner_args.host_post_info.remote_user
        self.remote_pass = runner_args.host_post_info.remote_pass
        self.become = runner_args.host_post_info.become
        self.become_user = runner_args.host_post_info.become_user
        self.become_pass = runner_args.host_post_info.remote_pass
        self.transport = 'smart'

        ansible_context.CLIARGS = ansible_collections.ImmutableDict(
            connection=self.transport,
            become=self.become,
            become_user=self.become_user,
            private_key_file=self.private_key,
            become_method='sudo',
            ansible_pipelining=True,
            ansible_ssh_extra_args=('-C -o ControlMaster=auto '
                                    '-o ControlPersist=1800s'),
        )
        self.ansible_module = AnsibleModules(runner_args)

    def run(self):
        action = {'module': self.module_name}
        if self.module_name == 'shell':
            action['_raw_params'] = self.module_args
        else:
            action['args'] = self.module_args
        play_source = dict(
            hosts=self.host,
            tasks=[{'action': action,
                    'register': 'shell_out',
                    }],
            vars={'ansible_user': self.remote_user,
                  'ansible_port': self.remote_port},
            gather_facts=False
        )
        play = ansible_play.Play().load(
            play_source,
            variable_manager=self.ansible_module.variable_manager,
            loader=self.ansible_module.loader)
        try:
            ret = self.ansible_module.task_queue_manager.run(play)
        finally:
            self.ansible_module.task_queue_manager.cleanup()
            if self.ansible_module.tqm._loader:
                self.ansible_module.tqm._loader.cleanup_all_tmp_files()
        return self.ansible_module.result_callback.fetch_result()
