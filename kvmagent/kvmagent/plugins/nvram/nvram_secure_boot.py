import hashlib
import os
import os.path
import struct
import tempfile
import time
import uuid

from kvmagent.plugins.nvram import secure_boot_certs

from zstacklib.utils import log

logger = log.get_logger(__name__)

EFI_GLOBAL_VARIABLE_GUID = '8be4df61-93ca-11d2-aa0d-00e098032b8c'
EFI_IMAGE_SECURITY_DATABASE_GUID = 'd719b2cb-3d3a-4596-a3bc-dad00e67656f'
EFI_SECURE_BOOT_ENABLE_DISABLE_GUID = 'f0a30bc7-af08-4556-99c4-001009c93a44'
EFI_AUTHENTICATED_VARIABLE_GUID = 'aaf32c78-947b-439a-a180-2e144ec37792'
EFI_CERT_X509_GUID = 'a5c059a1-94e4-4aa7-87b5-ab155c2bf072'
EFI_CERT_SHA256_GUID = 'c1c41626-504c-4092-aca9-41f936934328'
MICROSOFT_SIGNATURE_OWNER_GUID = '77fa9abd-0359-4d32-bd60-28f4e78f784b'
ZSTACK_SIGNATURE_OWNER_GUID = 'c936afa6-f055-43ef-bd6e-73c3ae49fa94'

FV_SIGNATURE = b'_FVH'
FV_SIGNATURE_OFFSET = 40
FV_HEADER_LENGTH_OFFSET = 48
VARIABLE_STORE_HEADER_SIZE = 28
VARIABLE_HEADER = struct.Struct('<HBBIQ16sIII16s')
STORE_SIZE_OFFSET = 16
VARIABLE_START_ID = 0x55AA
VAR_ADDED = 0x3F
VAR_ADDED_IN_DELETED_TRANSITION = 0x3E
ERASED_UINT8 = 0xFF
ERASED_UINT32 = 0xFFFFFFFF

NV_BS = 0x03
NV_BS_RT_TIME_BASED_AUTH = 0x27
AUTHENTICATED_WRITE_ACCESS = 0x10
TIME_BASED_AUTHENTICATED_WRITE_ACCESS = 0x20
EMPTY_EFI_TIME = b'\0' * 16

SECURE_BOOT_ENABLE_NAME = 'SecureBootEnable'
SECURE_BOOT_ENABLE = 1
SECURE_BOOT_DISABLE = 0


class VariableStoreFullError(Exception):
    pass


def _align4(offset):
    return (offset + 3) & ~3


def _guid_bytes(guid):
    # type: (str) -> bytes
    return uuid.UUID(guid).bytes_le


def _guid_at(data, offset):
    # type: (bytearray, int) -> str
    return str(uuid.UUID(bytes_le=bytes(data[offset:offset + 16])))


def _efi_time_now():
    # type: () -> bytes
    t = time.gmtime()
    return struct.pack('<HBBBBBBIhBB', t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, 0, 0, 0, 0, 0)


def _signature_list(signature_type, owner, signature):
    # type: (str, str, bytes) -> bytes
    signature_size = 16 + len(signature)
    return struct.pack('<16sIII', _guid_bytes(signature_type), 28 + signature_size, 0, signature_size) \
        + _guid_bytes(owner) + signature


def _x509_signature_lists(owner, certs):
    # type: (str, list[bytes]) -> bytes
    return b''.join(_signature_list(EFI_CERT_X509_GUID, owner, cert) for cert in certs)


class OvmfVariableStore(object):
    def __init__(self, data):
        # type: (bytearray) -> None
        self.data = data
        self.variables = {}  # type: dict[tuple[str, str], tuple[int, int, int]]
        self.free_offset, self.end_offset = self._parse()

    @staticmethod
    def load(path):
        # type: (str) -> OvmfVariableStore
        with open(path, 'rb') as fd:
            return OvmfVariableStore(bytearray(fd.read()))

    def _parse(self):
        data = self.data
        if bytes(data[FV_SIGNATURE_OFFSET:FV_SIGNATURE_OFFSET + 4]) != FV_SIGNATURE:
            raise Exception('not an OVMF firmware volume')
        header_length = struct.unpack_from('<H', data, FV_HEADER_LENGTH_OFFSET)[0]
        if _guid_at(data, header_length) != EFI_AUTHENTICATED_VARIABLE_GUID:
            raise Exception('not an authenticated variable store')

        end_offset = header_length + struct.unpack_from('<I', data, header_length + STORE_SIZE_OFFSET)[0]
        offset = header_length + VARIABLE_STORE_HEADER_SIZE
        while offset + VARIABLE_HEADER.size <= end_offset:
            start_id, state, _, attributes, _, _, _, name_size, data_size, _ = \
                VARIABLE_HEADER.unpack_from(data, offset)
            if start_id != VARIABLE_START_ID:
                break

            # edk2 reads a header with any erased field as an interrupted write of zero size
            if state == ERASED_UINT8 or ERASED_UINT32 in (attributes, name_size, data_size):
                name_size = data_size = 0
            name_offset = offset + VARIABLE_HEADER.size
            data_offset = name_offset + name_size
            if data_offset + data_size > end_offset:
                raise Exception('corrupted variable at offset %d' % offset)

            if name_size and state in (VAR_ADDED, VAR_ADDED_IN_DELETED_TRANSITION):
                name = data[name_offset:data_offset].decode('utf-16-le', 'replace').rstrip(u'\0')
                key = (name, _guid_at(data, offset + 44))
                if state == VAR_ADDED or key not in self.variables:
                    self.variables[key] = (data_offset, data_size, attributes)
            offset = _align4(data_offset + data_size)
        return offset, end_offset

    def has(self, name, guid):
        # type: (str, str) -> bool
        return (name, guid) in self.variables

    def append_all(self, variables):
        # type: (list[tuple[str, str, int, bytes, bytes]]) -> None
        records = []
        for name, guid, attributes, payload, timestamp in variables:
            encoded_name = (name + u'\0').encode('utf-16-le')
            header = VARIABLE_HEADER.pack(VARIABLE_START_ID, VAR_ADDED, 0, attributes, 0, timestamp, 0,
                                          len(encoded_name), len(payload), _guid_bytes(guid))
            records.append((name, guid, attributes, header + encoded_name + payload, len(payload)))

        required = sum(_align4(len(record)) for _, _, _, record, _ in records)
        available = self.end_offset - self.free_offset
        if required > available:
            raise VariableStoreFullError('%d bytes required, %d bytes available' % (required, available))
        if self.data[self.free_offset:self.free_offset + required].count(ERASED_UINT8) != required:
            raise VariableStoreFullError('free space is not erased')

        for name, guid, attributes, record, payload_size in records:
            record_end = self.free_offset + len(record)
            self.data[self.free_offset:record_end] = record
            self.variables[(name, guid)] = (record_end - payload_size, payload_size, attributes)
            self.free_offset = _align4(record_end)

    def _write_uint8_in_place(self, name, variable, value):
        # type: (str, tuple[int, int, int], int) -> bool
        data_offset, data_size, attributes = variable
        if data_size != 1 or attributes & (AUTHENTICATED_WRITE_ACCESS | TIME_BASED_AUTHENTICATED_WRITE_ACCESS):
            logger.warn('cannot set %s of nvram: unexpected record[size=%d, attributes=0x%x]'
                        % (name, data_size, attributes))
            return False
        if self.data[data_offset] == value:
            return False
        self.data[data_offset] = value
        return True

    def _default_key_variables(self):
        # type: () -> list[tuple[str, str, int, bytes, bytes]]
        timestamp = _efi_time_now()
        defaults = [
            ('dbx', EFI_IMAGE_SECURITY_DATABASE_GUID,
             _signature_list(EFI_CERT_SHA256_GUID, ZSTACK_SIGNATURE_OWNER_GUID, hashlib.sha256(b'').digest())),
            ('db', EFI_IMAGE_SECURITY_DATABASE_GUID,
             _x509_signature_lists(MICROSOFT_SIGNATURE_OWNER_GUID, secure_boot_certs.DB_CERTS)),
            ('KEK', EFI_GLOBAL_VARIABLE_GUID,
             _x509_signature_lists(MICROSOFT_SIGNATURE_OWNER_GUID, secure_boot_certs.KEK_CERTS)),
        ]
        variables = [(name, guid, NV_BS_RT_TIME_BASED_AUTH, payload, timestamp)
                     for name, guid, payload in defaults if not self.has(name, guid)]
        variables.append(('PK', EFI_GLOBAL_VARIABLE_GUID, NV_BS_RT_TIME_BASED_AUTH,
                          _signature_list(EFI_CERT_X509_GUID, ZSTACK_SIGNATURE_OWNER_GUID, secure_boot_certs.PK_CERT),
                          timestamp))
        return variables

    def apply_secure_boot(self, enable):
        # type: (bool) -> bool
        enrolled = self.has('PK', EFI_GLOBAL_VARIABLE_GUID)
        toggle = self.variables.get((SECURE_BOOT_ENABLE_NAME, EFI_SECURE_BOOT_ENABLE_DISABLE_GUID))
        if not enable and not enrolled:
            return False
        # edk2 creates SecureBootEnable=1 by itself when PK exists and the variable is absent
        if enable and enrolled and toggle is None:
            return False

        state = SECURE_BOOT_ENABLE if enable else SECURE_BOOT_DISABLE
        variables = [] if enrolled else self._default_key_variables()
        if toggle is None:
            variables.append((SECURE_BOOT_ENABLE_NAME, EFI_SECURE_BOOT_ENABLE_DISABLE_GUID, NV_BS,
                              struct.pack('<B', state), EMPTY_EFI_TIME))
        self.append_all(variables)

        if toggle is None:
            return True
        return self._write_uint8_in_place(SECURE_BOOT_ENABLE_NAME, toggle, state) or bool(variables)

    def save(self, path):
        # type: (str) -> None
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.%s.' % os.path.basename(path))
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(self.data)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(path):
                st = os.stat(path)
                os.chmod(tmp_path, st.st_mode & 0o7777)
                os.chown(tmp_path, st.st_uid, st.st_gid)
            os.rename(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise


def prepare_secure_boot_nvram(nvram_path, template_path, secure_boot):
    # type: (str, str, bool) -> None
    source_path = nvram_path if os.path.exists(nvram_path) else template_path
    try:
        store = OvmfVariableStore.load(source_path)
    except Exception as e:
        if secure_boot:
            raise Exception('cannot enable UEFI secure boot, invalid OVMF variable store %s: %s' % (source_path, e))
        logger.warn('skip preparing secure boot state of nvram %s: %s' % (source_path, e))
        return

    try:
        changed = store.apply_secure_boot(secure_boot)
    except VariableStoreFullError as e:
        logger.warn('cannot update secure boot state of nvram %s: %s' % (nvram_path, e))
        if secure_boot:
            raise Exception('variable store of nvram %s has not enough space to enroll secure boot keys, '
                            'disable secure boot for the vm and restart' % nvram_path)
        return

    if not changed:
        return

    store.save(nvram_path)
    logger.debug('%s UEFI secure boot in nvram %s (from %s)'
                 % ('enabled' if secure_boot else 'disabled', nvram_path, source_path))
