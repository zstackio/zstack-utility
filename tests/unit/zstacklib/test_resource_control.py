import io
import os
from unittest.mock import Mock

import pytest

from zstacklib.utils import resource_control, resource_control_utils as resource_utils, systemd_resource_control_utils
from zstacklib.utils.cgroup_resource_control_backend import (
    CGROUP_VERSION_V1,
    CGROUP_VERSION_V2,
    CgroupResourceControlBackend,
    ResourceControlError,
)
from zstacklib.utils.cgroup_resource_control_backend_factory import CgroupResourceControlBackendFactory
from zstacklib.utils.cgroup_v1_resource_control_backend import CgroupV1ResourceControlBackend
from zstacklib.utils.cgroup_v2_resource_control_backend import CgroupV2ResourceControlBackend
from zstacklib.utils.resource_control import ResourceControlManager


def test_systemd_configuration_does_not_require_cgroup_backend(tmp_path):
    systemd = systemd_resource_control_utils.SystemdResourceControlUtils()
    systemd.SYSTEMD_UNIT_ROOT = str(tmp_path / "systemd")
    assert systemd.configure_slice("role.slice", "AllowedCPUs", "1-2", "MemoryMax", 1048576)
    assert systemd.configure_service("agent.service", "role.slice")
    assert systemd.configure_service("obsolete.service", "role.slice")
    assert systemd.prune_services("role.slice", ["agent.service"])
    assert systemd.configured_slice("agent.service") == "role.slice"
    assert systemd.configured_slice("obsolete.service") is None
    assert systemd.release_slice("role.slice")
    assert systemd.configured_slice("agent.service") == "role.slice", "Release must preserve service placement"


def test_backend_resolves_control_group_within_controller_root(tmp_path):
    backend = CgroupV2ResourceControlBackend(str(tmp_path))
    group = tmp_path / "role.slice"
    group.mkdir()
    assert backend.find_target("/role.slice/../role.slice") == str(group)
    with pytest.raises(ResourceControlError, match="outside root"):
        backend.find_target("/../outside")


@pytest.mark.parametrize('smt', ['present', 'missing', 'empty'])
def test_shared_cpu_topology_preserves_numa_online_cpus_and_smt(monkeypatch, smt):
    root = '/sys/devices/system'
    files = {
        root + '/cpu/online': '0-3,8-11,^11\n',
        root + '/node/node0/cpulist': '0-1,8-9\n',
        root + '/node/node2/cpulist': '2-3,10-11\n',
    }
    for cpu in [0, 1, 2, 3, 8, 9, 10]:
        files[root + '/cpu/cpu%s/topology/thread_siblings_list' % cpu] = '%s,%s\n' % (cpu % 8, cpu % 8 + 8)
    path = root + '/cpu/cpu2/topology/thread_siblings_list'
    if smt == 'missing':
        del files[path]
    elif smt == 'empty':
        files[path] = '\n'
    monkeypatch.setattr(resource_control, 'open', lambda path: io.StringIO(files[path]), raising=False)
    monkeypatch.setattr(resource_control.os.path, 'isfile', lambda path: path in files)
    monkeypatch.setattr(resource_control.glob, 'glob', lambda _: [root + '/node/node0', root + '/node/node2'])

    nodes = resource_control.get_cpu_topology()
    assert set(nodes) == {'0', '2'}, 'Sparse NUMA node IDs must not truncate enumeration'
    assert nodes['0']['coreGroups'] == [['0', '8'], ['1', '9']], 'Preserve CPU0 siblings for allocation'
    assert nodes['2']['cpus'] == ['2', '3', '10', '11'], 'KVM still needs the full node CPU list'
    assert nodes['2']['onlineCpus'] == ['2', '3', '10'], 'Offline CPUs must not be allocatable'
    assert nodes['2']['coreGroups'] == ([['2', '10'], ['3']] if smt == 'present' else []), \
        'Missing or empty SMT facts must not invent core groups'

    monkeypatch.setattr(resource_control.glob, 'glob', lambda _: [])
    nodes = resource_control.get_cpu_topology()
    assert set(nodes) == {'0'}, 'Non-NUMA Image Store servers still need a CPU planning domain'
    assert nodes['0']['onlineCpus'] == ['0', '1', '2', '3', '8', '9', '10']


def backend_for_version(version, root):
    if version == CGROUP_VERSION_V1:
        return CgroupV1ResourceControlBackend(root)
    return CgroupV2ResourceControlBackend(root)


def test_manager_delegates_to_factory_backends_without_version_fields(monkeypatch):
    cpu = Mock(spec=["root", "supports_exclusive_cpu_partition", "apply_cpu_set", "release_cpu_set"])
    cpu.root = "/cpuset"
    cpu.apply_cpu_set.return_value = "1-2"
    memory = Mock(spec=["root", "apply_memory", "target"])
    memory.root = "/memory"
    memory.target.side_effect = lambda relative: "/memory/" + relative
    memory.apply_memory.side_effect = [1048576, 0]
    factory = Mock(spec=CgroupResourceControlBackendFactory)
    factory.cpu.return_value = cpu
    factory.memory.return_value = memory
    factory.find_memory.return_value = memory
    manager = ResourceControlManager(factory)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)
    monkeypatch.setattr(manager, "_resolve", lambda *_args: "/cpuset/service")
    monkeypatch.setattr(manager, "_resolve_for_release", lambda *_args: "/cpuset/service")

    assert manager.apply("COMPUTE", "1-2", [handle("agent.service")], 1048576)["synced"], \
        "The manager must use the factory's execution contract without selecting a version itself"
    assert manager.release("COMPUTE", [handle("agent.service")])["synced"]
    cpu.apply_cpu_set.assert_called_once_with("/cpuset/service", "1-2")
    cpu.release_cpu_set.assert_called_once_with("/cpuset/service")
    assert [call.args for call in memory.apply_memory.call_args_list] == [
        ("/memory/service", 1048576, "/cpuset/service"), ("/memory/service", 0, "/cpuset/service")], \
        "CPU and memory must retain their independently selected controller roots"


def handle(value):
    return {
        "handleType": "SYSTEMD_UNIT",
        "value": value,
        "serviceName": value.rsplit(".service", 1)[0],
        "optional": False,
        "restartable": False,
    }


def optional_handle(value):
    item = handle(value)
    item["optional"] = True
    return item


@pytest.mark.parametrize("slice_name, handles", [
    ("../../attacker.slice", [handle("agent.service")]),
    ("zstack-compute.slice", [dict(handle("agent.service"), value="../../attacker.service")]),
    ("zstack-compute.slice", [handle("agent.service"), handle("agent.service")]),
    ("zstack-compute.slice", [dict(handle("agent.service"), optional=None)]),
    ("zstack-compute.slice", [dict(handle("agent.service"), serviceName=None)]),
    ("zstack-compute.slice", [dict(handle("agent.service"), restartable=None)]),
    ("zstack-compute.slice", []),
])
def test_service_command_rejects_unsafe_or_ambiguous_targets(slice_name, handles):
    with pytest.raises(ResourceControlError):
        ResourceControlManager.validate_service_command(slice_name, handles)


@pytest.mark.parametrize("count", [64, 65])
def test_service_command_preserves_handle_count_limit(count):
    handles = [handle("agent-%s.service" % index) for index in range(count)]
    if count == 64:
        ResourceControlManager.validate_service_command("role.slice", handles)
    else:
        with pytest.raises(ResourceControlError, match="between 1 and 64"):
            ResourceControlManager.validate_service_command("role.slice", handles)


@pytest.mark.parametrize("field,tail_limit", [("slice", 248), ("unit", 248), ("serviceName", 63)])
@pytest.mark.parametrize("extra", [0, 1])
def test_service_command_preserves_name_tail_limits(field, tail_limit, extra):
    name = "a" * (1 + tail_limit + extra)
    slice_name = name + ".slice" if field == "slice" else "role.slice"
    service = handle("agent.service")
    if field == "unit":
        service["value"] = name + ".service"
    elif field == "serviceName":
        service["serviceName"] = name
    if extra:
        with pytest.raises(ResourceControlError):
            ResourceControlManager.validate_service_command(slice_name, [service])
    else:
        ResourceControlManager.validate_service_command(slice_name, [service])


@pytest.mark.parametrize("cpu_set,valid", [
    ("9999999999", True), ("10000000000", False),
    ("0-9999999999", True), ("0-10000000000", False),
    ("9999999999-9999999999", True), ("10000000000-10000000000", False),
])
def test_cpu_normalization_preserves_token_digit_limit(cpu_set, valid):
    manager = ResourceControlManager()
    if valid:
        expected = "9999999999" if cpu_set == "9999999999-9999999999" else cpu_set
        assert resource_utils.normalize(cpu_set) == expected
    else:
        with pytest.raises(ResourceControlError):
            resource_utils.normalize(cpu_set)


def prepare_restart(manager, monkeypatch):
    in_target = Mock(return_value=True)
    monkeypatch.setattr(manager.systemd, "configured_slice", lambda _unit: "zstack-compute.slice")
    monkeypatch.setattr(
        manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-compute.slice")
    monkeypatch.setattr(manager.backend_factory.cpu(), "contains", in_target)
    return in_target


def test_release_with_only_optional_handles_is_an_idempotent_success(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(
        manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")),)
    monkeypatch.setattr(
        manager.backend_factory, "find_memory", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(manager, "_resolve_for_release", lambda *_args: None)

    result = manager.release("MANAGEMENT", [optional_handle("collectd.service")])

    assert result["synced"], "Releasing absent optional handles must remain idempotent"


@pytest.mark.parametrize("results,apply_synced,release_synced", [
    ([], False, True), ([None, None], False, True), ([None, True], True, True),
    ([False, True], False, False), ([True, None, False], False, False),
])
def test_apply_and_release_preserve_skipped_and_unsynced_results(results, apply_synced, release_synced):
    manager = ResourceControlManager()
    assert manager._summarize_apply(results) == {"synced": apply_synced}
    assert manager._summarize_release(results) == {"synced": release_synced}


@pytest.mark.parametrize("operation", ["apply", "release"])
def test_unsynced_first_handle_does_not_stop_later_resource_operations(monkeypatch, operation):
    manager = ResourceControlManager()
    services = [handle("first.service"), handle("second.service")]
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/cgroup")))
    monkeypatch.setattr(manager.backend_factory, "memory", Mock(return_value=CgroupV2ResourceControlBackend("/memory")))
    monkeypatch.setattr(
        manager.backend_factory, "find_memory", Mock(return_value=CgroupV2ResourceControlBackend("/memory")))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)
    resolve = lambda _backend, _role, service: "/cgroup/" + service["value"]
    monkeypatch.setattr(manager, "_resolve", resolve)
    monkeypatch.setattr(manager, "_resolve_for_release", resolve)
    cpu = Mock(side_effect=["0", "0-3"])
    memory = Mock(side_effect=[resource_utils.MEBIBYTE, resource_utils.MEBIBYTE]
                  if operation == "apply" else [resource_utils.MEBIBYTE, 0])
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", cpu)
    monkeypatch.setattr(manager.backend_factory.cpu(), "release_cpu_set", cpu)
    monkeypatch.setattr(manager, "_apply_memory_limit", memory)

    result = (manager.apply("COMPUTE", "0-3", services, resource_utils.MEBIBYTE) if operation == "apply"
              else manager.release("COMPUTE", services))

    assert not result["synced"], "An earlier mismatch must not be hidden by a later successful handle"
    assert [call.args[0] for call in cpu.call_args_list] == ["/cgroup/first.service", "/cgroup/second.service"]
    assert [call.args[1] for call in memory.call_args_list] == ["/cgroup/first.service", "/cgroup/second.service"]


@pytest.mark.parametrize("desired,actual,synced", [
    (None, 1048576, True), (0, None, True), (0, 0, True), (0, 1048576, False),
    (1048576, None, False), (1048576, 1048576, True), (1048576, 2097152, False),
])
def test_apply_preserves_unmanaged_unlimited_and_limited_memory(monkeypatch, desired, actual, synced):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/cgroup")))
    monkeypatch.setattr(manager.backend_factory, "memory", Mock(return_value=CgroupV2ResourceControlBackend("/memory")))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)
    monkeypatch.setattr(manager, "_resolve", lambda *_args: "/cgroup/agent.service")
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", lambda *_args: "0-3")
    apply_memory = Mock(return_value=actual)
    monkeypatch.setattr(manager, "_apply_memory_limit", apply_memory)

    assert manager.apply("COMPUTE", "0-3", [handle("agent.service")], desired) == {"synced": synced}
    assert apply_memory.call_count == (0 if desired is None else 1), "None must not release an existing memory limit"


def test_release_keeps_service_slice_membership(monkeypatch):
    manager = ResourceControlManager()
    remove_drop_in = Mock(return_value=True)
    release_cpu = Mock()
    release_memory = Mock(return_value=0)
    systemctl = Mock()
    calls = Mock()
    calls.attach_mock(release_cpu, "cpu")
    calls.attach_mock(remove_drop_in, "remove")
    calls.attach_mock(systemctl, "reload")
    monkeypatch.setattr(
        manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(
        manager.backend_factory, "find_memory", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(manager.systemd, "_remove_drop_in", remove_drop_in)
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-compute.slice")
    monkeypatch.setattr(manager.backend_factory.cpu(), "release_cpu_set", release_cpu)
    monkeypatch.setattr(manager.backend_factory.find_memory(), "apply_memory", release_memory)
    monkeypatch.setattr(manager.systemd, "_systemctl", systemctl)

    result = manager.release("COMPUTE", [handle("zstack-kvmagent.service")], "zstack-compute.slice")

    assert result["synced"]
    assert [call[0] for call in calls.mock_calls] == ["cpu", "remove", "reload"], \
        "Restore thread CPU affinity before systemd can disable the last cpuset controller"
    remove_drop_in.assert_called_once_with(manager.systemd._drop_in_path("zstack-compute.slice"))
    release_cpu.assert_called_once_with("/sys/fs/cgroup/zstack-compute.slice")
    release_memory.assert_called_once_with("/sys/fs/cgroup/zstack-compute.slice", 0)
    systemctl.assert_called_once_with(["daemon-reload"], 30)


def test_first_role_to_write_a_service_slice_keeps_ownership(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    manager.systemd.SYSTEMD_UNIT_ROOT = str(tmp_path)
    service = handle("node_exporter.service")

    assert manager.systemd.configure_service(service["value"], "zstack-management.slice")
    assert not manager.systemd.configure_service(service["value"], "zstack-compute.slice")

    with open(manager.systemd._drop_in_path("node_exporter.service")) as stream:
        assert stream.read() == "[Service]\nSlice=zstack-management.slice\n"


@pytest.mark.parametrize("slice_name", ["zstack-compute.slice", "role-custom.slice", "role:custom.slice"])
def test_configured_slice_round_trip_preserves_valid_names(tmp_path, slice_name):
    manager = ResourceControlManager()
    manager.systemd.SYSTEMD_UNIT_ROOT = str(tmp_path)
    service = handle("node_exporter.service")

    assert manager.systemd.configure_service(service["value"], slice_name)
    assert manager.systemd.configured_slice(service["value"]) == slice_name
    assert not manager.systemd.configure_service(service["value"], "another.slice")
    assert manager.systemd.configured_slice(service["value"]) == slice_name


@pytest.mark.parametrize("slice_name", ["../role.slice", "/role.slice", "role/name.slice", "-role.slice"])
def test_configured_slice_rejects_invalid_names(tmp_path, slice_name):
    manager = ResourceControlManager()
    manager.systemd.SYSTEMD_UNIT_ROOT = str(tmp_path)
    path = manager.systemd._drop_in_path("node_exporter.service")
    manager.systemd._write_drop_in(path, "[Service]\nSlice=%s\n" % slice_name)

    assert manager.systemd.configured_slice("node_exporter.service") is None


@pytest.mark.parametrize("cpu_version,memory_version", [
    (CGROUP_VERSION_V1, CGROUP_VERSION_V1),
    (CGROUP_VERSION_V1, CGROUP_VERSION_V2),
    (CGROUP_VERSION_V2, CGROUP_VERSION_V1),
])
@pytest.mark.parametrize("changed", [False, True])
@pytest.mark.parametrize("cpu_failure", [False, True])
def test_release_without_cpu_slice_clears_role_memory_and_reloads(
        tmp_path, monkeypatch, cpu_version, memory_version, changed, cpu_failure):
    manager = ResourceControlManager()
    manager.systemd.SYSTEMD_UNIT_ROOT = str(tmp_path / "systemd")
    service = handle("node_exporter.service")
    manager.systemd.configure_service(service["value"], "zstack-compute.slice")
    if changed:
        manager.systemd.configure_slice(
            "zstack-compute.slice", backend_for_version(cpu_version, "/cpuset").cpu_set_property, "2-3",
            backend_for_version(memory_version, "/memory").memory_limit_property, resource_utils.MEBIBYTE)
    memory_root = str(tmp_path / "memory")
    memory_target = os.path.join(memory_root, "zstack-compute.slice")
    os.makedirs(memory_target)
    limit_name = "memory.max" if memory_version == CGROUP_VERSION_V2 else "memory.limit_in_bytes"
    for path, value in [(os.path.join(memory_root, limit_name), "9223372036854771712"),
                        (os.path.join(memory_target, limit_name), str(resource_utils.MEBIBYTE))]:
        with open(path, "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=backend_for_version(cpu_version, "/cpuset")))
    memory_backend = backend_for_version(memory_version, memory_root)
    monkeypatch.setattr(manager.backend_factory, "find_memory", lambda: memory_backend)
    monkeypatch.setattr(manager, "_active_slice_target",
                        lambda backend, _slice: memory_target if backend.root == memory_root else None)
    systemctl = Mock()
    monkeypatch.setattr(manager.systemd, "_systemctl", systemctl)
    fallback = Mock(return_value=True)
    if cpu_failure:
        fallback.side_effect = ResourceControlError("CPU release failed")
    monkeypatch.setattr(manager, "_release_non_systemd_handle", fallback)

    if cpu_failure:
        with pytest.raises(ResourceControlError, match="CPU release failed"):
            manager.release("COMPUTE", [service], "zstack-compute.slice")
    else:
        assert manager.release("COMPUTE", [service], "zstack-compute.slice")["synced"]

    with open(os.path.join(memory_target, limit_name)) as stream:
        assert stream.read() == ("max" if memory_version == CGROUP_VERSION_V2 else "9223372036854771712")
    assert manager.systemd.configured_slice(service["value"]) == "zstack-compute.slice"
    assert not os.path.exists(manager.systemd._drop_in_path("zstack-compute.slice"))
    if changed:
        systemctl.assert_called_once_with(["daemon-reload"], 30)
    else:
        systemctl.assert_not_called()


@pytest.mark.parametrize("properties,message", [
    ({"LoadState": "not-found"}, "does not exist"),
    ({"LoadState": "loaded", "ActiveState": "inactive"}, None),
])
@pytest.mark.parametrize("optional", [False, True])
@pytest.mark.parametrize("cpu_version", [CGROUP_VERSION_V1, CGROUP_VERSION_V2])
@pytest.mark.parametrize("slice_name", [None, "zstack-compute.slice"])
@pytest.mark.parametrize("cpu_set,memory", [("2-3", None), (None, 1048576), ("2-3", 1048576)])
def test_apply_persists_inactive_rejects_required_missing(
        tmp_path, monkeypatch, properties, message, optional, cpu_version, slice_name, cpu_set, memory):
    manager = ResourceControlManager()
    manager.systemd.SYSTEMD_UNIT_ROOT = str(tmp_path / "units")
    service = optional_handle("node_exporter.service") if optional else handle("node_exporter.service")
    memory_version = CGROUP_VERSION_V1 if cpu_version == CGROUP_VERSION_V1 else CGROUP_VERSION_V2
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=backend_for_version(cpu_version, "/cpuset")))
    monkeypatch.setattr(
        manager.backend_factory, "memory", Mock(return_value=backend_for_version(memory_version, "/memory")))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)
    monkeypatch.setattr(manager, "_ensure_active_slice_target", lambda *_args: None)
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: None)
    apply_cpu, apply_memory, move_processes, systemctl = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", apply_cpu)
    monkeypatch.setattr(manager.backend_factory.memory(), "apply_memory", apply_memory)
    monkeypatch.setattr(manager.backend_factory.cpu(), "_move_processes", move_processes)
    monkeypatch.setattr(manager.systemd, "_systemctl", systemctl)
    monkeypatch.setattr(manager.systemd, "properties", lambda *_args: properties)

    if optional or message is None:
        results = [manager.apply("COMPUTE", cpu_set, [service], memory, slice_name) for _ in range(2)]
        if slice_name:
            assert resource_utils.read(manager.systemd._drop_in_path(service["value"])) == \
                "[Service]\nSlice=%s\n" % slice_name
            expected = "[Slice]\n"
            if cpu_set is not None and cpu_version == CGROUP_VERSION_V2:
                expected += "AllowedCPUs=%s\n" % cpu_set
            if memory is not None:
                setting = "MemoryLimit" if memory_version == CGROUP_VERSION_V1 else "MemoryMax"
                expected += "%s=%s\n" % (setting, memory)
            assert resource_utils.read(manager.systemd._drop_in_path(slice_name)) == expected
            assert [call.args for call in systemctl.call_args_list] == [
                (["daemon-reload"], 30)] * (1 if memory is None else 2), \
                "Only the initial apply reloads CPU/service settings and the independent memory setting"
        else:
            assert not os.path.exists(manager.systemd.SYSTEMD_UNIT_ROOT)
            systemctl.assert_not_called()
        synced = message is None and slice_name is not None and (cpu_set is None or cpu_version == CGROUP_VERSION_V2)
        assert results == [{"synced": synced}] * 2, "Initial and unchanged persisted assignments must agree"
    else:
        with pytest.raises(ResourceControlError) as error:
            manager.apply("COMPUTE", cpu_set, [service], memory, slice_name)
        assert str(error.value) == "Systemd unit[node_exporter.service] %s" % message
    apply_cpu.assert_not_called()
    apply_memory.assert_not_called()
    move_processes.assert_not_called()


@pytest.mark.parametrize("boundary", ["ownership", "slice-write", "service-write", "reload"])
def test_inactive_slice_apply_requires_owned_persisted_configuration(tmp_path, monkeypatch, boundary):
    manager = ResourceControlManager()
    manager.systemd.SYSTEMD_UNIT_ROOT = str(tmp_path / "units")
    service = handle("node_exporter.service")
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/cpuset")))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)
    monkeypatch.setattr(manager, "_ensure_active_slice_target", lambda *_args: None)
    monkeypatch.setattr(manager.systemd, "properties", lambda *_args: {
        "LoadState": "loaded", "ActiveState": "inactive"})
    systemctl = Mock()
    monkeypatch.setattr(manager.systemd, "_systemctl", systemctl)
    if boundary == "ownership":
        manager.systemd.configure_service(service["value"], "another.slice")
        assert not manager.apply("COMPUTE", "2-3", [service], None, "zstack-compute.slice")["synced"]
        assert resource_utils.read(manager.systemd._drop_in_path(service["value"])) == \
            "[Service]\nSlice=another.slice\n"
    else:
        if boundary == "reload":
            systemctl.side_effect = ResourceControlError("reload failed")
        else:
            method = "configure_slice" if boundary == "slice-write" else "configure_service"
            monkeypatch.setattr(manager.systemd, method, Mock(side_effect=OSError("write failed")))
        with pytest.raises((OSError, ResourceControlError), match="failed"):
            manager.apply("COMPUTE", "2-3", [service], None, "zstack-compute.slice")
    assert all(call.args == (["daemon-reload"], 30) for call in systemctl.call_args_list)


def test_release_reports_role_memory_failure_after_reloading_removed_configuration(monkeypatch):
    manager = ResourceControlManager()
    cpu_backend = CgroupV1ResourceControlBackend("/cpuset")
    monkeypatch.setattr(cpu_backend, "release_cpu_set", Mock())
    memory_backend = CgroupV1ResourceControlBackend("/memory")
    monkeypatch.setattr(manager.systemd, "_remove_drop_in", lambda *_args: True)
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: "/memory/zstack-compute.slice")
    monkeypatch.setattr(memory_backend, "apply_memory", Mock(side_effect=ResourceControlError("Memory release failed")))
    systemctl = Mock()
    monkeypatch.setattr(manager.systemd, "_systemctl", systemctl)

    with pytest.raises(ResourceControlError, match="Memory release failed"):
        manager._release_systemd_slice(
            cpu_backend, "COMPUTE", "zstack-compute.slice",
            [handle("node_exporter.service")], memory_backend)

    systemctl.assert_called_once_with(["daemon-reload"], 30)


def test_inspect_omits_a_service_owned_by_another_role(monkeypatch):
    manager = ResourceControlManager()
    inspect_systemd = Mock()
    monkeypatch.setattr(
        manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(manager.systemd, "configured_slice", lambda _unit: "zstack-management.slice")
    monkeypatch.setattr(manager.systemd, "properties", inspect_systemd)

    usages = manager.inspect("COMPUTE", [handle("node_exporter.service")], "zstack-compute.slice")

    assert usages == []
    inspect_systemd.assert_not_called()


def test_role_memory_limit_is_applied_once_at_slice_boundary(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(
        manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(
        manager.backend_factory, "memory", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(manager, "_prepare_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager.systemd, "prune_services", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "configure_slice", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "configure_service", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "configured_slice", lambda _unit: "zstack-management.slice")
    monkeypatch.setattr(manager, "_ensure_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-management.slice")
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-management.slice")
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", lambda *_args: "0-3")
    apply_memory = Mock(return_value=4 * 1024 * 1024 * 1024)
    monkeypatch.setattr(manager.backend_factory.memory(), "apply_memory", apply_memory)
    monkeypatch.setattr(manager.systemd, "properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/zstack-management.slice/%s" % unit,
    })
    monkeypatch.setattr(CgroupResourceControlBackend, "find_target", lambda self, group: self.root + group)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    result = manager.apply(
        "MANAGEMENT",
        "0-3",
        [handle("zstack.service"), handle("mariadb.service")],
        4 * 1024 * 1024 * 1024,
        "zstack-management.slice",
    )

    apply_memory.assert_called_once_with("/sys/fs/cgroup/zstack-management.slice", 4 * 1024 * 1024 * 1024)
    assert result["synced"], "Sync requires both role CPU and memory boundaries"


def test_v2_exclusive_boundary_changes_partition_without_moving_processes(tmp_path):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstack-compute.slice")
    os.makedirs(target)
    for path, value in (
            (os.path.join(root, "cpuset.mems.effective"), "0"),
            (os.path.join(target, "cpuset.cpus"), "0-7"),
            (os.path.join(target, "cpuset.mems"), "0"),
            (os.path.join(target, "cpuset.cpus.partition"), "member"),
            (os.path.join(target, "cpuset.cpus.exclusive"), "")):
        with open(path, "w") as stream:
            stream.write(value)

    actual = CgroupV2ResourceControlBackend(root).apply_exclusive_cpu_set(target, "4-7")

    assert actual == "4-7"
    with open(os.path.join(target, "cpuset.cpus.partition")) as stream:
        assert stream.read() == "root"
    with open(os.path.join(target, "cpuset.cpus.exclusive")) as stream:
        assert stream.read() == "4-7"

    actual = CgroupV2ResourceControlBackend(root).apply_cpu_set(target, "2-5")

    assert actual == "2-5"
    with open(os.path.join(target, "cpuset.cpus.partition")) as stream:
        assert stream.read() == "member"
    with open(os.path.join(target, "cpuset.cpus.exclusive")) as stream:
        assert stream.read() == "\n"


def test_v2_without_partition_interface_does_not_change_cpu_boundary(tmp_path):
    target = tmp_path / "role.slice"
    target.mkdir()
    cpus = target / "cpuset.cpus"
    cpus.write_text("0-7")
    manager = ResourceControlManager()

    with pytest.raises(ResourceControlError, match="CPU partition interface is unavailable"):
        CgroupV2ResourceControlBackend(str(tmp_path)).apply_exclusive_cpu_set(str(target), "2-3")

    assert cpus.read_text() == "0-7", "An unsupported partition must fail before changing the CPU mask"


def test_exclusive_partition_check_follows_controller_activation(tmp_path, monkeypatch):
    target = tmp_path / "role.slice"
    target.mkdir()
    (tmp_path / "cgroup.subtree_control").write_text("")
    manager = ResourceControlManager()
    write = resource_utils.write

    def activate_controller(path, value):
        write(path, value)
        if path == str(tmp_path / "cgroup.subtree_control") and value == "+cpuset":
            (target / "cpuset.cpus").write_text("0-7")
            (target / "cpuset.cpus.partition").write_text("member")

    monkeypatch.setattr(resource_utils, "write", (activate_controller))

    actual = CgroupV2ResourceControlBackend(str(tmp_path)).apply_exclusive_cpu_set(str(target), "2-3")

    assert actual == "2-3", "A not-yet-enabled controller must not be mistaken for an unsupported partition"
    assert (target / "cpuset.cpus.partition").read_text() == "root"


@pytest.mark.parametrize("hierarchy", [None, "0", "1"])
def test_v1_subtree_memory_capability_checks_hierarchical_accounting(tmp_path, monkeypatch, hierarchy):
    manager = ResourceControlManager()
    target = tmp_path / "role.slice"
    target.mkdir()
    (target / "memory.limit_in_bytes").write_text(str(4 * resource_utils.MEBIBYTE))
    (target / "memory.usage_in_bytes").write_text("0")
    if hierarchy is not None:
        (target / "memory.use_hierarchy").write_text(hierarchy)
    backend = CgroupV1ResourceControlBackend(str(tmp_path))
    assert backend.supports_subtree_memory_limit(str(target)) == (hierarchy == "1"), \
        "A per-cgroup memory limit must not be mistaken for a subtree limit"
    assert not backend.supports_exclusive_cpu_partition(), "v1 exclusivity is not the partition contract"
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "ActiveState": "active", "ControlGroup": "/role.slice",
    })
    if hierarchy == "1":
        manager._prepare_active_slice_memory("role.slice", 2 * resource_utils.MEBIBYTE, backend)
    else:
        with pytest.raises(ResourceControlError, match="Subtree memory limits are not supported"):
            manager._prepare_active_slice_memory("role.slice", 2 * resource_utils.MEBIBYTE, backend)


def test_v2_subtree_memory_capability_does_not_require_target_activation(tmp_path):
    backend = CgroupV2ResourceControlBackend(str(tmp_path))
    assert backend.supports_subtree_memory_limit(str(tmp_path / "inactive.slice")), \
        "The v2 subtree limit capability must not prevent controller activation during apply"


@pytest.mark.parametrize("usage", [1, 3])
def test_active_v2_slice_initializes_memory_controller_before_usage_validation(tmp_path, monkeypatch, usage):
    manager = ResourceControlManager()
    target = tmp_path / "role.slice"
    target.mkdir()
    (tmp_path / "cgroup.controllers").write_text("memory")
    control = tmp_path / "cgroup.subtree_control"
    control.write_text("")
    backend = CgroupV2ResourceControlBackend(str(tmp_path))
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "ActiveState": "active", "ControlGroup": "/role.slice",
    })
    write = resource_utils.write

    def activate_memory_controller(path, value):
        write(path, value)
        if path == str(control) and value == "+memory":
            (target / "memory.max").write_text("max")
            (target / "memory.current").write_text(str(usage * resource_utils.MEBIBYTE))

    monkeypatch.setattr(resource_utils, "write", activate_memory_controller)
    desired = 2 * resource_utils.MEBIBYTE
    if usage > 2:
        with pytest.raises(ResourceControlError, match="is below current usage"):
            manager._prepare_active_slice_memory("role.slice", desired, backend)
        assert (target / "memory.max").read_text() == "max"
    else:
        manager._prepare_active_slice_memory("role.slice", desired, backend)
        assert backend.apply_memory(str(target), desired, str(target)) == desired
    assert control.read_text() == "+memory", "Active slices need controller activation before reading usage"


@pytest.mark.parametrize("previous_memory", [None, 4 * 1024 ** 3])
@pytest.mark.parametrize("cpu_set", [None, "1-2"])
def test_memory_rejection_preserves_cpu_assignment_and_previous_memory_limit(
        tmp_path, monkeypatch, previous_memory, cpu_set):
    manager = ResourceControlManager()
    manager.systemd.SYSTEMD_UNIT_ROOT = str(tmp_path / "units")
    target = tmp_path / "role.slice"
    (target / "agent.service").mkdir(parents=True)
    (tmp_path / "cgroup.controllers").write_text("cpuset memory")
    (tmp_path / "cgroup.subtree_control").write_text("cpuset memory")
    (target / "cpuset.cpus").write_text("0-3")
    (target / "memory.current").write_text("2149494784")
    previous_limit = "max" if previous_memory is None else str(previous_memory)
    (target / "memory.max").write_text(previous_limit)
    backend = CgroupV2ResourceControlBackend(str(tmp_path))
    monkeypatch.setattr(manager.backend_factory, "cpu", lambda: backend)
    monkeypatch.setattr(manager.backend_factory, "memory", lambda: backend)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)
    monkeypatch.setattr(manager.systemd, "properties", lambda unit: {
        "LoadState": "loaded", "ActiveState": "active",
        "ControlGroup": "/role.slice" if unit == "role.slice" else "/role.slice/agent.service",
    })
    systemctl = Mock(return_value="")
    monkeypatch.setattr(manager.systemd, "_systemctl", systemctl)
    manager.systemd.configure_slice("role.slice", "AllowedCPUs", "0-3", "MemoryMax", previous_memory)
    desired_memory = 2 * 1024 ** 3

    with pytest.raises(ResourceControlError, match="is below current usage"):
        manager.apply("IMAGE_STORE", cpu_set, [handle("agent.service")], desired_memory, "role.slice")

    expected_cpus = cpu_set or "0-3"
    assert (target / "cpuset.cpus").read_text() == expected_cpus, \
        "Rejecting memory must not block requested CPUs or change unrequested CPUs"
    assert (target / "memory.max").read_text() == previous_limit
    with open(manager.systemd._drop_in_path("role.slice")) as stream:
        memory_setting = "" if previous_memory is None else "\nMemoryMax=%s" % previous_memory
        assert stream.read() == "[Slice]\nAllowedCPUs=%s%s\n" % (expected_cpus, memory_setting), \
            "Persist CPU while preserving the previous memory setting, not the rejected limit"
    systemctl.assert_called_once_with(["daemon-reload"], 30)

    (target / "memory.current").write_text(str(1024 ** 3))
    assert manager.apply("IMAGE_STORE", cpu_set, [handle("agent.service")], desired_memory, "role.slice")["synced"]
    assert (target / "memory.max").read_text() == str(desired_memory)
    with open(manager.systemd._drop_in_path("role.slice")) as stream:
        assert "MemoryMax=%s" % desired_memory in stream.read()


def test_active_v2_slice_rejects_unavailable_memory_controller(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    (tmp_path / "role.slice").mkdir()
    (tmp_path / "cgroup.controllers").write_text("cpuset")
    (tmp_path / "cgroup.subtree_control").write_text("")
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "ActiveState": "active", "ControlGroup": "/role.slice",
    })
    backend = CgroupV2ResourceControlBackend(str(tmp_path))
    with pytest.raises(ResourceControlError, match="Memory controller cannot be delegated"):
        manager._prepare_active_slice_memory("role.slice", resource_utils.MEBIBYTE, backend)
    assert not (tmp_path / "role.slice" / "memory.max").exists()


def test_exclusive_boundary_rejects_cgroup_v1(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV1ResourceControlBackend("/cpuset")))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    with pytest.raises(ResourceControlError) as error:
        manager.apply("COMPUTE", "2-3", [handle("zstack.service")], None, "zstack-compute.slice", "EXCLUSIVE")

    assert str(error.value) == "Exclusive CPU partitions are not supported by the cgroup backend"


def test_exclusive_boundary_requires_role_slice(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/cgroup2")))
    monkeypatch.setattr(manager.backend_factory, "memory", Mock(
        side_effect=ResourceControlError("No available memory controller was found")))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)
    monkeypatch.setattr(manager.systemd, "prune_services", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "configure_slice", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "configure_service", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "configured_slice", lambda _unit: "zstack-compute.slice")
    monkeypatch.setattr(manager, "_ensure_active_slice_target", Mock(return_value=None))

    with pytest.raises(ResourceControlError) as error:
        manager.apply("COMPUTE", "2-3", [handle("zstack.service")], None, "zstack-compute.slice", "EXCLUSIVE")

    assert "must be active before applying exclusive isolation" in str(error.value)


def test_memory_only_role_does_not_apply_cpu_boundary(monkeypatch):
    manager = ResourceControlManager()
    configure_slice = Mock(return_value=False)
    apply_cpu = Mock(return_value="0-7")
    monkeypatch.setattr(
        manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(
        manager.backend_factory, "memory", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(manager, "_prepare_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager.systemd, "prune_services", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "configure_slice", configure_slice)
    monkeypatch.setattr(manager.systemd, "configure_service", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "configured_slice", lambda _unit: "zstack-management.slice")
    monkeypatch.setattr(manager, "_ensure_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-management.slice")
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-management.slice")
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", apply_cpu)
    monkeypatch.setattr(manager.backend_factory.memory(), "apply_memory", lambda *_args: 2 * 1024 ** 3)
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/zstack-management.slice/zstack.service",
    })
    monkeypatch.setattr(manager.backend_factory.cpu(), "require_target", lambda group: "/sys/fs/cgroup%s" % group)
    monkeypatch.setattr(manager.backend_factory.memory(), "contains", lambda *_args: True)

    result = manager.apply("MANAGEMENT", None, [handle("zstack.service")], 2 * 1024 ** 3, "zstack-management.slice")

    assert result["synced"], "Memory-only assignments must sync independently"
    apply_cpu.assert_not_called()
    assert configure_slice.call_args.args[2] is None, "Unset CPU must not write AllowedCPUs"


@pytest.mark.parametrize("active_in_slice", [False, True])
def test_apply_stages_service_slice_without_restarting_running_service(tmp_path, monkeypatch, active_in_slice):
    manager = ResourceControlManager()
    manager.systemd.SYSTEMD_UNIT_ROOT = str(tmp_path / "units")
    commands = []
    monkeypatch.setattr(
        manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(
        manager.backend_factory, "memory", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(manager, "_prepare_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager.systemd, "_systemctl", lambda args, _timeout: commands.append(args) or "")
    monkeypatch.setattr(manager, "_ensure_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-compute.slice")
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-compute.slice")
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", lambda *_args: "0-3")
    monkeypatch.setattr(manager.backend_factory.memory(), "apply_memory", lambda *_args: 2 * 1024 ** 3)
    monkeypatch.setattr(manager.systemd, "properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "inactive" if unit == "collectd.service" else "active",
        "ControlGroup": ("/zstack-compute.slice" if active_in_slice else "/system.slice") + "/" + unit,
    })
    monkeypatch.setattr(manager, "_prepare_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(CgroupResourceControlBackend, "find_target", lambda self, group: self.root + group)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    services = [handle("collectd.service"), handle("node_exporter.service")]
    result = manager.apply("COMPUTE", "0-3", services, 2 * 1024 ** 3, "zstack-compute.slice")

    assert commands == [["daemon-reload"], ["daemon-reload"]], \
        "CPU configuration must load independently before validating and persisting the memory limit"
    assert manager.systemd.configured_slice("collectd.service") == "zstack-compute.slice"
    assert result["synced"] == active_in_slice, "Persisted inactive services must not hide active pending membership"


def test_legacy_systemd_hybrid_keeps_cpu_fallback_and_stages_role_memory(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(CgroupV1ResourceControlBackend, "supports_subtree_memory_limit", lambda *_args: True)
    service = handle("node_exporter.service")
    cpu_fallback = Mock(return_value=True)
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/cgroup2")))
    monkeypatch.setattr(manager.backend_factory, "memory", Mock(return_value=CgroupV1ResourceControlBackend("/memory")))
    monkeypatch.setattr(manager.systemd, "configure_slice", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "configure_service", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "configured_slice", lambda _unit: "zstack-compute.slice")
    monkeypatch.setattr(manager, "_ensure_active_slice_target", lambda *_args: None)
    monkeypatch.setattr(manager, "_apply_non_systemd_handle", cpu_fallback)
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: "/memory/zstack-compute.slice")
    monkeypatch.setattr(manager.backend_factory.memory(), "apply_memory", lambda *_args: 2 * 1024 ** 3)
    monkeypatch.setattr(manager.backend_factory.memory(), "contains", lambda *_args: False)
    monkeypatch.setattr(manager.systemd, "properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": ("/zstack-compute.slice" if unit.endswith(".slice") else "/system.slice/node_exporter.service"),
    })
    monkeypatch.setattr(manager, "_prepare_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    result = manager.apply("COMPUTE", "0-3", [service], 2 * 1024 ** 3, "zstack-compute.slice")

    assert cpu_fallback.call_count == 1
    assert not result["synced"], "Legacy services must remain unsynced before restart"


def test_legacy_systemd_release_reports_cpu_fallback_failure(monkeypatch):
    manager = ResourceControlManager()
    service = handle("node_exporter.service")
    monkeypatch.setattr(manager.systemd, "_remove_drop_in", lambda *_args: False)
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: None)
    monkeypatch.setattr(
        manager, "_release_non_systemd_handle", Mock(side_effect=ResourceControlError("CPU release failed")))

    with pytest.raises(ResourceControlError, match="CPU release failed"):
        manager._release_systemd_slice(
            CgroupV1ResourceControlBackend("/cpuset"), "COMPUTE", "zstack-compute.slice", [service], None)


@pytest.mark.parametrize("optional", [False, True])
@pytest.mark.parametrize("cpu_synced", [False, True])
def test_cgroup_v1_systemd_slice_uses_managed_cpuset_and_role_memory_boundary(
        tmp_path, monkeypatch, optional, cpu_synced):
    manager = ResourceControlManager()
    monkeypatch.setattr(CgroupV1ResourceControlBackend, "supports_subtree_memory_limit", lambda *_args: True)
    manager.systemd.SYSTEMD_UNIT_ROOT = str(tmp_path / "units")
    services = [handle("node_exporter.service"), dict(handle("collectd.service"), optional=optional),
                handle("pushgateway.service")]
    root = str(tmp_path / "cpuset")
    for service in (services[0], services[2]):
        os.makedirs(os.path.join(root, "zstack-compute.slice", service["value"]))
    apply_cpu = Mock(side_effect=["1-2" if cpu_synced else "1", "1-2"])
    apply_memory = Mock(return_value=2 * 1024 ** 3)
    systemctl = Mock()
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV1ResourceControlBackend(root)))
    monkeypatch.setattr(manager.backend_factory, "memory", Mock(return_value=CgroupV1ResourceControlBackend("/memory")))
    monkeypatch.setattr(manager, "_ensure_active_slice_target", lambda *_args: None)
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", apply_cpu)
    monkeypatch.setattr(manager.systemd, "_systemctl", systemctl)
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: "/memory/zstack-compute.slice")
    monkeypatch.setattr(manager.backend_factory.memory(), "apply_memory", apply_memory)
    monkeypatch.setattr(manager.backend_factory.memory(), "contains", lambda *_args: True)
    monkeypatch.setattr(manager.systemd, "properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "inactive",
        "ControlGroup": "" if unit == "collectd.service" else "/zstack-compute.slice/" + unit,
    })
    monkeypatch.setattr(manager, "_prepare_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    result = manager.apply("COMPUTE", "1-2", services, 2 * 1024 ** 3, "zstack-compute.slice")

    assert [call.args for call in apply_cpu.call_args_list] == [
        (os.path.join(root, "zstack-compute.slice", service["value"]), "1-2")
        for service in (services[0], services[2])
    ], "Existing cgroups must receive CPU limits regardless of the service ActiveState"
    apply_memory.assert_called_once_with("/memory/zstack-compute.slice", 2 * 1024 ** 3)
    assert resource_utils.read(manager.systemd._drop_in_path("collectd.service")) == \
        "[Service]\nSlice=zstack-compute.slice\n"
    assert resource_utils.read(manager.systemd._drop_in_path("zstack-compute.slice")) == \
        "[Slice]\nMemoryLimit=2147483648\n"
    assert [call.args for call in systemctl.call_args_list] == [
        (["daemon-reload"], 30), (["daemon-reload"], 30)]
    assert result["synced"] == cpu_synced, "CPU mismatch must not stop later CPU or role memory assignment"

    release_cpu = Mock()
    monkeypatch.setattr(manager.backend_factory.cpu(), "release_cpu_set", release_cpu)
    monkeypatch.setattr(manager.backend_factory, "find_memory", lambda: None)
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: None)
    assert manager.release("COMPUTE", [services[1], services[0], services[2]], "zstack-compute.slice")["synced"]
    assert [call.args[0] for call in release_cpu.call_args_list] == [
        os.path.join(root, "zstack-compute.slice", service["value"]) for service in (services[0], services[2])
    ], "An inactive required service must not prevent releasing following services"
    assert not os.path.exists(manager.systemd._drop_in_path("zstack-compute.slice"))
    assert manager.systemd.configured_slice("collectd.service") == "zstack-compute.slice"


def test_restart_fully_stops_units_before_start_so_new_slice_is_applied(monkeypatch):
    manager = ResourceControlManager()
    in_target = prepare_restart(manager, monkeypatch)
    node_exporter = handle("node_exporter.service")
    prometheus = handle("prometheus.service")
    node_exporter["restartable"] = True
    prometheus["restartable"] = True
    commands = []
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {"LoadState": "loaded", "ActiveState": "active"})
    monkeypatch.setattr(manager.systemd, "_systemctl", lambda args, _timeout: commands.append(args) or "")

    manager.restart("zstack-compute.slice", [node_exporter, prometheus])

    assert commands == [
        ["stop", "node_exporter.service"],
        ["start", "node_exporter.service"],
        ["stop", "prometheus.service"],
        ["start", "prometheus.service"],
    ]
    assert in_target.call_count == 2


def test_restart_failure_does_not_touch_remaining_services(monkeypatch):
    manager = ResourceControlManager()
    prepare_restart(manager, monkeypatch)
    services = [handle(name + ".service") for name in ["first", "second", "third"]]
    for service in services:
        service["restartable"] = True
    commands = []

    def systemctl(args, _timeout):
        commands.append(args)
        if args == ["start", "second.service"]:
            raise ResourceControlError("second service failed to start")
        return ""

    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {"LoadState": "loaded", "ActiveState": "active"})
    monkeypatch.setattr(manager.systemd, "_systemctl", systemctl)
    with pytest.raises(ResourceControlError, match="second service failed to start"):
        manager.restart("zstack-compute.slice", services)
    assert commands == [["stop", "first.service"], ["start", "first.service"],
                        ["stop", "second.service"], ["start", "second.service"]], (
        "failure must leave unprocessed services running: actual=%s" % commands)


def test_restart_reports_service_outside_configured_slice(monkeypatch):
    manager = ResourceControlManager()
    in_target = prepare_restart(manager, monkeypatch)
    in_target.return_value = False
    service = handle("node_exporter.service")
    service["restartable"] = True
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/system.slice/node_exporter.service",
    })
    monkeypatch.setattr(manager.systemd, "_systemctl", lambda _args, _timeout: "")

    with pytest.raises(ResourceControlError) as error:
        manager.restart("zstack-compute.slice", [service])

    assert str(error.value) == (
        "Systemd unit[node_exporter.service] did not enter "
        "slice[zstack-compute.slice] after restart")


def test_restart_allows_v1_slice_outside_cpuset_but_propagates_other_probe_errors(monkeypatch):
    manager = ResourceControlManager()
    service = handle("node_exporter.service")
    service["restartable"] = True
    commands = []
    monkeypatch.setattr(manager.systemd, "configured_slice", lambda _unit: "zstack-compute.slice")
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV1ResourceControlBackend("/cpuset")))
    monkeypatch.setattr(manager, "_active_slice_target", Mock(return_value=None))
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {"LoadState": "loaded", "ActiveState": "active"})
    monkeypatch.setattr(manager.systemd, "_systemctl", lambda args, _timeout: commands.append(args) or "")

    manager.restart("zstack-compute.slice", [service])

    assert commands == [["stop", "node_exporter.service"], ["start", "node_exporter.service"]]

    monkeypatch.setattr(manager, "_active_slice_target", Mock(side_effect=ResourceControlError("probe failed")))
    with pytest.raises(ResourceControlError) as error:
        manager.restart("zstack-compute.slice", [service])
    assert str(error.value) == "probe failed"


def test_restart_propagates_first_start_failure_without_local_retry(monkeypatch):
    manager = ResourceControlManager()
    prepare_restart(manager, monkeypatch)
    service = handle("node_exporter.service")
    service["restartable"] = True
    commands = []

    def systemctl(args, _timeout):
        commands.append(args)
        if args == ["start", "node_exporter.service"] and commands.count(args) == 1:
            raise ResourceControlError("start failed")
        return ""

    monkeypatch.setattr(manager.systemd, "_systemctl", systemctl)
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {"LoadState": "loaded", "ActiveState": "active"})

    with pytest.raises(ResourceControlError) as error:
        manager.restart("zstack-compute.slice", [service])

    assert commands == [
        ["stop", "node_exporter.service"],
        ["start", "node_exporter.service"],
    ]
    assert str(error.value) == "start failed"


def test_restart_reports_unit_when_single_start_stays_inactive(monkeypatch):
    manager = ResourceControlManager()
    prepare_restart(manager, monkeypatch)
    service = handle("node_exporter.service")
    service["restartable"] = True
    commands = []
    states = iter(["active", "inactive"])
    monkeypatch.setattr(manager.systemd, "_systemctl", lambda args, _timeout: commands.append(args) or "")
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "LoadState": "loaded", "ActiveState": next(states)})

    with pytest.raises(ResourceControlError) as error:
        manager.restart("zstack-compute.slice", [service])

    assert commands == [
        ["stop", "node_exporter.service"],
        ["start", "node_exporter.service"],
    ]
    assert str(error.value) == "Systemd unit[node_exporter.service] is not active after restart"


def test_systemctl_process_start_failure_propagates(monkeypatch):
    manager = ResourceControlManager()

    def fail_to_start(*_args, **_kwargs):
        raise OSError("systemctl is unavailable")

    monkeypatch.setattr(systemd_resource_control_utils.subprocess, "run", fail_to_start)

    with pytest.raises(OSError) as error:
        manager.systemd._systemctl(["show", "zstack.service"], 5)

    assert str(error.value) == "systemctl is unavailable"


def test_validate_cpu_set_rejects_omitted_cpu_set():
    manager = ResourceControlManager()

    with pytest.raises(ResourceControlError) as error:
        manager.validate_cpu_set(None)
    assert str(error.value) == "CPU set cannot be empty"


def test_invalid_memory_limit_reports_the_rejected_value():
    manager = ResourceControlManager()

    with pytest.raises(ResourceControlError) as error:
        manager.validate_memory_limit(1)

    assert str(error.value) == ("Memory limit[1] must be zero or a positive multiple of 1 MiB")


def test_inspect_reports_effective_cpu_memory_and_parent_memory_limit(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstack-compute.slice", "node_exporter.service")
    os.makedirs(target)
    for path, value in (
            (os.path.join(root, "memory.max"), "max"),
            (os.path.join(root, "zstack-compute.slice", "memory.max"), str(2 * 1024 ** 3)),
            (os.path.join(target, "memory.max"), "max"),
            (os.path.join(target, "memory.current"), str(96 * 1024 ** 2)),
            (os.path.join(target, "cpuset.cpus.effective"), "4-7"),
            (os.path.join(target, "cpu.stat"), "usage_usec 123\n")):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend(root)))
    monkeypatch.setattr(manager.backend_factory, "v2_roots", lambda: [root])
    monkeypatch.setattr(manager.backend_factory, "find_memory", Mock(return_value=CgroupV2ResourceControlBackend(root)))
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/zstack-compute.slice/node_exporter.service",
    })
    service = handle("node_exporter.service")
    service["restartable"] = True

    usage = manager.inspect("COMPUTE", [service])[0]

    assert usage == {
        "serviceName": "node_exporter",
        "restartable": True,
        "restartRequired": False,
        "state": "RUNNING",
        "cpuSet": "4-7",
        "cpuTime": 123000,
        "memory": 96 * 1024 ** 2,
        "memoryLimit": 2 * 1024 ** 3,
    }


def test_inspect_propagates_backend_failure_to_role(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(
        manager.backend_factory, "cpu",
        Mock(side_effect=ResourceControlError("No available cpuset controller was found")),
    )

    with pytest.raises(ResourceControlError) as error:
        manager.inspect("COMPUTE", [handle("kvmagent.service")])

    assert str(error.value) == "No available cpuset controller was found"


def test_inspect_propagates_service_probe_failure_to_role(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(
        manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(manager, "_inspect_target", Mock(side_effect=ResourceControlError("Systemd query failed")))

    with pytest.raises(ResourceControlError) as error:
        manager.inspect("COMPUTE", [handle("kvmagent.service")])

    assert str(error.value) == "Systemd query failed"


@pytest.mark.parametrize("load_state,expected", [("loaded", "INACTIVE"), ("not-found", "NOT_FOUND")])
def test_inspect_preserves_inactive_and_missing_wire_states(tmp_path, monkeypatch, load_state, expected):
    manager = ResourceControlManager()
    manager.systemd.SYSTEMD_UNIT_ROOT = str(tmp_path / "units")
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/cgroup")))
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "LoadState": load_state, "ActiveState": "inactive"})

    usage = manager.inspect("COMPUTE", [handle("agent.service")])[0]

    assert usage["state"] == expected, "Internal enums must preserve the existing wire strings"
    assert usage["restartRequired"] is False


def test_inspect_systemd_slices_reports_existing_cgroup_facts(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstone.cs.slice")
    os.makedirs(target)
    for path, value in (
            (os.path.join(root, "memory.max"), "max"),
            (os.path.join(target, "memory.max"), str(4 * 1024 ** 3)),
            (os.path.join(target, "memory.current"), str(3 * 1024 ** 3)),
            (os.path.join(target, "cpuset.cpus.effective"), "8-15"),
            (os.path.join(target, "cpu.stat"), "usage_usec 250\n")):
        with open(path, "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend(root)))
    monkeypatch.setattr(manager.backend_factory, "v2_roots", lambda: [root])
    monkeypatch.setattr(manager.backend_factory, "find_memory", Mock(return_value=CgroupV2ResourceControlBackend(root)))
    monkeypatch.setattr(manager.systemd, "properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/%s" % unit,
    })

    usages = manager.inspect_systemd_slices(["zstone.cs.slice"])

    assert usages == [{
        "cgroupName": "zstone.cs.slice",
        "cpuSet": "8-15",
        "cpuTime": 250000,
        "memory": 3 * 1024 ** 3,
        "memoryLimit": 4 * 1024 ** 3,
    }]


def test_inspect_systemd_slices_omits_inactive_cgroups(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    os.makedirs(root)
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend(root)))
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "inactive",
        "ControlGroup": "",
    })

    assert manager.inspect_systemd_slices(["zstone.cs.slice"]) == []


def test_inspect_reports_restart_required_until_service_enters_role_slice(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    role = os.path.join(root, "zstack.slice", "zstack-compute.slice")
    old_target = os.path.join(root, "system.slice", "node_exporter.service")
    ready_target = os.path.join(role, "node_exporter.service")
    for target in (role, old_target, ready_target):
        os.makedirs(target)
        with open(os.path.join(target, "cpuset.cpus.effective"), "w") as stream:
            stream.write("1-4")
    drop_in = str(tmp_path / "units" / "node_exporter.service.d" / manager.systemd.SYSTEMD_DROP_IN)
    os.makedirs(os.path.dirname(drop_in))
    with open(drop_in, "w") as stream:
        stream.write("[Service]\nSlice=zstack-compute.slice\n")
    current = {"group": "/system.slice/node_exporter.service"}
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend(root)))
    monkeypatch.setattr(manager.backend_factory, "v2_roots", lambda: [root])
    monkeypatch.setattr(
        manager.backend_factory, "memory",
        lambda: (_ for _ in ()).throw(ResourceControlError("No available memory controller was found")))
    monkeypatch.setattr(manager.systemd, "_drop_in_path", lambda _unit: drop_in)
    monkeypatch.setattr(manager.systemd, "properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": ("/zstack.slice/zstack-compute.slice" if unit == "zstack-compute.slice" else current["group"]),
    })

    pending = manager.inspect("COMPUTE", [handle("node_exporter.service")])[0]
    assert pending["restartRequired"] is True, (
        "Services still in the previous cgroup must require restart: "
        "expected=True actual=%s" % pending.get("restartRequired"))

    current["group"] = ("/zstack.slice/zstack-compute.slice/node_exporter.service")
    ready = manager.inspect("COMPUTE", [handle("node_exporter.service")])[0]
    assert ready["restartRequired"] is False, (
        "Services in the configured role slice must clear the restart hint: "
        "expected=False actual=%s" % ready.get("restartRequired"))


def test_inspect_reports_cpu_inherited_from_role_slice(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    role = os.path.join(root, "zstack-compute.slice")
    target = os.path.join(role, "zstack-kvmagent.service")
    os.makedirs(target)
    for path, value in (
            (os.path.join(role, "cpuset.cpus.effective"), "2-5"),
            (os.path.join(target, "cpu.stat"), "usage_usec 123\n"),
            (os.path.join(target, "memory.current"), str(96 * 1024 ** 2)),
            (os.path.join(target, "memory.max"), "max")):
        with open(path, "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend(root)))
    monkeypatch.setattr(manager.backend_factory, "v2_roots", lambda: [root])
    monkeypatch.setattr(manager.backend_factory, "find_memory", Mock(return_value=CgroupV2ResourceControlBackend(root)))
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/zstack-compute.slice/zstack-kvmagent.service",
    })

    usage = manager.inspect("COMPUTE", [handle("zstack-kvmagent.service")])[0]

    assert usage["state"] == "RUNNING"
    assert usage["cpuSet"] == "2-5", ("Show inherited role CPUs when the service has no cpuset controller")
    assert usage["cpuTime"] == 123000
    assert usage["memory"] == 96 * 1024 ** 2


def test_cgroup_v1_inspect_uses_main_pid_without_reporting_root_cpu_time(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    cpu_root = str(tmp_path / "cpuset")
    memory_root = str(tmp_path / "memory")
    memory_target = os.path.join(memory_root, "zstack.slice", "zstack-compute.slice", "node_exporter.service")
    os.makedirs(cpu_root)
    os.makedirs(memory_target)
    for path, value in (
            (os.path.join(cpu_root, "cpuset.cpus"), "0-5"),
            (os.path.join(memory_root, "memory.limit_in_bytes"), "9223372036854771712"),
            (os.path.join(memory_target, "memory.limit_in_bytes"), str(2 * 1024 ** 3)),
            (os.path.join(memory_target, "memory.usage_in_bytes"), str(96 * 1024 ** 2))):
        with open(path, "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV1ResourceControlBackend(cpu_root)))
    monkeypatch.setattr(
        manager.backend_factory, "find_memory", Mock(return_value=CgroupV1ResourceControlBackend(memory_root)))
    monkeypatch.setattr(manager.backend_factory, "v2_roots", lambda: [])
    monkeypatch.setattr(manager.backend_factory, "CGROUP_V1_CPUACCT_ROOTS", ())
    monkeypatch.setattr(manager.systemd, "_drop_in_path", lambda _unit: str(tmp_path / "missing-drop-in"))
    monkeypatch.setattr(manager.backend_factory.cpu(), "process_group", lambda _pid: cpu_root)
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": ("/zstack.slice/zstack-compute.slice/" "node_exporter.service"),
        "MainPID": "1234",
    })

    usage = manager.inspect("COMPUTE", [handle("node_exporter.service")])[0]

    assert usage == {
        "serviceName": "node_exporter",
        "restartable": False,
        "restartRequired": False,
        "state": "RUNNING",
        "cpuSet": "0-5",
        "cpuTime": None,
        "memory": 96 * 1024 ** 2,
        "memoryLimit": 2 * 1024 ** 3,
    }


def test_hybrid_inspect_reads_each_controller_from_its_own_hierarchy(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    cpu_root = str(tmp_path / "cgroup2")
    memory_root = str(tmp_path / "memory")
    cpuacct_root = str(tmp_path / "cpuacct")
    relative = os.path.join("zstack-compute.slice", "node_exporter.service")
    cpu_target = os.path.join(cpu_root, relative)
    memory_target = os.path.join(memory_root, relative)
    cpuacct_target = os.path.join(cpuacct_root, relative)
    for target in (cpu_target, memory_target, cpuacct_target):
        os.makedirs(target)
    for path, value in (
            (os.path.join(cpu_target, "cpuset.cpus.effective"), "4-7"),
            (os.path.join(memory_root, "memory.limit_in_bytes"), "9223372036854771712"),
            (os.path.join(memory_target, "memory.limit_in_bytes"), str(2 * 1024 ** 3)),
            (os.path.join(memory_target, "memory.usage_in_bytes"), str(96 * 1024 ** 2)),
            (os.path.join(cpuacct_target, "cpuacct.usage"), "123000")):
        with open(path, "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend(cpu_root)))
    monkeypatch.setattr(manager.backend_factory, "v2_roots", lambda: [cpu_root])
    monkeypatch.setattr(
        manager.backend_factory, "find_memory", Mock(return_value=CgroupV1ResourceControlBackend(memory_root)))
    monkeypatch.setattr(manager.backend_factory, "CGROUP_V1_CPUACCT_ROOTS", (cpuacct_root,))
    monkeypatch.setattr(manager.systemd, "properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/%s" % relative,
    })

    usage = manager.inspect("COMPUTE", [handle("node_exporter.service")])[0]

    assert usage["cpuSet"] == "4-7"
    assert usage["cpuTime"] == 123000
    assert usage["memory"] == 96 * 1024 ** 2
    assert usage["memoryLimit"] == 2 * 1024 ** 3


def test_hybrid_slice_drop_in_uses_independent_cpu_and_memory_backends(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    path = str(tmp_path / "role.conf")
    monkeypatch.setattr(manager.systemd, "_drop_in_path", lambda _unit: path)

    manager.systemd.configure_slice(
        "zstack-compute.slice", CgroupV2ResourceControlBackend("/cpuset").cpu_set_property, "0-3",
        CgroupV1ResourceControlBackend("/memory").memory_limit_property, 2 * 1024 ** 3)
    with open(path) as stream:
        v2_cpu_v1_memory = stream.read()
    assert "AllowedCPUs=0-3" in v2_cpu_v1_memory
    assert "MemoryLimit=%s" % (2 * 1024 ** 3) in v2_cpu_v1_memory
    assert "MemoryMax=" not in v2_cpu_v1_memory

    manager.systemd.configure_slice(
        "zstack-compute.slice", CgroupV1ResourceControlBackend("/cpuset").cpu_set_property, "0-3",
        CgroupV2ResourceControlBackend("/memory").memory_limit_property, 2 * 1024 ** 3)
    with open(path) as stream:
        v1_cpu_v2_memory = stream.read()
    assert "AllowedCPUs=" not in v1_cpu_v2_memory
    assert "MemoryMax=%s" % (2 * 1024 ** 3) in v1_cpu_v2_memory
    assert "MemoryLimit=" not in v1_cpu_v2_memory


def test_cpuset_and_memory_backends_are_detected_independently(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    v2_root = str(tmp_path / "unified")
    v1_cpuset_root = str(tmp_path / "cpuset")
    v1_memory_root = str(tmp_path / "memory")
    os.makedirs(v2_root)
    os.makedirs(v1_cpuset_root)
    os.makedirs(v1_memory_root)
    with open(os.path.join(v2_root, "cgroup.controllers"), "w") as stream:
        stream.write("cpuset cpu")
    with open(os.path.join(v1_cpuset_root, "cpuset.cpus"), "w") as stream:
        stream.write("0-7")
    with open(os.path.join(v1_memory_root, "memory.limit_in_bytes"), "w") as stream:
        stream.write("9223372036854771712")
    monkeypatch.setattr(manager.backend_factory, "v2_roots", lambda: [v2_root])
    monkeypatch.setattr(manager.backend_factory, "CGROUP_V1_ROOT", v1_cpuset_root)
    monkeypatch.setattr(manager.backend_factory, "CGROUP_V1_MEMORY_ROOT", v1_memory_root)

    assert type(manager.backend_factory.cpu().version) is int
    assert type(manager.backend_factory.memory().version) is int
    assert isinstance(manager.backend_factory.cpu(), CgroupV2ResourceControlBackend)
    assert manager.backend_factory.cpu().root == v2_root
    assert isinstance(manager.backend_factory.memory(), CgroupV1ResourceControlBackend)
    assert manager.backend_factory.memory().root == v1_memory_root

    with open(os.path.join(v2_root, "cgroup.controllers"), "w") as stream:
        stream.write("memory io")

    assert isinstance(manager.backend_factory.cpu(), CgroupV1ResourceControlBackend)
    assert manager.backend_factory.cpu().root == v1_cpuset_root
    assert isinstance(manager.backend_factory.memory(), CgroupV2ResourceControlBackend)
    assert manager.backend_factory.memory().root == v2_root


def test_missing_memory_controller_does_not_erase_staged_memory_limit(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    path = str(tmp_path / "role.conf")
    with open(path, "w") as stream:
        stream.write("[Slice]\nAllowedCPUs=0-3\nMemoryLimit=2147483648\n")
    monkeypatch.setattr(manager.systemd, "_drop_in_path", lambda _unit: path)

    manager.systemd.configure_slice(
        "zstack-compute.slice", CgroupV2ResourceControlBackend("/cpuset").cpu_set_property, "4-7", None, 4 * 1024 ** 3)

    with open(path) as stream:
        content = stream.read()
    assert "AllowedCPUs=4-7" in content
    assert "MemoryLimit=2147483648" in content


def test_handle_failure_propagates_to_the_assignment_boundary(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(
        manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend("/sys/fs/cgroup")))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    def resolve(_backend, _role, item):
        if item["value"] == "missing.service":
            raise ResourceControlError("Systemd unit does not exist")
        return "/sys/fs/cgroup/%s" % item["value"]

    monkeypatch.setattr(manager, "_resolve", resolve)
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", lambda *_args: "0-3")

    with pytest.raises(ResourceControlError) as error:
        manager.apply("MANAGEMENT", "0-3", [handle("zstack.service"), handle("missing.service")], None,)

    assert str(error.value) == "Systemd unit does not exist"


def test_apply_memory_limit_v2_sets_and_clears_limit_in_cgroup_files(tmp_path):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstack-role-management-unit-zstack.service")
    os.makedirs(target)
    memory_max = os.path.join(target, "memory.max")
    with open(memory_max, "w") as stream:
        stream.write("max")
    with open(os.path.join(target, "memory.current"), "w") as stream:
        stream.write("0")

    actual = CgroupV2ResourceControlBackend(root).apply_memory(target, 2 * resource_utils.MEBIBYTE, target)

    assert actual == 2 * resource_utils.MEBIBYTE
    with open(memory_max) as stream:
        assert stream.read() == str(2 * resource_utils.MEBIBYTE)

    actual = CgroupV2ResourceControlBackend(root).apply_memory(target, 0, target)

    assert actual == 0
    with open(memory_max) as stream:
        assert stream.read() == "max"


def test_apply_memory_limit_v2_rejects_limit_below_current_usage(tmp_path):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstack-role-COMPUTE-owner-host-agent")
    os.makedirs(target)
    memory_max = os.path.join(target, "memory.max")
    with open(memory_max, "w") as stream:
        stream.write("max")
    with open(os.path.join(target, "memory.current"), "w") as stream:
        stream.write(str(2 * resource_utils.MEBIBYTE))

    with pytest.raises(ResourceControlError) as error:
        CgroupV2ResourceControlBackend(root).apply_memory(target, resource_utils.MEBIBYTE, target)

    assert "is below current usage" in str(error.value)
    with open(memory_max) as stream:
        assert stream.read() == "max", ("Reject limits below usage before writing memory.max")


def test_apply_memory_limit_v2_accounts_for_resident_memory_after_process_move(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstack-role-COMPUTE-owner-host-agent")
    os.makedirs(target)
    for name, value in (("memory.max", "max"), ("memory.current", "4096"), ("cgroup.procs", "1234\n")):
        with open(os.path.join(target, name), "w") as stream:
            stream.write(value)
    monkeypatch.setattr(CgroupResourceControlBackend, "_resident_memory_usage",
                        staticmethod(lambda _process_file: 200 * resource_utils.MEBIBYTE))

    with pytest.raises(ResourceControlError) as error:
        CgroupV2ResourceControlBackend(root).apply_memory(target, resource_utils.MEBIBYTE, target)

    assert "is below current usage" in str(error.value)
    with open(os.path.join(target, "memory.max")) as stream:
        assert stream.read() == "max", ("Use PID RSS to reject unsafe limits before moving existing charges")


def test_resident_memory_usage_sums_process_rss(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(CgroupResourceControlBackend, "_process_ids", staticmethod(lambda _path: ["11", "12"]))
    real_isfile = resource_control.os.path.isfile
    expected_files = {"/sys/fs/cgroup/test/cgroup.procs", "/proc/11/status", "/proc/12/status",}
    monkeypatch.setattr(resource_control.os.path, "isfile", lambda path: path in expected_files or real_isfile(path))
    monkeypatch.setattr(
        resource_utils, "read",
        lambda path: "Name:\ttest\nVmRSS:\t%s kB\n" % ("1024" if path.endswith("/11/status") else "2048"))

    backend = CgroupResourceControlBackend("/cgroup")
    assert backend._resident_memory_usage("/sys/fs/cgroup/test/cgroup.procs") == 3 * resource_utils.MEBIBYTE


def test_apply_memory_limit_v1_rejects_limit_below_current_usage(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    cpuset_root = str(tmp_path / "cpuset")
    memory_root = str(tmp_path / "memory")
    target = os.path.join(cpuset_root, "zstack-role-COMPUTE-owner-host-agent")
    memory_target = os.path.join(memory_root, "zstack-role-COMPUTE-owner-host-agent")
    os.makedirs(target)
    os.makedirs(memory_target)
    for path, value in (
            (os.path.join(target, "cgroup.procs"), ""),
            (os.path.join(memory_root, "memory.limit_in_bytes"), "9223372036854771712"),
            (os.path.join(memory_target, "memory.limit_in_bytes"), "9223372036854771712"),
            (os.path.join(memory_target, "memory.usage_in_bytes"), str(2 * resource_utils.MEBIBYTE)),
            (os.path.join(memory_target, "cgroup.procs"), "")):
        with open(path, "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager.backend_factory, "CGROUP_V1_MEMORY_ROOT", memory_root)

    with pytest.raises(ResourceControlError) as error:
        manager._apply_memory_limit(CgroupV1ResourceControlBackend(cpuset_root), target, resource_utils.MEBIBYTE,
                                    CgroupV1ResourceControlBackend(memory_root))

    assert "is below current usage" in str(error.value)
    with open(os.path.join(memory_target, "memory.limit_in_bytes")) as stream:
        assert stream.read() == "9223372036854771712", ("Reject v1 limits below usage before writing")


def test_apply_propagates_memory_controller_unavailable(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstack.service")
    os.makedirs(target)
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV2ResourceControlBackend(root)))
    monkeypatch.setattr(
        manager.backend_factory, "memory",
        lambda: (_ for _ in ()).throw(ResourceControlError("No available memory controller was found")))
    monkeypatch.setattr(manager, "_resolve", lambda *_args: target)
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", lambda *_args: "0-3")
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    with pytest.raises(ResourceControlError) as error:
        manager.apply("MANAGEMENT", "0-3", [handle("zstack.service")], resource_utils.MEBIBYTE)

    assert str(error.value) == "No available memory controller was found"


@pytest.mark.parametrize(
    "cpu_version,memory_version",
    [(CGROUP_VERSION_V2, CGROUP_VERSION_V1), (CGROUP_VERSION_V1, CGROUP_VERSION_V2)],
)
def test_hybrid_apply_uses_memory_controller_independently_from_cpuset(
        tmp_path, monkeypatch, cpu_version, memory_version):
    manager = ResourceControlManager()
    cpu_root = str(tmp_path / "cpu")
    memory_root = str(tmp_path / "memory")
    relative = "zstack-role-MANAGEMENT-unit-zstack.service"
    cpu_target = os.path.join(cpu_root, relative)
    memory_target = os.path.join(memory_root, relative)
    os.makedirs(cpu_target)
    os.makedirs(memory_target)
    for path, value in (
            (os.path.join(cpu_target, "cgroup.procs"), ""),
            (os.path.join(memory_target, "cgroup.procs"), "")):
        with open(path, "w") as stream:
            stream.write(value)
    if memory_version == CGROUP_VERSION_V2:
        for path, value in (
                (os.path.join(memory_root, "memory.max"), "max"),
                (os.path.join(memory_target, "memory.max"), "max"),
                (os.path.join(memory_target, "memory.current"), "0")):
            with open(path, "w") as stream:
                stream.write(value)
    else:
        for path, value in (
                (os.path.join(memory_root, "memory.limit_in_bytes"), "9223372036854771712"),
                (os.path.join(memory_target, "memory.limit_in_bytes"), "9223372036854771712"),
                (os.path.join(memory_target, "memory.usage_in_bytes"), "0")):
            with open(path, "w") as stream:
                stream.write(value)
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=backend_for_version(cpu_version, cpu_root)))
    memory_backend = backend_for_version(memory_version, memory_root)
    monkeypatch.setattr(manager.backend_factory, "memory", lambda: memory_backend)
    monkeypatch.setattr(manager, "_resolve", lambda *_args: cpu_target)
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", lambda *_args: "0-3")
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    result = manager.apply("MANAGEMENT", "0-3", [handle("zstack.service")], 3 * resource_utils.MEBIBYTE)

    assert result["synced"], "Hybrid assignments must sync after both controllers apply"
    limit_name = ("memory.max" if memory_version == CGROUP_VERSION_V2 else "memory.limit_in_bytes")
    with open(os.path.join(memory_target, limit_name)) as stream:
        assert stream.read() == str(3 * resource_utils.MEBIBYTE)


def test_hybrid_v2_cpuset_moves_systemd_members_from_v1_hierarchy(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    systemd_root = str(tmp_path / "systemd")
    source = os.path.join(systemd_root, "system.slice", "zstack.service")
    target = os.path.join(root, "zstack-role-management-unit-zstack.service")
    os.makedirs(source)
    os.makedirs(root)
    with open(os.path.join(source, "cgroup.procs"), "w") as stream:
        stream.write("987654\n")

    real_mkdir = resource_utils.mkdir
    real_isdir = os.path.isdir

    def mkdir(path):
        real_mkdir(path)
        if path == target:
            for name, value in (("cgroup.procs", ""), ("cpuset.cpus", ""), ("cpuset.mems", "0")):
                with open(os.path.join(path, name), "w") as stream:
                    stream.write(value)

    monkeypatch.setattr(resource_utils, "mkdir", (mkdir))
    monkeypatch.setattr(manager.systemd, "CGROUP_SYSTEMD_V1_ROOT", systemd_root)
    monkeypatch.setattr(resource_control.os.path, "isdir", lambda path: path == "/proc/987654" or real_isdir(path))

    resolved = manager._resolve_systemd_fallback(
        CgroupV2ResourceControlBackend(root), handle("zstack.service"), "/system.slice/zstack.service", target)

    assert resolved == target
    with open(os.path.join(target, "cgroup.procs")) as stream:
        assert stream.read() == "987654"


def test_apply_memory_limit_v1_managed_group_moves_processes_and_releases(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    cpuset_root = str(tmp_path / "cpuset")
    memory_root = str(tmp_path / "memory")
    target = os.path.join(cpuset_root, "zstack-role-management-unit-zstack.service")
    os.makedirs(target)
    os.makedirs(memory_root)
    for path, value in (
            (os.path.join(target, "cgroup.procs"), "987654\n"),
            (os.path.join(memory_root, "memory.limit_in_bytes"), "9223372036854771712"),
            (os.path.join(memory_root, "cgroup.procs"), "")):
        with open(path, "w") as stream:
            stream.write(value)

    real_mkdir = resource_utils.mkdir
    real_write = resource_utils.write
    real_isdir = os.path.isdir

    def mkdir(path):
        real_mkdir(path)
        if path == os.path.join(memory_root, os.path.basename(target)):
            for name in ("memory.limit_in_bytes", "memory.usage_in_bytes", "cgroup.procs"):
                with open(os.path.join(path, name), "w") as stream:
                    stream.write("0" if name == "memory.usage_in_bytes" else "")

    def write(path, value):
        if path.endswith("cgroup.procs"):
            for current_root, _dirs, files in os.walk(str(tmp_path)):
                if "cgroup.procs" not in files:
                    continue
                process_file = os.path.join(current_root, "cgroup.procs")
                with open(process_file) as stream:
                    pids = [pid for pid in stream.read().split() if pid != value]
                with open(process_file, "w") as stream:
                    stream.write("\n".join(pids) + ("\n" if pids else ""))
            with open(path, "a") as stream:
                stream.write(value + "\n")
            return
        real_write(path, value)

    monkeypatch.setattr(resource_utils, "mkdir", (mkdir))
    monkeypatch.setattr(resource_utils, "write", (write))
    monkeypatch.setattr(manager.backend_factory, "cpu", Mock(return_value=CgroupV1ResourceControlBackend(cpuset_root)))
    monkeypatch.setattr(
        manager.backend_factory, "memory", Mock(return_value=CgroupV1ResourceControlBackend(memory_root)))
    monkeypatch.setattr(
        manager.backend_factory, "find_memory", Mock(return_value=CgroupV1ResourceControlBackend(memory_root)))
    monkeypatch.setattr(manager, "_resolve", lambda *_args: target)
    monkeypatch.setattr(manager, "_resolve_for_release", lambda *_args: target)
    monkeypatch.setattr(manager.backend_factory.cpu(), "apply_cpu_set", lambda _target, desired: desired)
    monkeypatch.setattr(manager.backend_factory.cpu(), "release_cpu_set", lambda *_args: None)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)
    monkeypatch.setattr(manager.backend_factory, "CGROUP_V1_MEMORY_ROOT", memory_root)
    monkeypatch.setattr(resource_control.os.path, "isdir", lambda path: path == "/proc/987654" or real_isdir(path))

    limited = manager.apply("MANAGEMENT", "0-3", [handle("zstack.service")], 3 * resource_utils.MEBIBYTE)
    memory_target = os.path.join(memory_root, os.path.basename(target))

    assert limited["synced"]
    with open(os.path.join(memory_target, "memory.limit_in_bytes")) as stream:
        assert stream.read() == str(3 * resource_utils.MEBIBYTE)
    with open(os.path.join(target, "cgroup.procs")) as stream:
        assert stream.read() == ""
    with open(os.path.join(memory_target, "cgroup.procs")) as stream:
        assert stream.read() == "987654\n"

    released = manager.release("MANAGEMENT", [handle("zstack.service")])

    assert released["synced"]
    with open(os.path.join(memory_target, "memory.limit_in_bytes")) as stream:
        assert stream.read() == "9223372036854771712"
    with open(os.path.join(memory_target, "cgroup.procs")) as stream:
        assert stream.read() == ""
    with open(os.path.join(memory_root, "cgroup.procs")) as stream:
        assert stream.read() == "987654\n"
