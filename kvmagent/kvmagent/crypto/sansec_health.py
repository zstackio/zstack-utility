import errno
import glob
import json
import os
import re
import stat
import shutil
import subprocess
import sys
import tempfile
import time

from kvmagent.crypto import sansec_config
from zstacklib.utils import sansec_sdk, sansec_utils, shell
from zstacklib.utils.sansec_utils import HealthStatus, Qualification, SdkPhase, SdkStatus, ValidationError

CONFIG_PATH = '/var/lib/zstack/crypto/sansec-health.json'
SYSFS_DEVICES = sansec_utils.SYSFS_DEVICES
SDK_DEVICE_GLOB = '/dev/swcsm*'


class SansecHealthDetector(object):
    def __init__(self):
        self.failures = {}
        self.config = None
        self.pending = None

    def is_busy(self):
        return self.pending is not None and self.pending[0].poll() is None

    def unavailable(self, addresses, reason):
        self.failures.clear()
        return [dict(pciDeviceAddress=a, healthStatus=HealthStatus.UNKNOWN,
                     qualification=Qualification.UNVERIFIED, reason=reason)
                for a in addresses]

    @staticmethod
    def system_check(address, present):
        if address.lower() not in present:
            return HealthStatus.FAULT, 'Requested PCI device is no longer enumerated'
        path = os.path.join(SYSFS_DEVICES, address.lower())
        with open(os.path.join(path, 'vendor')) as source:
            vendor = source.read().strip().lower()
        with open(os.path.join(path, 'device')) as source:
            device = source.read().strip().lower()
        if not sansec_utils.supported_device(vendor, device) or os.path.exists(os.path.join(path, 'physfn')):
            return HealthStatus.UNKNOWN, 'Requested PCI device is not a supported Sansec PF'
        if not sansec_utils.driver_loaded(path):
            return HealthStatus.UNKNOWN, 'Sansec PF driver is not loaded'
        return None, None

    @staticmethod
    def check_sdk_endpoint(present, selected):
        bound = []
        for address in present:
            try:
                driver = os.readlink(os.path.join(SYSFS_DEVICES, address, 'driver'))
            except OSError as error:
                if error.errno == errno.ENOENT:
                    continue
                raise
            if os.path.basename(driver) == 'swcsm':
                bound.append(address)
        if len(selected) != 1:
            raise ValidationError('SDK requires one configured PF; per-card selection is not documented')
        primary = next(iter(selected)).lower()
        if bound != [primary]:
            functions = {primary.rsplit('.', 1)[0] + '.' + str(n) for n in range(4)}
            if not primary.endswith('.0') or set(bound) != functions:
                raise ValidationError('SDK requires one Sansec card with an unambiguous physical-function layout')
            for address in functions:
                path = os.path.join(SYSFS_DEVICES, address)
                with open(os.path.join(path, 'vendor')) as vendor, open(os.path.join(path, 'device')) as device:
                    supported = (vendor.read().strip() == '0x' + sansec_utils.VENDOR_ID
                                 and device.read().strip() == '0x' + sansec_utils.PF_DEVICE_ID)
                if not supported or os.path.exists(os.path.join(path, 'physfn')):
                    raise ValidationError('Sansec companion functions must be supported physical devices')
                capacity = os.path.join(path, 'sriov_totalvfs')
                if address == primary:
                    with open(capacity) as total:
                        if sansec_utils.parse_int(total.read()) <= 0:
                            raise ValidationError('Sansec primary function must provide SR-IOV')
                elif os.path.exists(capacity):
                    raise ValidationError('Several SR-IOV PFs cannot share an SDK health result')
        nodes = glob.glob(SDK_DEVICE_GLOB)
        states = [os.stat(node) for node in nodes]
        if not nodes or any(not stat.S_ISCHR(state.st_mode) for state in states):
            raise ValidationError('SDK requires Sansec character devices')
        if len(nodes) == 1:
            return
        names = [re.fullmatch(r'(swcsm-pci\d+)-([0-3])', os.path.basename(node)) for node in nodes]
        if (len(bound) != 4 or len(nodes) != 4 or not all(names)
                or len({name.group(1) for name in names}) != 1
                or {name.group(2) for name in names} != {'0', '1', '2', '3'}
                or len({os.major(state.st_rdev) for state in states}) != 1
                or any(os.minor(state.st_rdev) != int(name.group(2)) for name, state in zip(names, states))):
            raise ValidationError('SDK nodes must belong to one complete Sansec physical-function group')
        with open(os.path.join(SYSFS_DEVICES, primary, 'sriov_numvfs')) as count:
            if sansec_utils.parse_int(count.read()) != 0:
                raise ValidationError('Four SDK nodes are only supported on an unsplit Sansec card')

    def probe(self, config):
        if self.pending:
            process, output = self.pending
            if process.poll() is None:
                return dict(status=SdkStatus.UNKNOWN, reason='Previous SDK worker has not exited')
            process.communicate()
            shutil.rmtree(os.path.dirname(output))
            self.pending = None
        directory = tempfile.mkdtemp(prefix='sansec-health-')
        output = os.path.join(directory, 'result')
        with open(output, 'w'):
            pass
        try:
            process = shell.get_process([sys.executable, sansec_sdk.__file__, output], shell=False, pipe=True,
                                        workdir='/')
            try:
                process.communicate(json.dumps(config).encode('utf-8'), timeout=config['timeout'])
            except subprocess.TimeoutExpired:
                if not sansec_utils.terminate_process(process):
                    self.pending = (process, output)
                with open(output) as source:
                    result = json.load(source)
                if result.get('phase') == SdkPhase.PROBING:
                    result.update(status=SdkStatus.COMMFAIL, reason='SDK timed out at %s' % result['reason'])
                    return result
                return dict(status=SdkStatus.UNKNOWN,
                            reason='SDK timed out before identity verification or during cleanup')
            if process.returncode != 0:
                return dict(status=SdkStatus.UNKNOWN, reason='SDK worker exited with code %s' % process.returncode)
            with open(output) as source:
                return json.load(source)
        finally:
            if self.pending is None:
                shutil.rmtree(directory)

    def classify(self, address, profile, result):
        status, reason = HealthStatus.UNKNOWN, result['reason']
        if result.get('phase') == SdkPhase.PROBING:
            if result['status'] == SdkStatus.OK:
                status = HealthStatus.NORMAL
            elif result['status'] in (SdkStatus.HARDFAIL, SdkStatus.SELFTEST_FAILED):
                status = HealthStatus.FAULT
            elif result['status'] == SdkStatus.COMMFAIL:
                now = time.monotonic()
                count, last = self.failures.get(address, (0, now))
                if now - last >= profile['validityPeriod']:
                    count = 0
                if address not in self.failures or now - last >= profile['pollInterval']:
                    count, last = min(count + 1, sansec_utils.COMMUNICATION_FAILURE_THRESHOLD), now
                self.failures[address] = count, last
                status = (HealthStatus.FAULT if count >= sansec_utils.COMMUNICATION_FAILURE_THRESHOLD
                          else HealthStatus.UNKNOWN)
                return status, '%s; consecutive communication failures: %s/%s' % (
                    reason, count, sansec_utils.COMMUNICATION_FAILURE_THRESHOLD)
        return status, reason

    def health(self, addresses):
        reports = {a: dict(pciDeviceAddress=a, healthStatus=HealthStatus.UNKNOWN,
                           qualification=Qualification.UNVERIFIED) for a in addresses}
        eligible = []
        counted = set()
        try:
            present = os.listdir(SYSFS_DEVICES)
            if not present:
                raise ValidationError('PCI sysfs inventory is empty')
            for address, report in reports.items():
                try:
                    status, reason = self.system_check(address, present)
                    if status:
                        report.update(healthStatus=status, reason=reason)
                    else:
                        eligible.append(address)
                except OSError as error:
                    report['reason'] = 'Cannot inspect PCI device: %s' % error
            if not eligible:
                return [reports[a] for a in addresses]
            config = sansec_config.read_config(CONFIG_PATH)
            if config != self.config:
                self.failures.clear()
                self.config = config
            selected = {}
            for address in eligible:
                report = reports[address]
                profile = config['devices'].get(address.lower())
                if profile is None:
                    report['reason'] = 'No Sansec serial/version/capability profile for this PF'
                    continue
                try:
                    version = sansec_utils.driver_version(os.path.join(SYSFS_DEVICES, address.lower()),
                                                          profile.get('driverVersionSource', 'version'))
                except OSError as error:
                    report['reason'] = 'Cannot read Sansec driver version: %s' % error
                    continue
                if version != profile['driverVersion']:
                    report['reason'] = 'Sansec driver version differs from the configured profile'
                    continue
                with open(os.path.join(SYSFS_DEVICES, address.lower(), 'sriov_totalvfs')) as source:
                    capacity = sansec_utils.parse_int(source.read())
                if capacity <= 0:
                    raise ValidationError('Sansec primary function must provide SR-IOV')
                selected[address] = dict(profile, supportedVfCounts=list(range(1, capacity + 1)))
            if selected:
                self.check_sdk_endpoint(present, selected)
                result = self.probe(dict(config, devices=selected))
                for address, profile in selected.items():
                    report = reports[address]
                    if result.get('serialNumber') != profile['serialNumber']:
                        report['reason'] = 'SDK did not identify this PF: %s' % result['reason']
                        continue
                    status, reason = self.classify(address, profile, result)
                    if result.get('phase') == SdkPhase.PROBING and result['status'] == SdkStatus.COMMFAIL:
                        counted.add(address)
                    report.update(healthStatus=status, reason=reason)
                    if result.get('phase') == SdkPhase.PROBING:
                        for key in ('serialNumber', 'firmwareVersion', 'pollInterval', 'validityPeriod',
                                    'recoveryInterval', 'supportedVfCounts'):
                            report[key] = profile[key]
                        report['qualification'] = (Qualification.QUALIFIED if profile['compatible']
                                                   else Qualification.UNVERIFIED)
        except (OSError, ValidationError, json.JSONDecodeError) as error:
            for report in reports.values():
                if 'reason' not in report:
                    report['reason'] = 'Sansec health collection unavailable: %s' % error
        finally:
            self.failures = {address: failure for address, failure in self.failures.items() if address in counted}
        return [reports[a] for a in addresses]
