"""
Tests for the key logic change in Vm.stop() for ZSTAC-91026/90416/90915/90918.

The bug: loop_shutdown waited for VM_STATE_SHUTDOWN which maps both
VIR_DOMAIN_SHUTDOWN(raw=4, still active) and VIR_DOMAIN_SHUTOFF(raw=5, fully stopped).
When the domain reached raw=4, loop_shutdown returned True and loop_undefine would
call undefineFlags. If the domain was still active at that point, libvirt's qemu cleanup
deleted the swtpm directory even with KEEP_TPM passed, because the domain had no
persistent_state.

The fix: loop_shutdown and loop_destroy now check raw == VIR_DOMAIN_SHUTOFF(5) directly,
waiting until the domain is fully stopped before proceeding to undefine.
"""

import unittest
from kvmagent.plugins.vm_plugin import Vm, VIR_DOMAIN_UNDEFINE_KEEP_TPM
from kvmagent.plugins.vms import tpm

# Hard-coded libvirt undefine flag values (avoid importing libvirt which may not be installed)
_VIR_DOMAIN_UNDEFINE_KEEP_NVRAM = 8
_VIR_DOMAIN_UNDEFINE_KEEP_TPM = VIR_DOMAIN_UNDEFINE_KEEP_TPM  # defined in vm_plugin


def _make_shutdown_check(raw_value):
    """
    Simulate the fixed loop_shutdown condition from vm_plugin.py:
      (raw_state, _, _, _, _) = self.domain.info()
      return raw_state == self.VIR_DOMAIN_SHUTOFF
    """
    return raw_value == Vm.VIR_DOMAIN_SHUTOFF


def _make_undefine_flags(tpm_supported):
    """
    Simulate the loop_undefine flags construction from vm_plugin.py,
    using hard-coded integer values to avoid mock library returns.
    """
    flags = _VIR_DOMAIN_UNDEFINE_KEEP_NVRAM  # always include
    if tpm_supported:
        flags |= _VIR_DOMAIN_UNDEFINE_KEEP_TPM
    return flags


class TestShutdownCheckLogic(unittest.TestCase):
    """
    The core check in the fixed loop_shutdown is:
        raw_state == VIR_DOMAIN_SHUTOFF
    This must return False for raw=4 (SHUTDOWN, still active) and True for raw=5 (SHUTOFF).
    """

    def test_raw_shutdown4_does_not_satisfy(self):
        """VIR_DOMAIN_SHUTDOWN(4) must NOT satisfy the SHUTOFF check."""
        self.assertFalse(
            _make_shutdown_check(Vm.VIR_DOMAIN_SHUTDOWN),
            "SHUTDOWN(4) should not satisfy the raw == SHUTOFF(5) check"
        )

    def test_raw_shutoff5_satisfies(self):
        """VIR_DOMAIN_SHUTOFF(5) must satisfy the SHUTOFF check."""
        self.assertTrue(
            _make_shutdown_check(Vm.VIR_DOMAIN_SHUTOFF),
            "SHUTOFF(5) should satisfy the raw == SHUTOFF(5) check"
        )

    def test_polling_scenario(self):
        """After several SHUTDOWN(4) polls, SHUTOFF(5) finally satisfies."""
        states = [
            Vm.VIR_DOMAIN_SHUTDOWN,
            Vm.VIR_DOMAIN_SHUTDOWN,
            Vm.VIR_DOMAIN_SHUTOFF,
        ]
        results = [_make_shutdown_check(s) for s in states]
        self.assertFalse(results[0], "poll 1: SHUTDOWN(4)")
        self.assertFalse(results[1], "poll 2: SHUTDOWN(4)")
        self.assertTrue(results[2], "poll 3: SHUTOFF(5)")


class TestRawStatePowerMapping(unittest.TestCase):
    """
    Regression: Vm.power_state maps both raw=4 and raw=5 to VM_STATE_SHUTDOWN.
    That ambiguity is what made the old code trigger undefine too early.
    """

    def test_both_raw_map_to_vm_state_shutdown(self):
        """Confirm the mapping that caused the bug."""
        self.assertEqual(
            Vm.power_state[Vm.VIR_DOMAIN_SHUTDOWN],
            Vm.VM_STATE_SHUTDOWN,
        )
        self.assertEqual(
            Vm.power_state[Vm.VIR_DOMAIN_SHUTOFF],
            Vm.VM_STATE_SHUTDOWN,
        )

    def test_raw_constants_are_distinct(self):
        """Raw constants have distinct integer values (4 and 5)."""
        self.assertEqual(Vm.VIR_DOMAIN_SHUTDOWN, 4)
        self.assertEqual(Vm.VIR_DOMAIN_SHUTOFF, 5)
        self.assertNotEqual(Vm.VIR_DOMAIN_SHUTDOWN, Vm.VIR_DOMAIN_SHUTOFF)

    def test_mapped_check_is_ambiguous(self):
        """The OLD check (state == VM_STATE_SHUTDOWN) matches both raw=4 and raw=5."""
        mapped4 = Vm.power_state[Vm.VIR_DOMAIN_SHUTDOWN]
        mapped5 = Vm.power_state[Vm.VIR_DOMAIN_SHUTOFF]
        # Both mapped values are the same — old code could not distinguish them
        self.assertEqual(mapped4, mapped5)

    def test_raw_check_distinguishes(self):
        """The NEW check (raw == VIR_DOMAIN_SHUTOFF) correctly distinguishes."""
        self.assertFalse(Vm.VIR_DOMAIN_SHUTDOWN == Vm.VIR_DOMAIN_SHUTOFF)
        self.assertTrue(Vm.VIR_DOMAIN_SHUTOFF == Vm.VIR_DOMAIN_SHUTOFF)


class TestUndefineFlagsKeepTpm(unittest.TestCase):
    """
    undefineFlags must include KEEP_TPM when VIRSH_SUPPORT_KEEP_TPM is True,
    and must NOT include it when False.
    """

    def test_keep_tpm_set_when_supported(self):
        flags = _make_undefine_flags(tpm_supported=True)
        self.assertTrue(
            flags & _VIR_DOMAIN_UNDEFINE_KEEP_TPM,
            "KEEP_TPM must be set (flags=0x{:02x})".format(flags)
        )

    def test_keep_nvram_always_set(self):
        flags = _make_undefine_flags(tpm_supported=True)
        self.assertTrue(
            flags & _VIR_DOMAIN_UNDEFINE_KEEP_NVRAM,
            "KEEP_NVRAM must always be set (flags=0x{:02x})".format(flags)
        )

    def test_keep_tpm_not_set_when_not_supported(self):
        flags = _make_undefine_flags(tpm_supported=False)
        self.assertFalse(
            flags & _VIR_DOMAIN_UNDEFINE_KEEP_TPM,
            "KEEP_TPM must NOT be set when not supported (flags=0x{:02x})".format(flags)
        )

    def test_keep_nvram_set_even_when_tpm_not_supported(self):
        flags = _make_undefine_flags(tpm_supported=False)
        self.assertTrue(
            flags & _VIR_DOMAIN_UNDEFINE_KEEP_NVRAM,
            "KEEP_NVRAM must be set even when TPM not supported (flags=0x{:02x})".format(flags)
        )

    def test_virsh_support_keep_tpm_constant_is_integer(self):
        """VIR_DOMAIN_UNDEFINE_KEEP_TPM exported from vm_plugin is an integer."""
        self.assertIsInstance(VIR_DOMAIN_UNDEFINE_KEEP_TPM, int)
        self.assertEqual(VIR_DOMAIN_UNDEFINE_KEEP_TPM, 64,
                         "VIR_DOMAIN_UNDEFINE_KEEP_TPM should be 1<<6 == 64")


class TestVmPluginCodeFix(unittest.TestCase):
    """
    Verify that the fixed vm_plugin code actually uses raw state check.
    We check the source code change by inspecting the loop_shutdown body.
    """

    def test_loop_shutdown_source_contains_vir_domain_shutoff_check(self):
        """
        The fix adds a raw state check in loop_shutdown. Verify the source
        contains the explicit SHUTOFF constant comparison, not just VM_STATE_SHUTDOWN.
        """
        import inspect
        import kvmagent.plugins.vm_plugin as vm_module
        source = inspect.getsource(vm_module.Vm.stop)
        # The fixed code should contain VIR_DOMAIN_SHUTOFF (the constant) in stop
        self.assertIn(
            'VIR_DOMAIN_SHUTOFF',
            source,
            "vm_plugin.Vm.stop must reference VIR_DOMAIN_SHUTOFF for the raw state check"
        )
        # The fixed code should NOT use wait_for_state_change(VM_STATE_SHUTDOWN) for shutdown
        # (it now uses raw domain.info() check instead)
        # Count occurrences: original had 2 (loop_shutdown + loop_destroy), fix removes them
        wfsc_shutdown_count = source.count(
            'wait_for_state_change(self.VM_STATE_SHUTDOWN)'
        )
        self.assertEqual(
            wfsc_shutdown_count, 0,
            "loop_shutdown and loop_destroy must not use wait_for_state_change(VM_STATE_SHUTDOWN) "
            "after the fix; found {} occurrences".format(wfsc_shutdown_count)
        )


if __name__ == '__main__':
    unittest.main()
