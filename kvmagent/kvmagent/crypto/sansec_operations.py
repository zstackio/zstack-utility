import glob
import json
import os
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

from zstacklib.utils import log, sansec_utils, shell
from zstacklib.utils.sansec_utils import CommandError, OperationStatus, ValidationError
from kvmagent.crypto import sansec_config, sansec_health

MODULE_CONFIG = sansec_utils.MODULE_CONFIG
PROC_ROOT = '/proc'
logger = log.get_logger(__name__)


def sync_directory(path):
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def create_directory(path):
    parent = os.path.dirname(path)
    if parent == path:
        return
    create_directory(parent)
    try:
        os.mkdir(path, mode=0o700)
    except FileExistsError:
        if not os.path.isdir(path):
            raise
    sync_directory(parent)


def atomic_write(path, content):
    directory = os.path.dirname(path)
    create_directory(directory)
    fd, temporary = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SansecOperations(object):
    def __init__(self, detector):
        self.detector = detector
        self.pending = None

    def is_busy(self):
        return self.pending is not None and self.pending.poll() is None

    @staticmethod
    def read(path):
        with open(path) as source:
            return source.read().strip()

    def run(self, arguments):
        process = shell.get_process(arguments, shell=False, pipe=True, workdir='/')
        try:
            stdout, _ = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            if not sansec_utils.terminate_process(process):
                self.pending = process
            raise CommandError('%s timed out; hardware outcome is unknown' % arguments[0])
        if process.returncode:
            raise CommandError('%s exited with code %s' % (arguments[0], process.returncode))
        return stdout.decode('utf-8')

    def inventory(self):
        devices = sansec_health.SYSFS_DEVICES
        pfs = {}
        bound = set()
        for address in os.listdir(devices):
            path = os.path.join(devices, address)
            try:
                vendor, device = self.read(path + '/vendor'), self.read(path + '/device')
            except FileNotFoundError:
                if os.path.exists(path):
                    raise
                continue
            if sansec_utils.driver_loaded(path):
                bound.add(address)
            if not sansec_utils.supported_device(vendor, device) or os.path.exists(path + '/physfn'):
                continue
            vfs = sorted(os.path.basename(os.path.realpath(vf)) for vf in glob.glob(path + '/virtfn*'))
            total = (sansec_utils.parse_int(self.read(path + '/sriov_totalvfs'))
                     if os.path.exists(path + '/sriov_totalvfs') else 0)
            pfs[address] = dict(vfs=vfs, total=total)
        return pfs, bound

    def assert_idle(self, pfs):
        protected = set(pfs)
        for device in pfs.values():
            protected.update(device['vfs'])
        groups = set()
        for address in protected:
            group = os.path.join(sansec_health.SYSFS_DEVICES, address, 'iommu_group')
            if not os.path.exists(group):
                raise ValidationError('Cannot verify IOMMU group for %s' % address)
            groups.add(os.path.basename(os.path.realpath(group)))
        for pid in os.listdir(PROC_ROOT):
            if not pid.isdigit():
                continue
            try:
                directory = os.path.join(PROC_ROOT, pid, 'fd')
                for fd in os.listdir(directory):
                    try:
                        target = os.readlink(os.path.join(directory, fd))
                    except FileNotFoundError:
                        continue
                    if target.startswith('/dev/vfio/') and target.rsplit('/', 1)[-1] in groups:
                        raise ValidationError('A Sansec IOMMU group has an active VFIO consumer')
            except FileNotFoundError:
                continue
        for uuid in self.run(['virsh', 'list', '--uuid']).split():
            domain = ET.fromstring(self.run(['virsh', 'dumpxml', uuid]))
            for address in domain.findall("./devices/hostdev[@type='pci']/source/address"):
                fields = [address.get(key) for key in ('domain', 'bus', 'slot', 'function')]
                if any(value is None for value in fields):
                    raise ValidationError('Active VM PCI address is incomplete')
                bdf = '%04x:%02x:%02x.%x' % tuple(sansec_utils.parse_int(value, 16) for value in fields)
                if bdf in protected:
                    raise ValidationError('An active VM consumes a Sansec device')

    def prepare(self, record):
        if self.is_busy():
            raise ValidationError('Previous Sansec command has not exited')
        if self.detector.is_busy():
            raise ValidationError('Previous Sansec SDK worker has not exited')
        self.converge()
        config = sansec_config.read_config(sansec_health.CONFIG_PATH)
        sriov = config.get('sriov', {})
        if not isinstance(sriov, dict) or sriov.get('enabled') is not True or sriov.get('restoreVfnum') != -1:
            raise ValidationError('Sansec SR-IOV requires an explicit enabled profile with restoreVfnum=-1')
        pfs, bound = self.inventory()
        managed = {address for address in pfs
                   if not sansec_utils.is_companion_function(os.path.join(sansec_health.SYSFS_DEVICES, address))}
        if set(record['pciDeviceAddresses']) != managed:
            raise ValidationError('Operation scope must cover every Sansec PF on the host')
        covered = set(pfs)
        for device in pfs.values():
            covered.update(device['vfs'])
        if not bound.issubset(covered):
            raise ValidationError('swcsm also controls devices outside the requested scope')
        target = record['pciDeviceAddress']
        profile = config['devices'].get(target)
        if not profile or profile['compatible'] is not True or target not in bound:
            raise ValidationError('Target PF requires a compatible Sansec profile and loaded driver')
        version = sansec_utils.driver_version(os.path.join(sansec_health.SYSFS_DEVICES, target),
                                              profile.get('driverVersionSource', 'version'))
        if version != profile['driverVersion']:
            raise ValidationError('Loaded Sansec driver differs from the configured profile')
        desired = record['vfCount'] if record['operation'] == 'Split' else 0
        expected = {address: len(device['vfs']) for address, device in pfs.items()}
        expected[target] = desired
        record.update(expected=expected, moduleParameter=desired if desired else -1)
        if self.applied(record):
            return True
        if not pfs[target]['total'] or desired > pfs[target]['total']:
            raise ValidationError('Target PF has insufficient SR-IOV capacity')
        if record['operation'] == 'Split':
            if desired <= 0 or pfs[target]['vfs']:
                raise ValidationError('Use a positive VF count on an unsplit PF')
        elif not pfs[target]['vfs']:
            raise ValidationError('Target PF is not split')
        if any(device['total'] and expected[address] != desired for address, device in pfs.items()):
            raise ValidationError('Module-wide VFnum would change another PF topology')
        self.assert_idle(pfs)
        return False

    @staticmethod
    def query(arguments):
        try:
            return shell.call(' '.join(arguments))
        except shell.ShellError as error:
            raise CommandError(str(error))

    def effective_vfnum(self):
        values = re.findall(r'^options\s+swcsm\s.*\bVFnum=(-?\d+)', self.query(['modprobe', '-c']), re.M)
        return int(values[-1]) if values else None

    def applied(self, record):
        return self.matches(record) and self.effective_vfnum() == record['moduleParameter']

    def converge(self):
        if self.is_busy() or not os.path.exists(MODULE_CONFIG) or self.inventory()[1]:
            return
        self.run(['modprobe', 'swcsm'])
        logger.warning('Loaded swcsm with the effective VFnum=%s', self.effective_vfnum())

    def submit(self, command):
        record = dict(operation=command.operation,
                      pciDeviceAddresses=sorted(a.lower() for a in command.pciDeviceAddresses),
                      pciDeviceAddress=command.pciDeviceAddress.lower() if command.pciDeviceAddress else None,
                      vfCount=command.vfCount, status=OperationStatus.UNKNOWN)
        try:
            if self.prepare(record):
                record.update(status=OperationStatus.SUCCEEDED, vfCounts=record['expected'])
                return record
            atomic_write(MODULE_CONFIG, 'options swcsm VFnum=%s\n' % record['moduleParameter'])
            if self.effective_vfnum() != record['moduleParameter']:
                raise ValidationError('Another modprobe configuration overrides swcsm VFnum')
        except (OSError, ValidationError, CommandError, json.JSONDecodeError, ET.ParseError) as error:
            record.update(status=OperationStatus.FAILED, reason=str(error))
            logger.error('Sansec operation[type:%s, pf:%s] failed during preparation: %s' %
                         (record['operation'], record['pciDeviceAddress'], error))
            return record
        stage = 'unload driver'
        try:
            self.run(['modprobe', '-r', 'swcsm'])
            stage = 'load driver'
            self.run(['modprobe', 'swcsm'])
            stage = 'verify topology'
            deadline = time.monotonic() + 10
            while not self.matches(record):
                if time.monotonic() >= deadline:
                    raise CommandError('Observed Sansec topology does not match the requested operation')
                time.sleep(0.2)
            record.update(status=OperationStatus.SUCCEEDED, vfCounts=record['expected'])
        except (OSError, ValidationError, CommandError) as error:
            record['reason'] = str(error)
            logger.error('Sansec operation[type:%s, pf:%s] remains Unknown during %s: %s' %
                         (record['operation'], record['pciDeviceAddress'], stage, error))
        return record

    def matches(self, record):
        pfs, bound = self.inventory()
        return (set(pfs) == set(record['expected']) and record['pciDeviceAddress'] in bound
                and all(len(device['vfs']) == record['expected'][address] for address, device in pfs.items()))
