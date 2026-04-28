# -*- coding: utf-8 -*-
"""Unit tests for ``vm_plugin._make_usb_redirect_xml``.

Regression coverage for ZSTAC-84629: on aarch64 + RPM-based hosts the
``set_default`` early-return previously dropped the ``set_redirdev``
call, silently disabling USB redirection. These tests pin down each
host/arch/flag combination so the early-return cannot regress without
a failing assertion.
"""
import unittest
from xml.etree import ElementTree as etree

from kvmagent.plugins import vm_plugin


class _FakeStartVmCmd(object):
    """Minimal stand-in for ``StartVmCmd``.

    ``_make_usb_redirect_xml`` only reads four boolean-ish fields, so a
    plain attribute holder is enough -- avoids spinning up the full
    HTTP/agent machinery just to exercise XML emission.
    """

    def __init__(self, usbRedirect=False, coloPrimary=False,
                 coloSecondary=False, useColoBinary=False):
        self.usbRedirect = usbRedirect
        self.coloPrimary = coloPrimary
        self.coloSecondary = coloSecondary
        self.useColoBinary = useColoBinary


def _new_devices_element(graphics_types=('spice',)):
    devices = etree.Element('devices')
    for graphics_type in graphics_types:
        etree.SubElement(devices, 'graphics', {'type': graphics_type})
    return devices


def _controller_indexes(devices):
    return [c.get('index') for c in devices.findall('controller')]


def _controller_models(devices):
    return [c.get('model') for c in devices.findall('controller')]


def _redirdev_addresses(devices):
    return [
        (rd.find('address').get('bus'), rd.find('address').get('port'))
        for rd in devices.findall('redirdev')
    ]


def _spicevmc_channel_count(devices):
    return sum(
        1 for ch in devices.findall('channel')
        if ch.get('type') == 'spicevmc'
    )


class AArch64RpmBasedRedirectTest(unittest.TestCase):
    """Drives the legacy aarch64 RPM-based ``set_default`` branch."""

    def test_redirdev_attached_when_usb_redirect_requested(self):
        # The original ZSTAC-84629 symptom: usbRedirect=true on aarch64
        # + RPM-based host produced zero <redirdev> nodes. After the
        # fix, set_default() is followed by two extra default-model
        # controllers (3, 4) and the four redirdev devices.
        devices = _new_devices_element()

        vm_plugin._make_usb_redirect_xml(
            devices,
            _FakeStartVmCmd(usbRedirect=True),
            dist_name='centos',
            host_arch='aarch64',
        )

        self.assertEqual(['0', '1', '2', '3', '4'],
                         _controller_indexes(devices))
        # set_default + the two added controllers must use libvirt's
        # default qemu-xhci -- never ehci/nec-xhci on this branch.
        self.assertEqual([None] * 5, _controller_models(devices))
        self.assertEqual(1, _spicevmc_channel_count(devices))
        self.assertEqual(
            [('3', '1'), ('3', '2'), ('4', '1'), ('4', '2')],
            _redirdev_addresses(devices),
        )

    def test_no_redirdev_when_usb_redirect_disabled(self):
        # usbRedirect=false must not perturb the legacy controller
        # layout: only 0/1/2 controllers, no redirdev, no spice channel.
        devices = _new_devices_element()

        vm_plugin._make_usb_redirect_xml(
            devices,
            _FakeStartVmCmd(usbRedirect=False),
            dist_name='centos',
            host_arch='aarch64',
        )

        self.assertEqual(['0', '1', '2'], _controller_indexes(devices))
        self.assertEqual([None, None, None], _controller_models(devices))
        self.assertEqual(0, _spicevmc_channel_count(devices))
        self.assertEqual([], _redirdev_addresses(devices))

    def test_colo_primary_skips_redirdev(self):
        # COLO VMs must keep skipping redirdev even though
        # set_default() succeeds and usbRedirect is true.
        devices = _new_devices_element()

        vm_plugin._make_usb_redirect_xml(
            devices,
            _FakeStartVmCmd(usbRedirect=True, coloPrimary=True),
            dist_name='centos',
            host_arch='aarch64',
        )

        self.assertEqual(['0', '1', '2'], _controller_indexes(devices))
        self.assertEqual([], _redirdev_addresses(devices))
        self.assertEqual(0, _spicevmc_channel_count(devices))


class NonDefaultBranchRedirectTest(unittest.TestCase):
    """Drives the ``set_usb2_3`` branch (non-aarch64 or non-RPM)."""

    def test_x86_redirect_uses_ehci_and_nec_xhci_models(self):
        # x86_64 + RPM-based: with_arch(['aarch64']) skips set_default,
        # so set_usb2_3() runs and emits ehci + nec-xhci controllers.
        devices = _new_devices_element()

        vm_plugin._make_usb_redirect_xml(
            devices,
            _FakeStartVmCmd(usbRedirect=True),
            dist_name='centos',
            host_arch='x86_64',
        )

        self.assertEqual(['0', '1', '2', '3', '4'],
                         _controller_indexes(devices))
        self.assertEqual(
            [None, 'ehci', 'nec-xhci', 'ehci', 'nec-xhci'],
            _controller_models(devices),
        )
        self.assertEqual(4, len(_redirdev_addresses(devices)))

    def test_aarch64_non_rpm_uses_set_usb2_3(self):
        # aarch64 + Debian-family: on_redhat_based() rejects 'ubuntu',
        # so set_default returns None and the function falls through
        # to set_usb2_3 + set_redirdev.
        devices = _new_devices_element()

        vm_plugin._make_usb_redirect_xml(
            devices,
            _FakeStartVmCmd(usbRedirect=True),
            dist_name='ubuntu',
            host_arch='aarch64',
        )

        self.assertEqual(['0', '1', '2', '3', '4'],
                         _controller_indexes(devices))
        self.assertEqual(
            [None, 'ehci', 'nec-xhci', 'ehci', 'nec-xhci'],
            _controller_models(devices),
        )
        self.assertEqual(4, len(_redirdev_addresses(devices)))

    def test_loongarch64_uses_nec_xhci_throughout(self):
        # loongarch64 has its own controller-model branch; protect it
        # from regressions while we are reshaping this code path.
        devices = _new_devices_element()

        vm_plugin._make_usb_redirect_xml(
            devices,
            _FakeStartVmCmd(usbRedirect=True),
            dist_name='ubuntu',
            host_arch='loongarch64',
        )

        self.assertEqual(
            [None, 'nec-xhci', 'nec-xhci', 'nec-xhci', 'nec-xhci'],
            _controller_models(devices),
        )
        self.assertEqual(4, len(_redirdev_addresses(devices)))


class ConsoleGraphicsRedirectTest(unittest.TestCase):
    """SPICE transports require an actual SPICE graphics device."""

    def test_vnc_only_skips_spice_redirection(self):
        for dist_name, host_arch in [('centos', 'aarch64'),
                                     ('centos', 'x86_64'),
                                     ('ubuntu', 'aarch64')]:
            devices = _new_devices_element(('vnc',))
            vm_plugin._make_usb_redirect_xml(
                devices, _FakeStartVmCmd(usbRedirect=True),
                dist_name=dist_name, host_arch=host_arch)
            self.assertEqual([], _redirdev_addresses(devices))
            self.assertEqual(0, _spicevmc_channel_count(devices))
            if host_arch == 'aarch64' and dist_name == 'centos':
                self.assertEqual(['0', '1', '2'],
                                 _controller_indexes(devices))

    def test_no_graphics_skips_spice_redirection(self):
        # noConsole can suppress graphics even if the requested mode is SPICE.
        devices = _new_devices_element(())
        vm_plugin._make_usb_redirect_xml(
            devices, _FakeStartVmCmd(usbRedirect=True),
            dist_name='centos', host_arch='aarch64')
        self.assertEqual(['0', '1', '2'], _controller_indexes(devices))
        self.assertEqual([], _redirdev_addresses(devices))
        self.assertEqual(0, _spicevmc_channel_count(devices))

    def test_vnc_and_spice_keeps_redirection(self):
        devices = _new_devices_element(('vnc', 'spice'))
        vm_plugin._make_usb_redirect_xml(
            devices, _FakeStartVmCmd(usbRedirect=True),
            dist_name='centos', host_arch='aarch64')
        self.assertEqual(['0', '1', '2', '3', '4'],
                         _controller_indexes(devices))
        self.assertEqual(4, len(_redirdev_addresses(devices)))
        self.assertEqual(1, _spicevmc_channel_count(devices))


if __name__ == '__main__':
    unittest.main()
