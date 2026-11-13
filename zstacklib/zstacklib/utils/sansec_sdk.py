import binascii
import ctypes as c
import json
import os
import sys

from zstacklib.utils.sansec_utils import SdkPhase, SdkStatus

SGD_SM3 = 0x00000001
SDR_COMMFAIL = 0x01000003
SDR_HARDFAIL = 0x01000004


class DeviceInfo(c.Structure):
    _fields_ = [('IssuerName', c.c_char * 40), ('DeviceName', c.c_char * 16), ('DeviceSerial', c.c_char * 16),
                ('DeviceVersion', c.c_uint), ('StandardVersion', c.c_uint), ('AsymAlgAbility', c.c_uint * 2),
                ('SymAlgAbility', c.c_uint), ('HashAlgAbility', c.c_uint), ('BufferSize', c.c_uint)]


class SdfError(Exception):
    def __init__(self, function, code):
        self.code = code
        super(SdfError, self).__init__('%s returned 0x%08x' % (function, code))


def load_library(path):
    lib = c.CDLL(path)
    signatures = {
        'SDF_OpenDevice': [c.POINTER(c.c_void_p)],
        'SDF_CloseDevice': [c.c_void_p],
        'SDF_OpenSession': [c.c_void_p, c.POINTER(c.c_void_p)],
        'SDF_CloseSession': [c.c_void_p],
        'SDF_GetDeviceInfo': [c.c_void_p, c.POINTER(DeviceInfo)],
        'SDF_GetFirmwareVersion': [c.c_void_p, c.c_void_p, c.POINTER(c.c_uint)],
        'SDF_GetLibraryVersion': [c.c_void_p, c.c_void_p, c.POINTER(c.c_uint)],
        'SDF_HashInit': [c.c_void_p, c.c_uint, c.c_void_p, c.c_void_p, c.c_uint],
        'SDF_HashUpdate': [c.c_void_p, c.c_void_p, c.c_uint],
        'SDF_HashFinal': [c.c_void_p, c.c_void_p, c.POINTER(c.c_uint)],
    }
    for name, args in signatures.items():
        function = getattr(lib, name)
        function.argtypes, function.restype = args, c.c_uint
    return lib


def check(lib, name, *args):
    code = getattr(lib, name)(*args)
    if code:
        raise SdfError(name, code)


def version(lib, name, session):
    buffer = c.create_string_buffer(128)
    length = c.c_uint(len(buffer) - 1)
    check(lib, name, session, buffer, c.byref(length))
    if length.value >= len(buffer):
        raise ValueError('%s returned invalid length' % name)
    return buffer.raw[:length.value].split(b'\0', 1)[0].decode('ascii').strip()


def probe(config, publish):
    result = dict(status=SdkStatus.UNKNOWN, phase=SdkPhase.IDENTIFYING, reason='SDK did not complete')
    device, session = c.c_void_p(), c.c_void_p()
    lib = None

    def call(name, *args):
        result.update(reason=name)
        publish(result)
        check(lib, name, *args)

    try:
        lib = load_library(config['libraryPath'])
        call('SDF_OpenDevice', c.byref(device))
        call('SDF_OpenSession', device, c.byref(session))
        info = DeviceInfo()
        call('SDF_GetDeviceInfo', session, c.byref(info))
        serial = info.DeviceSerial.decode('ascii').strip()
        profiles = [p for p in config['devices'].values() if p['serialNumber'] == serial]
        if len(profiles) != 1:
            raise ValueError('SDK device serial has no unique configured PCI mapping')
        result['serialNumber'] = serial
        result['firmwareVersion'] = version(lib, 'SDF_GetFirmwareVersion', session)
        result['libraryVersion'] = version(lib, 'SDF_GetLibraryVersion', session)
        profile = profiles[0]
        if any(result[key] != profile[key] for key in ('firmwareVersion', 'libraryVersion')):
            raise ValueError('SDK or firmware version differs from the configured profile')
        result['phase'] = SdkPhase.PROBING
        if not info.HashAlgAbility & SGD_SM3:
            raise ValueError('SDK device does not advertise SM3 support')
        call('SDF_HashInit', session, SGD_SM3, None, None, 0)
        call('SDF_HashUpdate', session, c.create_string_buffer(b'abc'), 3)
        digest, length = c.create_string_buffer(64), c.c_uint(64)
        call('SDF_HashFinal', session, digest, c.byref(length))
        expected = binascii.unhexlify('66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0')
        if length.value != len(expected) or digest.raw[:length.value] != expected:
            result.update(status=SdkStatus.SELFTEST_FAILED, reason='SM3 abc known-answer test failed')
        else:
            result.update(status=SdkStatus.OK, reason='SDK communication and SM3 abc known-answer test passed')
    except SdfError as error:
        status = {SDR_COMMFAIL: SdkStatus.COMMFAIL, SDR_HARDFAIL: SdkStatus.HARDFAIL}.get(error.code, SdkStatus.UNKNOWN)
        result.update(status=status, reason=str(error))
    except (OSError, AttributeError, ValueError) as error:
        result.update(status=SdkStatus.UNKNOWN, reason=str(error))
    finally:
        for handle, name in ((session, 'SDF_CloseSession'), (device, 'SDF_CloseDevice')):
            if not handle or lib is None:
                continue
            publish(dict(result, phase=SdkPhase.CLOSING, reason=name))
            try:
                check(lib, name, handle)
            except SdfError as error:
                if result['status'] == SdkStatus.OK:
                    result.update(status=SdkStatus.UNKNOWN, reason=str(error))
    publish(result)
    return result


def write_result(path, result):
    with open(path + '.tmp', 'w') as output:
        json.dump(result, output)
    os.replace(path + '.tmp', path)


if __name__ == '__main__':
    probe(json.load(sys.stdin), lambda result: write_result(sys.argv[1], result))
