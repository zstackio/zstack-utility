from unittest import TestCase

try:
    import mock
except ImportError:
    from unittest import mock

from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils
from zstacklib.utils import http, jsonobject, xmlobject

_MISSING = object()


class TestCpuHotplugOnline(TestCase):
    def _new_vm(self, domain_xml='<domain><name>vm-uuid</name></domain>'):
        vm = vm_plugin.Vm()
        vm.uuid = 'vm-uuid'
        vm.domain = object()
        vm.domain_xmlobject = xmlobject.loads(domain_xml)
        return vm

    def _run_qga(self, guest_os, vcpus, domain_xml=None, state='Running',
                 command_errors=None, set_results=None, get_results=None,
                 target_cpu_num=None, return_sleep=False):
        vm = self._new_vm(domain_xml or '<domain><name>vm-uuid</name></domain>')
        qga = mock.Mock()
        qga.state = state
        qga.os = guest_os
        calls = []
        command_errors = command_errors or {}
        set_results = iter(set_results) if set_results is not None else None
        get_results = iter(get_results) if get_results is not None else None

        if target_cpu_num is None:
            logical_ids = [vcpu.get('logical-id') for vcpu in vcpus
                           if isinstance(vcpu, dict)
                           and isinstance(vcpu.get('logical-id'), (int, long))
                           and not isinstance(vcpu.get('logical-id'), bool)] \
                if isinstance(vcpus, list) else []
            target_cpu_num = max(logical_ids) + 1 if logical_ids else 5

        def call_qga(command, args=None):
            calls.append((command, args))
            if command in command_errors:
                raise command_errors[command]
            if command == 'guest-get-vcpus':
                if get_results is not None:
                    return next(get_results)
                return vcpus
            if command == 'guest-set-vcpus':
                if set_results is not None:
                    return next(set_results)
                return len(args['vcpus'])
            return None

        qga.call_qga_command.side_effect = call_qga
        with mock.patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
                mock.patch.object(vm_plugin, 'VmQga') as qga_class, \
                mock.patch.object(vm_plugin.time, 'sleep') as sleep:
            qga_class.QGA_STATE_RUNNING = 'Running'
            qga_class.return_value = qga
            vm._qga_online_hotplugged_cpus(4, target_cpu_num)
        if return_sleep:
            return calls, sleep
        return calls

    def test_ubuntu_and_debian_payload_only_contains_new_offline_cpus(self):
        vcpus = [
            {'logical-id': 0, 'online': True},
            {'logical-id': 2, 'online': False},
            {'logical-id': 4, 'online': False},
            {'logical-id': 5, 'online': False},
            {'logical-id': 6, 'online': True},
        ]
        expected = {'vcpus': [
            {'logical-id': 4, 'online': True},
            {'logical-id': 5, 'online': True},
        ]}

        for guest_os in ('Ubuntu 22.04 LTS', 'Debian GNU/Linux 12'):
            calls, sleep = self._run_qga(
                guest_os,
                vcpus,
                return_sleep=True,
            )
            self.assertEqual(
                [('guest-get-vcpus', None), ('guest-set-vcpus', expected)],
                calls,
            )
            self.assertEqual([], sleep.call_args_list)

    def test_non_x86_skips_before_constructing_qga(self):
        vm = self._new_vm()
        with mock.patch.object(vm_plugin, 'HOST_ARCH', 'aarch64'), \
                mock.patch.object(vm_plugin, 'VmQga') as qga_class:
            vm._qga_online_hotplugged_cpus(4, 8)
        qga_class.assert_not_called()

    def test_empty_and_non_whitelist_os_skip(self):
        for guest_os in (None, '', 'CentOS 7', 'Kylin V10', 'Windows Server'):
            calls = self._run_qga(
                guest_os,
                [{'logical-id': 4, 'online': False}],
            )
            self.assertEqual([], calls)

    def test_qga_not_running_skips(self):
        calls = self._run_qga(
            'Ubuntu 22.04',
            [{'logical-id': 4, 'online': False}],
            state='NotRunning',
        )
        self.assertEqual([], calls)

    def test_existing_smbios_skips_qga_set(self):
        domain_xml = '''
        <domain>
          <name>vm-uuid</name>
          <sysinfo type="smbios"><system>
            <entry name="manufacturer">Microsoft Corporation</entry>
            <entry name="product">Virtual Machine</entry>
          </system></sysinfo>
        </domain>
        '''
        vm = self._new_vm(domain_xml)
        self.assertTrue(vm._has_smbios_cpu_hotplug())
        calls = self._run_qga(
            'Ubuntu 22.04',
            [{'logical-id': 4, 'online': False}],
            domain_xml=domain_xml,
        )
        self.assertEqual([], calls)

    def test_incomplete_smbios_does_not_match(self):
        vm = self._new_vm('''
        <domain>
          <name>vm-uuid</name>
          <sysinfo type="smbios"><system>
            <entry name="manufacturer">Microsoft Corporation</entry>
          </system></sysinfo>
        </domain>
        ''')
        self.assertFalse(vm._has_smbios_cpu_hotplug())

    def test_empty_and_all_online_vcpu_lists_do_not_call_guest_set(self):
        calls = self._run_qga(
            'Debian 12',
            [{'logical-id': cpu_id, 'online': True} for cpu_id in range(8)],
        )
        self.assertEqual([('guest-get-vcpus', None)], calls)

    def test_waits_for_guest_to_enumerate_hotplugged_cpus(self):
        old_vcpus = [{'logical-id': cpu_id, 'online': True}
                     for cpu_id in range(4)]
        complete_vcpus = old_vcpus + [
            {'logical-id': 4, 'online': False},
            {'logical-id': 5, 'online': False},
        ]

        calls, sleep = self._run_qga(
            'Ubuntu 22.04',
            complete_vcpus,
            get_results=(old_vcpus, complete_vcpus),
            target_cpu_num=6,
            return_sleep=True,
        )

        self.assertEqual([
            ('guest-get-vcpus', None),
            ('guest-get-vcpus', None),
            ('guest-set-vcpus', {'vcpus': [
                {'logical-id': 4, 'online': True},
                {'logical-id': 5, 'online': True},
            ]}),
        ], calls)
        self.assertEqual(
            [mock.call(vm_plugin._QGA_CPU_ENUM_RETRY_INTERVAL)],
            sleep.call_args_list,
        )

    def test_guest_cpu_enumeration_timeout_is_fail_open(self):
        old_vcpus = [{'logical-id': cpu_id, 'online': True}
                     for cpu_id in range(4)]
        with mock.patch.object(vm_plugin.logger, 'warning') as warning:
            calls, sleep = self._run_qga(
                'Debian 12',
                old_vcpus,
                target_cpu_num=6,
                return_sleep=True,
            )

        self.assertEqual(
            [('guest-get-vcpus', None)] * vm_plugin._QGA_CPU_ENUM_RETRY_TIMES,
            calls,
        )
        self.assertEqual(
            [mock.call(vm_plugin._QGA_CPU_ENUM_RETRY_INTERVAL)]
            * (vm_plugin._QGA_CPU_ENUM_RETRY_TIMES - 1),
            sleep.call_args_list,
        )
        warning.assert_called_once_with(
            'timed out waiting for guest to enumerate hotplugged CPUs '
            'for vm[uuid:vm-uuid], missing CPUs [4, 5]'
        )

    def test_qga_exception_is_fail_open(self):
        vm = self._new_vm()
        with mock.patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
                mock.patch.object(vm_plugin, 'VmQga', side_effect=Exception('QGA timeout')):
            vm._qga_online_hotplugged_cpus(4, 8)

    def test_guest_get_vcpus_exception_is_fail_open(self):
        calls = self._run_qga(
            'Ubuntu 22.04',
            None,
            command_errors={'guest-get-vcpus': Exception('unsupported command')},
        )
        self.assertEqual([('guest-get-vcpus', None)], calls)

    def test_guest_set_vcpus_exception_is_fail_open(self):
        expected = {'vcpus': [{'logical-id': 4, 'online': True}]}
        with mock.patch.object(vm_plugin.logger, 'warning') as warning:
            calls = self._run_qga(
                'Debian 12',
                [{'logical-id': 4, 'online': False}],
                command_errors={'guest-set-vcpus': Exception('QGA timeout')},
            )
        self.assertEqual(
            [('guest-get-vcpus', None), ('guest-set-vcpus', expected)],
            calls,
        )
        warning.assert_called_once()

    def test_guest_set_vcpus_partial_then_full_retries_unprocessed_suffix(self):
        vcpus = [
            {'logical-id': 4, 'online': False},
            {'logical-id': 5, 'online': False},
            {'logical-id': 6, 'online': False},
        ]
        calls = self._run_qga('Ubuntu 22.04', vcpus, set_results=(1, 2))
        self.assertEqual([
            ('guest-get-vcpus', None),
            ('guest-set-vcpus', {'vcpus': [
                {'logical-id': 4, 'online': True},
                {'logical-id': 5, 'online': True},
                {'logical-id': 6, 'online': True},
            ]}),
            ('guest-set-vcpus', {'vcpus': [
                {'logical-id': 5, 'online': True},
                {'logical-id': 6, 'online': True},
            ]}),
        ], calls)

    def test_guest_set_vcpus_persistent_partial_progress_is_bounded(self):
        vcpus = [{'logical-id': cpu_id, 'online': False}
                 for cpu_id in range(4, 8)]
        calls = self._run_qga(
            'Debian 12',
            vcpus,
            set_results=(1, 1, 1, 1),
        )
        set_calls = [call for call in calls if call[0] == 'guest-set-vcpus']
        self.assertEqual(4, len(set_calls))
        self.assertEqual([4, 3, 2, 1],
                         [len(call[1]['vcpus']) for call in set_calls])

    def test_guest_set_vcpus_zero_stops_retry_with_warning(self):
        vcpus = [
            {'logical-id': 4, 'online': False},
            {'logical-id': 5, 'online': False},
        ]
        with mock.patch.object(vm_plugin.logger, 'warning') as warning:
            calls = self._run_qga(
                'Ubuntu 22.04',
                vcpus,
                set_results=(0, 2),
            )
        self.assertEqual(2, len(calls))
        self.assertEqual('guest-set-vcpus', calls[-1][0])
        warning.assert_called_once()

    def test_guest_set_vcpus_invalid_result_stops_retry_with_warning(self):
        vcpus = [
            {'logical-id': 4, 'online': False},
            {'logical-id': 5, 'online': False},
        ]
        for result in (None, '1', -1, 3, True):
            with mock.patch.object(vm_plugin.logger, 'warning') as warning:
                calls = self._run_qga(
                    'Ubuntu 22.04',
                    vcpus,
                    set_results=(result, 2),
                )
            self.assertEqual(2, len(calls))
            self.assertEqual('guest-set-vcpus', calls[-1][0])
            warning.assert_called_once()

    def test_malformed_and_non_dict_vcpu_replies_are_safe_noops(self):
        malformed_replies = (
            object(),
            'not-a-vcpu-list',
            {'unexpected': 'reply'},
            [None, 'invalid-entry', 7, {}],
        )
        for reply in malformed_replies:
            calls = self._run_qga('Ubuntu 22.04', reply)
            self.assertEqual([('guest-get-vcpus', None)], calls)


class TestCpuHotplugSmbios(TestCase):
    def _build_vm(self, guest_os=_MISSING, arch='x86_64', oem_strings=None):
        cmd = vm_utils.create_startvm_body_jsonobject()
        if guest_os is not _MISSING:
            cmd.guestOsType = guest_os
        if oem_strings is not None:
            cmd.oemStrings = oem_strings
        cmd.architecture = arch
        if arch == 'aarch64':
            cmd.bootMode = 'UEFI'

        with mock.patch.object(vm_plugin, 'HOST_ARCH', arch), \
                mock.patch.object(vm_plugin.kvmagent, 'host_arch', arch):
            return vm_plugin.Vm.from_StartVmCmd(cmd)

    @staticmethod
    def _system_entries(vm):
        sysinfo = vm.domain_xmlobject.get_child_node('sysinfo')
        system = sysinfo.get_child_node('system')
        return [(entry.name_, entry.text_)
                for entry in system.get_child_node_as_list('entry')]

    def test_ubuntu_and_debian_x86_emit_smbios_and_preserve_sysinfo(self):
        for guest_os in ('Ubuntu 22.04 LTS', 'Debian 12'):
            vm = self._build_vm(guest_os)
            smbios = vm.domain_xmlobject.os.get_child_node('smbios')
            self.assertIsNotNone(smbios)
            self.assertEqual('sysinfo', smbios.mode_)

            entries = self._system_entries(vm)
            self.assertIn(('serial', '4f3e9046-776d-4095-8edd-909523ede46d'), entries)
            self.assertEqual(1, entries.count(('manufacturer', 'Microsoft Corporation')))
            self.assertEqual(1, entries.count(('product', 'Virtual Machine')))
            self.assertEqual('www.zstack.io',
                             vm.domain_xmlobject.sysinfo.chassis.entry.text_)

    def test_ubuntu_x86_preserves_oem_strings(self):
        expected = ['oem-entry-one', 'oem-entry-two']
        vm = self._build_vm('Ubuntu 22.04', oem_strings=expected)
        oem_strings = vm.domain_xmlobject.sysinfo.get_child_node('oemStrings')
        actual = [entry.text_
                  for entry in oem_strings.get_child_node_as_list('entry')]
        self.assertEqual(expected, actual)

    def test_missing_guest_os_attribute_is_mixed_version_safe(self):
        cmd = vm_utils.create_startvm_body_jsonobject()
        self.assertNotIn('guestOsType', cmd.__dict__)
        cmd.architecture = 'x86_64'

        with mock.patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
                mock.patch.object(vm_plugin.kvmagent, 'host_arch', 'x86_64'):
            vm = vm_plugin.Vm.from_StartVmCmd(cmd)

        names = [name for name, _ in self._system_entries(vm)]
        self.assertNotIn('manufacturer', names)
        self.assertNotIn('product', names)

    def test_empty_and_non_whitelist_os_do_not_emit_hotplug_entries(self):
        for guest_os in (None, '', 'CentOS 7', 'Kylin V10'):
            vm = self._build_vm(guest_os)
            names = [name for name, _ in self._system_entries(vm)]
            self.assertNotIn('manufacturer', names)
            self.assertNotIn('product', names)

    def test_non_x86_does_not_emit_hotplug_entries(self):
        vm = self._build_vm('Ubuntu 22.04', arch='aarch64')
        names = [name for name, _ in self._system_entries(vm)]
        self.assertNotIn('manufacturer', names)
        self.assertNotIn('product', names)


class TestCpuHotplugHandlers(TestCase):
    def test_cpumem_without_cpu_increase_skips_qga(self):
        vm = mock.Mock()
        vm.get_cpu_num.return_value = 4
        vm.get_memory.return_value = 8 * 1024 * 1024 * 1024
        req = {
            http.REQUEST_BODY: jsonobject.dumps({
                'vmUuid': 'vm-uuid',
                'cpuNum': 4,
                'memorySize': 9 * 1024 * 1024 * 1024,
            })
        }

        with mock.patch.object(vm_plugin, 'get_vm_by_uuid', return_value=vm):
            rsp = jsonobject.loads(vm_plugin.VmPlugin().online_change_cpumem(req))

        self.assertTrue(rsp.success)
        vm.hotplug_mem.assert_called_once_with(9 * 1024 * 1024 * 1024)
        vm.hotplug_cpu.assert_called_once_with(4)
        vm._qga_online_hotplugged_cpus.assert_not_called()

    def test_cpu_increase_calls_qga_with_previous_cpu_count(self):
        vm = mock.Mock()
        vm.get_cpu_num.side_effect = (4, 8, 8)
        req = {
            http.REQUEST_BODY: jsonobject.dumps({
                'vmUuid': 'vm-uuid',
                'cpuNum': 8,
            })
        }

        with mock.patch.object(vm_plugin, 'get_vm_by_uuid', return_value=vm):
            rsp = jsonobject.loads(vm_plugin.VmPlugin().online_increase_cpu(req))

        self.assertTrue(rsp.success)
        self.assertEqual(8, rsp.cpuNum)
        self.assertEqual(3, vm.get_cpu_num.call_count)
        vm.hotplug_cpu.assert_called_once_with(8)
        vm._qga_online_hotplugged_cpus.assert_called_once_with(4, 8)
        self.assertLess(
            vm.method_calls.index(mock.call.hotplug_cpu(8)),
            vm.method_calls.index(mock.call._qga_online_hotplugged_cpus(4, 8)),
        )

    def test_cpumem_cpu_increase_calls_qga_with_previous_cpu_count(self):
        vm = mock.Mock()
        vm.get_cpu_num.side_effect = (4, 8)
        vm.get_memory.return_value = 9 * 1024 * 1024 * 1024
        req = {
            http.REQUEST_BODY: jsonobject.dumps({
                'vmUuid': 'vm-uuid',
                'cpuNum': 8,
                'memorySize': 9 * 1024 * 1024 * 1024,
            })
        }

        with mock.patch.object(vm_plugin, 'get_vm_by_uuid', return_value=vm):
            rsp = jsonobject.loads(vm_plugin.VmPlugin().online_change_cpumem(req))

        self.assertTrue(rsp.success)
        self.assertEqual(8, rsp.cpuNum)
        self.assertEqual(9 * 1024 * 1024 * 1024, rsp.memorySize)
        vm.hotplug_mem.assert_called_once_with(9 * 1024 * 1024 * 1024)
        vm.hotplug_cpu.assert_called_once_with(8)
        vm._qga_online_hotplugged_cpus.assert_called_once_with(4, 8)
        expected_hotplug_order = [
            mock.call.hotplug_mem(9 * 1024 * 1024 * 1024),
            mock.call.hotplug_cpu(8),
            mock.call._qga_online_hotplugged_cpus(4, 8),
        ]
        self.assertEqual(
            expected_hotplug_order,
            [call for call in vm.method_calls if call in expected_hotplug_order],
        )
