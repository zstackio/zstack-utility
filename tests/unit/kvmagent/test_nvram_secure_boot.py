# -*- coding: utf-8 -*-

import hashlib
import os
import shutil
import struct
import uuid

import pytest

from kvmagent.plugins.nvram import nvram_secure_boot as sb
from kvmagent.plugins.nvram import secure_boot_certs

GLOBAL = sb.EFI_GLOBAL_VARIABLE_GUID
IMAGE_DB = sb.EFI_IMAGE_SECURITY_DATABASE_GUID
SB_ENABLE = sb.EFI_SECURE_BOOT_ENABLE_DISABLE_GUID
VAR_DELETED = 0x3C
HOST_SECBOOT_VARS_TEMPLATE = '/usr/share/edk2/ovmf/OVMF_VARS.secboot.fd'
NOT_ENOUGH_SPACE = 'has not enough space to enroll secure boot keys, disable secure boot for the vm and restart'


def build_blank_var_store(store_size=0x3E000, total_size=0x84000):
    fv_header = b'\0' * 16 + b'\0' * 16 + struct.pack('<Q', total_size) + b'_FVH' \
        + struct.pack('<IHHHBB', 0x4feff, 72, 0, 0, 0, 2) + struct.pack('<IIII', 132, 0x1000, 0, 0)
    store_header = uuid.UUID(sb.EFI_AUTHENTICATED_VARIABLE_GUID).bytes_le \
        + struct.pack('<IBBHI', store_size, 0x5A, 0xFE, 0, 0)
    data = fv_header + store_header
    return bytearray(data + b'\xff' * (total_size - len(data)))


def append(store, name, guid, attributes, payload):
    store.append_all([(name, guid, attributes, payload, sb.EMPTY_EFI_TIME)])


def fill_var_store(store):
    # leave less room than the smallest variable record (60-byte header) needs
    overhead = sb.VARIABLE_HEADER.size + len(u'Filler\0'.encode('utf-16-le'))
    append(store, 'Filler', GLOBAL, sb.NV_BS, b'\0' * (store.end_offset - store.free_offset - overhead - 32))
    assert store.end_offset - store.free_offset < sb.VARIABLE_HEADER.size


def read_variables(path):
    store = sb.OvmfVariableStore.load(path)
    return dict((key, variable_data(store, *key)) for key in store.variables)


def variable_data(store, name, guid):
    offset, size, _ = store.variables[(name, guid)]
    return bytes(store.data[offset:offset + size])


def x509_entries(signature_lists):
    entries, offset = [], 0
    while offset < len(signature_lists):
        signature_type = str(uuid.UUID(bytes_le=signature_lists[offset:offset + 16]))
        list_size, header_size, signature_size = struct.unpack_from('<III', signature_lists, offset + 16)
        cursor = offset + 28 + header_size
        while cursor < offset + list_size:
            owner = str(uuid.UUID(bytes_le=signature_lists[cursor:cursor + 16]))
            entries.append((signature_type, owner, signature_lists[cursor + 16:cursor + signature_size]))
            cursor += signature_size
        offset += list_size
    return entries


def read_file(path):
    with open(path, 'rb') as fd:
        return fd.read()


def assert_secure_boot_keys_enrolled(variables, secure_boot_enable=1):
    assert variables[('SecureBootEnable', SB_ENABLE)] == struct.pack('<B', secure_boot_enable)
    assert x509_entries(variables[('PK', GLOBAL)]) == \
        [(sb.EFI_CERT_X509_GUID, sb.ZSTACK_SIGNATURE_OWNER_GUID, secure_boot_certs.PK_CERT)]
    assert x509_entries(variables[('KEK', GLOBAL)]) == \
        [(sb.EFI_CERT_X509_GUID, sb.MICROSOFT_SIGNATURE_OWNER_GUID, c) for c in secure_boot_certs.KEK_CERTS]
    assert x509_entries(variables[('db', IMAGE_DB)]) == \
        [(sb.EFI_CERT_X509_GUID, sb.MICROSOFT_SIGNATURE_OWNER_GUID, c) for c in secure_boot_certs.DB_CERTS]
    assert x509_entries(variables[('dbx', IMAGE_DB)]) == \
        [(sb.EFI_CERT_SHA256_GUID, sb.ZSTACK_SIGNATURE_OWNER_GUID, hashlib.sha256(b'').digest())]


@pytest.fixture
def paths(tmp_path):
    template = str(tmp_path / 'OVMF_VARS.secboot.fd')
    with open(template, 'wb') as fd:
        fd.write(build_blank_var_store())
    return template, str(tmp_path / 'vm.fd')


@pytest.fixture
def full_enrolled_nvram(paths):
    template, nvram = paths
    sb.prepare_secure_boot_nvram(nvram, template, True)
    store = sb.OvmfVariableStore.load(nvram)
    fill_var_store(store)
    store.save(nvram)
    return template, nvram, store.free_offset


def test_first_boot_with_secure_boot_enrolls_keys_from_blank_template(paths):
    template, nvram = paths
    template_before = read_file(template)

    sb.prepare_secure_boot_nvram(nvram, template, True)

    assert_secure_boot_keys_enrolled(read_variables(nvram))
    assert read_file(template) == template_before


def test_existing_nvram_in_setup_mode_is_enrolled_and_keeps_boot_variables(paths):
    template, nvram = paths
    store = sb.OvmfVariableStore(build_blank_var_store())
    append(store, 'BootOrder', GLOBAL, 0x7, b'\x01\x00')
    store.save(nvram)

    sb.prepare_secure_boot_nvram(nvram, template, True)

    variables = read_variables(nvram)
    assert_secure_boot_keys_enrolled(variables)
    assert variables[('BootOrder', GLOBAL)] == b'\x01\x00'


def test_enrolled_nvram_is_not_rewritten(paths):
    template, nvram = paths
    sb.prepare_secure_boot_nvram(nvram, template, True)
    enrolled = read_file(nvram)
    os.utime(nvram, (0, 0))

    sb.prepare_secure_boot_nvram(nvram, template, True)

    assert read_file(nvram) == enrolled
    assert os.stat(nvram).st_mtime == 0


def test_toggle_secure_boot_rewrites_state_in_place_and_keeps_keys(paths):
    template, nvram = paths
    sb.prepare_secure_boot_nvram(nvram, template, True)
    used = sb.OvmfVariableStore.load(nvram).free_offset

    sb.prepare_secure_boot_nvram(nvram, template, False)
    assert_secure_boot_keys_enrolled(read_variables(nvram), secure_boot_enable=0)
    assert sb.OvmfVariableStore.load(nvram).free_offset == used

    sb.prepare_secure_boot_nvram(nvram, template, True)
    assert_secure_boot_keys_enrolled(read_variables(nvram), secure_boot_enable=1)
    assert sb.OvmfVariableStore.load(nvram).free_offset == used


def test_disable_again_on_disabled_nvram_does_not_write(paths):
    template, nvram = paths
    sb.prepare_secure_boot_nvram(nvram, template, True)
    sb.prepare_secure_boot_nvram(nvram, template, False)
    disabled = read_file(nvram)
    os.utime(nvram, (0, 0))

    sb.prepare_secure_boot_nvram(nvram, template, False)

    assert read_file(nvram) == disabled
    assert os.stat(nvram).st_mtime == 0


def test_secure_boot_off_does_not_touch_nvram_without_keys(paths):
    template, nvram = paths
    sb.prepare_secure_boot_nvram(nvram, template, False)
    assert not os.path.exists(nvram)


def test_deleted_platform_key_is_treated_as_absent(paths):
    template, nvram = paths
    store = sb.OvmfVariableStore(build_blank_var_store())
    pk_header = store.free_offset
    append(store, 'PK', GLOBAL, sb.NV_BS_RT_TIME_BASED_AUTH, b'stale')
    store.data[pk_header + 2] = VAR_DELETED
    store.save(nvram)

    sb.prepare_secure_boot_nvram(nvram, template, True)

    assert_secure_boot_keys_enrolled(read_variables(nvram))


def test_half_written_trailing_header_is_treated_as_end_of_store(paths):
    template, nvram = paths
    store = sb.OvmfVariableStore(build_blank_var_store())
    append(store, 'BootOrder', GLOBAL, 0x7, b'\x01\x00')
    half_written = store.free_offset
    store.data[half_written:half_written + 2] = struct.pack('<H', sb.VARIABLE_START_ID)
    store.save(nvram)

    reloaded = sb.OvmfVariableStore.load(nvram)
    assert reloaded.free_offset == half_written + sb.VARIABLE_HEADER.size
    assert set(reloaded.variables) == {('BootOrder', GLOBAL)}

    sb.prepare_secure_boot_nvram(nvram, template, True)

    variables = read_variables(nvram)
    assert_secure_boot_keys_enrolled(variables)
    assert variables[('BootOrder', GLOBAL)] == b'\x01\x00'


def test_invalid_var_store_fails_only_when_secure_boot_is_requested(paths):
    template, nvram = paths
    with open(template, 'wb') as fd:
        fd.write(b'\0' * 4096)

    with pytest.raises(Exception, match='invalid OVMF variable store'):
        sb.prepare_secure_boot_nvram(nvram, template, True)
    sb.prepare_secure_boot_nvram(nvram, template, False)
    assert not os.path.exists(nvram)


def test_full_nvram_without_keys_refuses_secure_boot_and_keeps_file(paths):
    template, nvram = paths
    store = sb.OvmfVariableStore(build_blank_var_store())
    append(store, 'BootOrder', GLOBAL, 0x7, b'\x01\x00')
    fill_var_store(store)
    store.save(nvram)
    before = read_file(nvram)

    with pytest.raises(Exception, match=NOT_ENOUGH_SPACE):
        sb.prepare_secure_boot_nvram(nvram, template, True)

    assert read_file(nvram) == before


def test_malformed_toggle_record_never_fails_the_start(paths):
    template, nvram = paths
    for secure_boot in (True, False):
        store = sb.OvmfVariableStore(build_blank_var_store())
        append(store, 'PK', GLOBAL, sb.NV_BS_RT_TIME_BASED_AUTH, b'foreign platform key')
        append(store, sb.SECURE_BOOT_ENABLE_NAME, SB_ENABLE, sb.NV_BS, b'\x01\x00')
        store.save(nvram)
        before = read_file(nvram)

        sb.prepare_secure_boot_nvram(nvram, template, secure_boot)

        assert read_file(nvram) == before


def test_existing_db_and_kek_are_kept_when_pk_is_enrolled(paths):
    template, nvram = paths
    store = sb.OvmfVariableStore(build_blank_var_store())
    append(store, 'db', IMAGE_DB, sb.NV_BS_RT_TIME_BASED_AUTH, b'custom db')
    append(store, 'KEK', GLOBAL, sb.NV_BS_RT_TIME_BASED_AUTH, b'custom kek')
    store.save(nvram)

    sb.prepare_secure_boot_nvram(nvram, template, True)

    store = sb.OvmfVariableStore.load(nvram)
    assert variable_data(store, 'db', IMAGE_DB) == b'custom db'
    assert variable_data(store, 'KEK', GLOBAL) == b'custom kek'
    assert [key for key in store.variables if key[0] == 'db'] == [('db', IMAGE_DB)]
    assert [key for key in store.variables if key[0] == 'KEK'] == [('KEK', GLOBAL)]
    assert store.has('PK', GLOBAL)
    assert store.has('dbx', IMAGE_DB)
    assert store.has(sb.SECURE_BOOT_ENABLE_NAME, SB_ENABLE)


def test_disable_with_foreign_pk_and_no_toggle_appends_disabled_state(paths):
    template, nvram = paths
    store = sb.OvmfVariableStore(build_blank_var_store())
    append(store, 'PK', GLOBAL, sb.NV_BS_RT_TIME_BASED_AUTH, b'foreign platform key')
    store.save(nvram)

    sb.prepare_secure_boot_nvram(nvram, template, False)

    variables = read_variables(nvram)
    assert variables[(sb.SECURE_BOOT_ENABLE_NAME, SB_ENABLE)] == b'\x00'
    assert variables[('PK', GLOBAL)] == b'foreign platform key'
    saved = read_file(nvram)
    os.utime(nvram, (0, 0))

    sb.prepare_secure_boot_nvram(nvram, template, False)

    assert read_file(nvram) == saved
    assert os.stat(nvram).st_mtime == 0


def test_save_failure_keeps_nvram_and_leaves_no_temp_file(paths, monkeypatch):
    template, nvram = paths
    store = sb.OvmfVariableStore(build_blank_var_store())
    append(store, 'BootOrder', GLOBAL, 0x7, b'\x01\x00')
    store.save(nvram)
    before = read_file(nvram)
    store = sb.OvmfVariableStore.load(nvram)

    def _fail(src, dst):
        raise OSError('rename failed')

    monkeypatch.setattr(sb.os, 'rename', _fail)
    with pytest.raises(OSError, match='rename failed'):
        store.save(nvram)

    assert read_file(nvram) == before
    assert sorted(os.listdir(os.path.dirname(nvram))) == ['OVMF_VARS.secboot.fd', 'vm.fd']


def test_full_enrolled_nvram_toggles_secure_boot_in_place(full_enrolled_nvram):
    template, nvram, used = full_enrolled_nvram
    enabled = read_file(nvram)

    sb.prepare_secure_boot_nvram(nvram, template, False)
    disabled = read_file(nvram)
    assert_secure_boot_keys_enrolled(read_variables(nvram), secure_boot_enable=0)
    assert sb.OvmfVariableStore.load(nvram).free_offset == used
    assert sum(a != b for a, b in zip(enabled, disabled)) == 1

    sb.prepare_secure_boot_nvram(nvram, template, True)
    assert read_file(nvram) == enabled


@pytest.mark.parametrize('secure_boot', [True, False])
def test_full_nvram_with_foreign_pk_and_no_toggle_is_left_untouched(paths, secure_boot):
    template, nvram = paths
    store = sb.OvmfVariableStore(build_blank_var_store())
    append(store, 'PK', GLOBAL, sb.NV_BS_RT_TIME_BASED_AUTH, b'foreign platform key')
    fill_var_store(store)
    store.save(nvram)
    before = read_file(nvram)

    sb.prepare_secure_boot_nvram(nvram, template, secure_boot)

    assert read_file(nvram) == before
    assert ('SecureBootEnable', SB_ENABLE) not in read_variables(nvram)


def test_enable_with_foreign_pk_and_no_toggle_keeps_firmware_default(paths):
    template, nvram = paths
    store = sb.OvmfVariableStore(build_blank_var_store())
    append(store, 'PK', GLOBAL, sb.NV_BS_RT_TIME_BASED_AUTH, b'foreign platform key')
    store.save(nvram)
    before = read_file(nvram)

    sb.prepare_secure_boot_nvram(nvram, template, True)

    assert read_file(nvram) == before


@pytest.mark.skipif(not os.path.isfile(HOST_SECBOOT_VARS_TEMPLATE), reason='host edk2-ovmf secboot vars template not installed')
def test_host_secboot_vars_template(paths):
    template, nvram = paths
    shutil.copy(HOST_SECBOOT_VARS_TEMPLATE, template)

    sb.prepare_secure_boot_nvram(nvram, template, True)

    assert_secure_boot_keys_enrolled(read_variables(nvram))
