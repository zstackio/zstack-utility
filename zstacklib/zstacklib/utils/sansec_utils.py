import os
import subprocess

SYSFS_DEVICES = '/sys/bus/pci/devices'
MODULE_CONFIG = '/etc/modprobe.d/zstack-sansec.conf'
VENDOR_ID = '1ed4'
PF_DEVICE_ID = '7011'
VF_DEVICE_ID = '1001'
DEVICE_IDS = (PF_DEVICE_ID, VF_DEVICE_ID)
COMMUNICATION_FAILURE_THRESHOLD = 3


class ValidationError(ValueError):
    pass


class CommandError(RuntimeError):
    pass


class HealthStatus:
    NORMAL = 'Normal'
    FAULT = 'Fault'
    UNKNOWN = 'Unknown'


class Qualification:
    DRIVER_UNAVAILABLE = 'DriverUnavailable'
    UNVERIFIED = 'Unverified'
    QUALIFIED = 'Qualified'


class OperationStatus:
    SUCCEEDED = 'Succeeded'
    FAILED = 'Failed'
    UNKNOWN = 'Unknown'


class SdkStatus:
    UNKNOWN = 'unknown'
    COMMFAIL = 'commfail'
    HARDFAIL = 'hardfail'
    SELFTEST_FAILED = 'selftest_failed'
    OK = 'ok'


class SdkPhase:
    IDENTIFYING = 'Identifying'
    PROBING = 'Probing'
    CLOSING = 'Closing'


def supported_device(vendor, device):
    return vendor.lower().removeprefix('0x') == VENDOR_ID and device.lower().removeprefix('0x') in DEVICE_IDS


def parse_int(value, base=10):
    try:
        return int(value, base)
    except ValueError as error:
        raise ValidationError('Invalid integer from device state: %s' % value) from error


def driver_loaded(path):
    driver = os.path.join(path, 'driver')
    return os.path.exists(driver) and os.path.basename(os.path.realpath(driver)) == 'swcsm'


def driver_version(path, source=None):
    if source is not None:
        with open(os.path.join(path, 'driver/module', source)) as driver:
            return driver.read().strip()
    for name in ('version', 'srcversion'):
        try:
            return driver_version(path, name)
        except FileNotFoundError:
            continue
    return None


def terminate_process(process):
    process.kill()
    try:
        process.communicate(timeout=1)
        return True
    except subprocess.TimeoutExpired:
        return False
