import _ctypes
import marshal
import sys
import threading
import types

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

    def run(self):
        self.password = {
            'conn_pass': self.remote_pass,
            'become_pass': self.become_pass
        }
        self.loader = ansible_dataloader.DataLoader()
        self.rc = ResultsCollectorJSONCallback()
        self.inventory = ansible_im.InventoryManager(
                loader=self.loader,
                sources=self.host_inventory)
        self.variable_manager = ansible_vm.VariableManager(loader=self.loader,
                    inventory=self.inventory)

        action = {'module': self.module_name}
        if self.module_name == 'shell':
            action['_raw_params'] = self.module_args
        else:
            action['args'] = self.module_args
        play_source = dict(
            hosts=self.host,
            tasks=[{'action': action,
                    # 'register': 'shell_out',
                    }],
            vars={'ansible_user': self.remote_user,
                  'ansible_port': self.remote_port,
                  'ansible_pipelining': True},
            gather_facts=False,
            ignore_errors= True
        )

        play = ansible_play.Play().load(
            play_source,
            variable_manager=self.variable_manager,
            loader=self.loader)
        self.task_queue_manager = ansible_tqm.TaskQueueManager(
                inventory=self.inventory,
                variable_manager=self.variable_manager,
                loader=self.loader,
                passwords=self.password,
                stdout_callback=self.rc,
                run_additional_callbacks=False)
        try:
            ret = self.task_queue_manager.run(play)
        finally:
            self.task_queue_manager.cleanup()
            if self.loader:
                self.loader.cleanup_all_tmp_files()
        return self.rc.fetch_result()


class ResultsCollectorJSONCallbacks(ansible_callback.CallbackBase):
    def __init__(self, *args, **kwargs):
        self.host_post_info = kwargs.pop('host_post_info')
        super(ResultsCollectorJSONCallbacks, self).__init__(*args, **kwargs)
        self.ret = {}

    def _handle_exit(self, result):
        task = result._task
        vars = task.vars
        if 'exit_on_fail' in vars and vars['exit_on_fail']:
            sys.exit(1)

        if 'callback_on_fail' in task.vars and task.vars['callback_on_fail']:
            params = task.vars['callback_on_fail']
            cb = marshal.loads(params[0])
            func = types.FunctionType(cb, globals())
            func(result, *params[1:])

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

        task = result._task
        if 'callback_on_succ' in task.vars and task.vars['callback_on_succ']:
            params = task.vars['callback_on_succ']
            cb = marshal.loads(params[0])
            func = types.FunctionType(cb, globals())
            func(result, *params[1:])

    def v2_runner_on_failed(self, result, *args, **kwargs):
        host = result._host
        r = result._result
        r.update({'failed': True, 'failed_reason': 'failed'})
        self.ret[host.get_name()] = r

        self._handle_exit(result)

    def v2_runner_on_skipped(self, result):
        host = result._host
        r = result._result
        r.update({'failed': False, 'failed_reason': ''})
        self.ret[host.get_name()] = r

    def v2_playbook_on_task_start(self, task, is_conditional):
        pass

    def fetch_result(self):
        return {
            'dark': {},
            'contacted': self.ret
        }


class AnsiblePBExecutor(object):
    def __init__(self, host_post_info):
        self.host_post_info = host_post_info
        self.host_inventory = host_post_info.host_inventory
        self.private_key = host_post_info.private_key
        self.host = host_post_info.host
        self.remote_port = host_post_info.remote_port
        self.remote_user = host_post_info.remote_user
        self.remote_pass = host_post_info.remote_pass
        self.become = host_post_info.become
        self.become_user = host_post_info.become_user
        self.become_pass = host_post_info.remote_pass
        self.transport = 'smart'

        ansible_context.CLIARGS = ansible_collections.ImmutableDict(
            connection=self.transport,
            become=self.become,
            become_user=self.become_user,
            private_key_file=self.private_key,
            become_method='sudo',
            ssh_extra_args='-C -o ControlMaster=auto -o ControlPersist=1800s',
        )

        self.actions = []

    def _add_action(self, action):
        self.actions.append(action)

    def add_modprobe_action(self, name, state, params=None):
        start_msg = 'INFO: starting change kernel module %s to %s ... ' % (
            name, state)
        succ_msg = ('SUCC: change kernel module %s status to %s '
                    'successfully') % (name, state)
        fail_msg = ('ERROR: change kernel module %s status to %s '
                    'failed') % (name, state)
        args = 'name=%s state=%s' % (name, state)
        if params:
            args = '%s params=%s' % (args, params)
        action = {
            'action': {
                'module': 'modprobe',
                'args': args
            },
            'vars': {
                'start_msg': start_msg,
                'succ_msg': succ_msg,
                'fail_msg': fail_msg,
                'post_label': 'ansible.modprobe',
                'post_label_param': [name, state],
                'exit_on_unreachable': False,
                'exit_on_fail': False
            }
        }
        self._add_action(action)

    def add_command_action(self, command, exit_on_fail=True,
                           exit_on_unreachable=True, with_match=True,
                           callback_on_succ=None, callback_on_fail=None):
        if 'yum' in command and with_match:
            set_yum0 = '''rpm -q zstack-release >/dev/null && releasever=`awk '{print $3}' /etc/zstack-release`;\
                        export YUM0=$releasever; grep $releasever /etc/yum/vars/YUM0 || echo $releasever > /etc/yum/vars/YUM0;'''
            command = set_yum0 + command
        action = {
            'action': {
                'module': 'shell',
                'cmd': command
            },
            'vars': {
                'exit_on_unreachable': exit_on_unreachable,
                'exit_on_fail': exit_on_fail,
                'callback_on_succ': callback_on_succ,
                'callback_on_fail': callback_on_fail
            }
        }
        self._add_action(action)

    def add_copy_action(self, src, dest, args=None):
        start_msg = 'INFO: starting copy %s to %s ... ' % (src, dest)
        succ_msg = ('SUCC: copy %s to %s successfully, the change '
                    'status is PLACEHOLER') % (src, dest)
        fail_msg = 'ERROR: copy %s to %s failed' % (src, dest)
        copy_args = 'src=%s dest=%s' % (src, dest)
        if args:
            copy_args = '%s %s' % (copy_args, args)
        action = {
            'action': {
                'module': 'copy',
                'args': copy_args
            },
            'vars': {
                'start_msg': start_msg,
                'succ_msg': succ_msg,
                'fail_msg': fail_msg,
                'post_label': 'ansible.copy',
                'post_label_param': [src, dest],
                'exit_on_unreachable': False,
                'exit_on_fail': False
            }
        }
        self._add_action(action)

    def run(self):
        self.password = {
            'conn_pass': self.remote_pass,
            'become_pass': self.become_pass
        }
        self.loader = ansible_dataloader.DataLoader()
        self.rc = ResultsCollectorJSONCallbacks(host_post_info=self.host_post_info)
        self.inventory = ansible_im.InventoryManager(
                loader=self.loader,
                sources=self.host_inventory)
        self.variable_manager = ansible_vm.VariableManager(
            loader=self.loader, inventory=self.inventory)

        play_source = dict(
            hosts=self.host,
            tasks=self.actions,
            vars={'ansible_user': self.remote_user,
                  'ansible_port': self.remote_port,
                  'ansible_pipelining': True},
            gather_facts=False,
            ignore_errors= True
        )
        play = ansible_play.Play().load(
            play_source,
            variable_manager=self.variable_manager,
            loader=self.loader)
        self.task_queue_manager = ansible_tqm.TaskQueueManager(
                inventory=self.inventory,
                variable_manager=self.variable_manager,
                loader=self.loader,
                passwords=self.password,
                stdout_callback=self.rc,
                run_additional_callbacks=False)
        try:
            ret = self.task_queue_manager.run(play)
        finally:
            self.task_queue_manager.cleanup()
            if self.loader:
                self.loader.cleanup_all_tmp_files()
        return self.rc.fetch_result()
