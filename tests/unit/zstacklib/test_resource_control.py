import os
from unittest.mock import Mock

import pytest

from zstacklib.utils import resource_control
from zstacklib.utils.resource_control import (
    MemoryControllerUnavailableError,
    ResourceControlError,
    ResourceControlManager,
    ResourceControlUnavailableError,
    SystemdControlGroupNotFoundError,
)


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


def prepare_restart(manager, monkeypatch):
    in_target = Mock(return_value=True)
    monkeypatch.setattr(manager, "_configured_slice", lambda _unit: "zstack-compute.slice")
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-compute.slice")
    monkeypatch.setattr(manager, "_control_group_in_target", in_target)
    return in_target


def test_release_with_only_optional_handles_is_an_idempotent_success(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"),)
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V2_MEMORY", "/sys/fs/cgroup"),)
    monkeypatch.setattr(manager, "_resolve_for_release", lambda *_args: None)

    result = manager.release("MANAGEMENT", [optional_handle("collectd.service")])

    assert result["synced"], "释放不存在的可选 Handle 必须保持幂等成功"


def test_role_memory_limit_is_applied_once_at_slice_boundary(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V2_MEMORY", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_validate_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager, "_prune_systemd_service_drop_ins", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_slice", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: False)
    monkeypatch.setattr(manager, "_ensure_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-management.slice")
    monkeypatch.setattr(manager, "_active_controller_slice_target",
                        lambda *_args: "/sys/fs/cgroup/zstack-management.slice")
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")
    apply_memory = Mock(return_value=4 * 1024 * 1024 * 1024)
    monkeypatch.setattr(manager, "_apply_memory_target", apply_memory)
    monkeypatch.setattr(manager, "_systemd_properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/zstack-management.slice/%s" % unit,
    })
    monkeypatch.setattr(manager, "_systemd_target", lambda _root, group: "/sys/fs/cgroup%s" % group)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    result = manager.apply(
        "MANAGEMENT",
        "0-3",
        [handle("zstack.service"), handle("mariadb.service")],
        4 * 1024 * 1024 * 1024,
        "zstack-management.slice",
    )

    apply_memory.assert_called_once_with(
        "CGROUP_V2_MEMORY", "/sys/fs/cgroup",
        "/sys/fs/cgroup/zstack-management.slice",
        4 * 1024 * 1024 * 1024)
    assert result["synced"], "Role Slice 的 CPU 和内存边界均生效后才能返回 synced"


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

    actual = manager._apply_cpu_boundary(root, "CGROUP_V2_CPUSET", target, "4-7", "EXCLUSIVE")

    assert actual == "4-7"
    with open(os.path.join(target, "cpuset.cpus.partition")) as stream:
        assert stream.read() == "root"
    with open(os.path.join(target, "cpuset.cpus.exclusive")) as stream:
        assert stream.read() == "4-7"

    actual = manager._apply_cpu_boundary(root, "CGROUP_V2_CPUSET", target, "2-5", "SHARED")

    assert actual == "2-5"
    with open(os.path.join(target, "cpuset.cpus.partition")) as stream:
        assert stream.read() == "member"
    with open(os.path.join(target, "cpuset.cpus.exclusive")) as stream:
        assert stream.read() == "\n"


def test_exclusive_boundary_rejects_cgroup_v1(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V1_CPUSET", "/cpuset"))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    with pytest.raises(ResourceControlError) as error:
        manager.apply("COMPUTE", "2-3", [handle("zstack.service")], None, "zstack-compute.slice", "EXCLUSIVE")

    assert str(error.value) == "Exclusive CPU partitions require cgroup v2"


def test_exclusive_boundary_requires_role_slice(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/cgroup2"))
    monkeypatch.setattr(manager, "_memory_backend", Mock(
        side_effect=MemoryControllerUnavailableError("No available memory controller was found")))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)
    monkeypatch.setattr(manager, "_prune_systemd_service_drop_ins", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_slice", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: False)
    monkeypatch.setattr(manager, "_ensure_active_slice_target", Mock(
        side_effect=SystemdControlGroupNotFoundError("Systemd control group does not exist")))

    with pytest.raises(ResourceControlError) as error:
        manager.apply("COMPUTE", "2-3", [handle("zstack.service")], None, "zstack-compute.slice", "EXCLUSIVE")

    assert "must be active before applying exclusive isolation" in str(error.value)


def test_memory_only_role_does_not_apply_cpu_boundary(monkeypatch):
    manager = ResourceControlManager()
    configure_slice = Mock(return_value=False)
    apply_cpu = Mock(return_value="0-7")
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V2_MEMORY", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_validate_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager, "_prune_systemd_service_drop_ins", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_slice", configure_slice)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: False)
    monkeypatch.setattr(manager, "_ensure_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-management.slice")
    monkeypatch.setattr(manager, "_active_controller_slice_target",
                        lambda *_args: "/sys/fs/cgroup/zstack-management.slice")
    monkeypatch.setattr(manager, "_apply_to_group", apply_cpu)
    monkeypatch.setattr(manager, "_apply_memory_target", lambda *_args: 2 * 1024 ** 3)
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/zstack-management.slice/zstack.service",
    })
    monkeypatch.setattr(manager, "_systemd_target", lambda _root, group: "/sys/fs/cgroup%s" % group)
    monkeypatch.setattr(manager, "_control_group_in_target", lambda *_args: True)

    result = manager.apply("MANAGEMENT", None, [handle("zstack.service")], 2 * 1024 ** 3, "zstack-management.slice")

    assert result["synced"], "仅设置内存时必须独立完成内存边界同步"
    apply_cpu.assert_not_called()
    assert configure_slice.call_args.args[3] is None, "未设置 CPU 时 systemd Slice 不得写入 AllowedCPUs"


def test_apply_stages_service_slice_without_restarting_running_service(monkeypatch):
    manager = ResourceControlManager()
    commands = []
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V2_MEMORY", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_validate_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager, "_configure_systemd_slice", lambda *_args: True)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: True)
    monkeypatch.setattr(manager, "_systemctl", lambda args, _timeout: commands.append(args) or "")
    monkeypatch.setattr(manager, "_ensure_active_slice_target", lambda *_args: "/sys/fs/cgroup/zstack-compute.slice")
    monkeypatch.setattr(manager, "_active_controller_slice_target",
                        lambda *_args: "/sys/fs/cgroup/zstack-compute.slice")
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")
    monkeypatch.setattr(manager, "_apply_memory_target", lambda *_args: 2 * 1024 ** 3)
    monkeypatch.setattr(manager, "_systemd_properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": ("/zstack-compute.slice" if unit.endswith(".slice") else "/system.slice/node_exporter.service"),
    })
    monkeypatch.setattr(manager, "_validate_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager, "_systemd_target", lambda _root, group: "/sys/fs/cgroup%s" % group)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    result = manager.apply("COMPUTE", "0-3", [handle("node_exporter.service")], 2 * 1024 ** 3, "zstack-compute.slice")

    assert commands == [["daemon-reload"]]
    assert not result["synced"], "仅写入 drop-in、进程尚未进入 Slice 时不能返回 synced"


def test_legacy_systemd_hybrid_keeps_cpu_fallback_and_stages_role_memory(monkeypatch):
    manager = ResourceControlManager()
    service = handle("node_exporter.service")
    cpu_fallback = Mock(return_value={"state": "READY", "cpuSet": "0-3", "memory": None})
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/cgroup2"))
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V1_MEMORY", "/memory"))
    monkeypatch.setattr(manager, "_configure_systemd_slice", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: False)
    monkeypatch.setattr(
        manager, "_ensure_active_slice_target",
        lambda *_args: (_ for _ in ()).throw(SystemdControlGroupNotFoundError("Systemd control group does not exist")))
    monkeypatch.setattr(manager, "_apply_non_systemd_handle", cpu_fallback)
    monkeypatch.setattr(manager, "_active_controller_slice_target", lambda *_args: "/memory/zstack-compute.slice")
    monkeypatch.setattr(manager, "_apply_memory_target", lambda *_args: 2 * 1024 ** 3)
    monkeypatch.setattr(manager, "_control_group_in_target", lambda *_args: False)
    monkeypatch.setattr(manager, "_systemd_properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": ("/zstack-compute.slice" if unit.endswith(".slice") else "/system.slice/node_exporter.service"),
    })
    monkeypatch.setattr(manager, "_validate_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    result = manager.apply("COMPUTE", "0-3", [service], 2 * 1024 ** 3, "zstack-compute.slice")

    assert cpu_fallback.call_count == 1
    assert not result["synced"], "遗留 systemd 服务重启前必须保持 Unsynced"


def test_legacy_systemd_release_preserves_cpu_fallback_failure(monkeypatch):
    manager = ResourceControlManager()
    service = handle("node_exporter.service")
    monkeypatch.setattr(manager, "_remove_systemd_service_drop_ins", lambda *_args: False)
    monkeypatch.setattr(manager, "_remove_drop_in", lambda *_args: False)
    monkeypatch.setattr(
        manager, "_active_slice_target",
        lambda *_args: (_ for _ in ()).throw(SystemdControlGroupNotFoundError("Systemd control group does not exist")))
    monkeypatch.setattr(manager, "_release_non_systemd_handle", lambda *_args: {
        "state": "ERROR", "cpuSet": None, "memory": None})
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/system.slice/node_exporter.service",
    })

    result = manager._release_systemd_slice(
        "/cpuset", "CGROUP_V1_CPUSET", "COMPUTE",
        "zstack-compute.slice", [service], None, None)

    assert not result["synced"], "释放失败不能被成功的 HTTP 调用掩盖"


def test_cgroup_v1_systemd_slice_uses_managed_cpuset_and_role_memory_boundary(monkeypatch):
    manager = ResourceControlManager()
    service = handle("node_exporter.service")
    cpu_fallback = Mock(return_value={"state": "READY", "cpuSet": "0-3", "memory": None})
    apply_memory = Mock(return_value=2 * 1024 ** 3)
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V1_CPUSET", "/cpuset"))
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V1_MEMORY", "/memory"))
    monkeypatch.setattr(manager, "_configure_systemd_slice", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: False)
    monkeypatch.setattr(
        manager, "_ensure_active_slice_target",
        lambda *_args: (_ for _ in ()).throw(SystemdControlGroupNotFoundError("Systemd control group does not exist")))
    monkeypatch.setattr(manager, "_apply_non_systemd_handle", cpu_fallback)
    monkeypatch.setattr(manager, "_active_controller_slice_target", lambda *_args: "/memory/zstack-compute.slice")
    monkeypatch.setattr(manager, "_apply_memory_target", apply_memory)
    monkeypatch.setattr(manager, "_control_group_in_target", lambda *_args: True)
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/zstack-compute.slice/node_exporter.service",
    })
    monkeypatch.setattr(manager, "_validate_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    result = manager.apply("COMPUTE", "0-3", [service], 2 * 1024 ** 3, "zstack-compute.slice")

    assert cpu_fallback.call_count == 1
    apply_memory.assert_called_once_with("CGROUP_V1_MEMORY", "/memory", "/memory/zstack-compute.slice", 2 * 1024 ** 3)
    assert result["synced"], "v1 CPU 和内存总体边界都生效后必须返回 synced"


def test_restart_fully_stops_units_before_start_so_new_slice_is_applied(monkeypatch):
    manager = ResourceControlManager()
    in_target = prepare_restart(manager, monkeypatch)
    node_exporter = handle("node_exporter.service")
    prometheus = handle("prometheus.service")
    node_exporter["restartable"] = True
    prometheus["restartable"] = True
    commands = []
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {"LoadState": "loaded", "ActiveState": "active"})
    monkeypatch.setattr(manager, "_systemctl", lambda args, _timeout: commands.append(args) or "")

    manager.restart("zstack-compute.slice", [node_exporter, prometheus])

    assert commands == [
        ["stop", "node_exporter.service"],
        ["start", "node_exporter.service"],
        ["stop", "prometheus.service"],
        ["start", "prometheus.service"],
    ]
    assert in_target.call_count == 2


def test_restart_reports_service_outside_configured_slice(monkeypatch):
    manager = ResourceControlManager()
    in_target = prepare_restart(manager, monkeypatch)
    in_target.return_value = False
    service = handle("node_exporter.service")
    service["restartable"] = True
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/system.slice/node_exporter.service",
    })
    monkeypatch.setattr(manager, "_systemctl", lambda _args, _timeout: "")

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
    monkeypatch.setattr(manager, "_configured_slice", lambda _unit: "zstack-compute.slice")
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V1_CPUSET", "/cpuset"))
    monkeypatch.setattr(manager, "_active_slice_target", Mock(side_effect=SystemdControlGroupNotFoundError("missing")))
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {"LoadState": "loaded", "ActiveState": "active"})
    monkeypatch.setattr(manager, "_systemctl", lambda args, _timeout: commands.append(args) or "")

    manager.restart("zstack-compute.slice", [service])

    assert commands == [["stop", "node_exporter.service"], ["start", "node_exporter.service"]]

    monkeypatch.setattr(manager, "_active_slice_target", Mock(side_effect=ResourceControlError("probe failed")))
    with pytest.raises(ResourceControlError) as error:
        manager.restart("zstack-compute.slice", [service])
    assert str(error.value) == "probe failed"


def test_restart_recovers_stopped_unit_after_first_start_failure(monkeypatch):
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

    monkeypatch.setattr(manager, "_systemctl", systemctl)
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {"LoadState": "loaded", "ActiveState": "active"})

    with pytest.raises(ResourceControlError) as error:
        manager.restart("zstack-compute.slice", [service])

    assert commands == [
        ["stop", "node_exporter.service"],
        ["start", "node_exporter.service"],
        ["start", "node_exporter.service"],
    ]
    assert str(error.value) == ("Systemd unit[node_exporter.service] failed to restart: start failed")


def test_restart_reports_unit_when_recovery_stays_inactive(monkeypatch):
    manager = ResourceControlManager()
    prepare_restart(manager, monkeypatch)
    service = handle("node_exporter.service")
    service["restartable"] = True
    commands = []
    states = iter(["active", "inactive", "inactive"])
    monkeypatch.setattr(manager, "_systemctl", lambda args, _timeout: commands.append(args) or "")
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded", "ActiveState": next(states)})

    with pytest.raises(ResourceControlError) as error:
        manager.restart("zstack-compute.slice", [service])

    assert commands == [
        ["stop", "node_exporter.service"],
        ["start", "node_exporter.service"],
        ["start", "node_exporter.service"],
    ]
    assert str(error.value) == (
        "Systemd unit[node_exporter.service] failed to restart: "
        "Systemd unit[node_exporter.service] is not active after restart; "
        "retry also failed: Systemd unit[node_exporter.service] is not "
        "active after restart")


def test_systemctl_start_failure_is_a_resource_control_error(monkeypatch):
    manager = ResourceControlManager()

    def fail_to_start(*_args, **_kwargs):
        raise OSError("systemctl is unavailable")

    monkeypatch.setattr(resource_control.subprocess, "Popen", fail_to_start)

    with pytest.raises(ResourceControlError) as error:
        manager._systemctl(["show", "zstack.service"], 5)

    assert str(error.value) == "Failed to execute systemctl: systemctl is unavailable"


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
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", root))
    monkeypatch.setattr(manager, "_v2_roots", lambda: [root])
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V2_MEMORY", root))
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
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
        manager,
        "_backend",
        Mock(side_effect=ResourceControlUnavailableError("No available cpuset controller was found")),
    )

    with pytest.raises(ResourceControlError) as error:
        manager.inspect("COMPUTE", [handle("kvmagent.service")])

    assert str(error.value) == "No available cpuset controller was found"


def test_inspect_propagates_service_probe_failure_to_role(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_inspect_target", Mock(side_effect=ResourceControlError("Systemd query failed")))

    with pytest.raises(ResourceControlError) as error:
        manager.inspect("COMPUTE", [handle("kvmagent.service")])

    assert str(error.value) == "Systemd query failed"


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
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", root))
    monkeypatch.setattr(manager, "_v2_roots", lambda: [root])
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V2_MEMORY", root))
    monkeypatch.setattr(manager, "_systemd_properties", lambda unit: {
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
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", root))
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
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
    drop_in = str(tmp_path / "units" / "node_exporter.service.d" / manager.SYSTEMD_DROP_IN)
    os.makedirs(os.path.dirname(drop_in))
    with open(drop_in, "w") as stream:
        stream.write("[Service]\nSlice=zstack-compute.slice\n")
    current = {"group": "/system.slice/node_exporter.service"}
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", root))
    monkeypatch.setattr(manager, "_v2_roots", lambda: [root])
    monkeypatch.setattr(
        manager, "_memory_backend",
        lambda: (_ for _ in ()).throw(MemoryControllerUnavailableError("No available memory controller was found")))
    monkeypatch.setattr(manager, "_drop_in_path", lambda _unit: drop_in)
    monkeypatch.setattr(manager, "_systemd_properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": ("/zstack.slice/zstack-compute.slice" if unit == "zstack-compute.slice" else current["group"]),
    })

    pending = manager.inspect("COMPUTE", [handle("node_exporter.service")])[0]
    assert pending["restartRequired"] is True, (
        "已写入 Role Slice 配置但仍运行在旧 cgroup 的服务必须提示重启: "
        "expected=True actual=%s" % pending.get("restartRequired"))

    current["group"] = ("/zstack.slice/zstack-compute.slice/node_exporter.service")
    ready = manager.inspect("COMPUTE", [handle("node_exporter.service")])[0]
    assert ready["restartRequired"] is False, (
        "服务进入目标 Role Slice 后必须清除重启提示: "
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
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", root))
    monkeypatch.setattr(manager, "_v2_roots", lambda: [root])
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V2_MEMORY", root))
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/zstack-compute.slice/zstack-kvmagent.service",
    })

    usage = manager.inspect("COMPUTE", [handle("zstack-kvmagent.service")])[0]

    assert usage["state"] == "RUNNING"
    assert usage["cpuSet"] == "2-5", ("service cgroup 未启用 cpuset controller 时必须展示 Role Slice 的继承 CPU 范围")
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
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V1_CPUSET", cpu_root))
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V1_MEMORY", memory_root))
    monkeypatch.setattr(manager, "_v2_roots", lambda: [])
    monkeypatch.setattr(manager, "CGROUP_V1_CPUACCT_ROOTS", ())
    monkeypatch.setattr(manager, "_drop_in_path", lambda _unit: str(tmp_path / "missing-drop-in"))
    monkeypatch.setattr(manager, "_process_group", lambda _root, _backend, _pid: cpu_root)
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
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
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", cpu_root))
    monkeypatch.setattr(manager, "_v2_roots", lambda: [cpu_root])
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V1_MEMORY", memory_root))
    monkeypatch.setattr(manager, "CGROUP_V1_CPUACCT_ROOTS", (cpuacct_root,))
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
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
    monkeypatch.setattr(manager, "_drop_in_path", lambda _unit: path)

    manager._configure_systemd_slice(
        "CGROUP_V2_CPUSET", "CGROUP_V1_MEMORY",
        "zstack-compute.slice", "0-3", 2 * 1024 ** 3)
    with open(path) as stream:
        v2_cpu_v1_memory = stream.read()
    assert "AllowedCPUs=0-3" in v2_cpu_v1_memory
    assert "MemoryLimit=%s" % (2 * 1024 ** 3) in v2_cpu_v1_memory
    assert "MemoryMax=" not in v2_cpu_v1_memory

    manager._configure_systemd_slice(
        "CGROUP_V1_CPUSET", "CGROUP_V2_MEMORY",
        "zstack-compute.slice", "0-3", 2 * 1024 ** 3)
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
    monkeypatch.setattr(manager, "_v2_roots", lambda: [v2_root])
    monkeypatch.setattr(manager, "CGROUP_V1_ROOT", v1_cpuset_root)
    monkeypatch.setattr(manager, "CGROUP_V1_MEMORY_ROOT", v1_memory_root)

    assert manager._backend() == ("CGROUP_V2_CPUSET", v2_root)
    assert manager._memory_backend() == ("CGROUP_V1_MEMORY", v1_memory_root)

    with open(os.path.join(v2_root, "cgroup.controllers"), "w") as stream:
        stream.write("memory io")

    assert manager._backend() == ("CGROUP_V1_CPUSET", v1_cpuset_root)
    assert manager._memory_backend() == ("CGROUP_V2_MEMORY", v2_root)


def test_missing_memory_controller_does_not_erase_staged_memory_limit(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    path = str(tmp_path / "role.conf")
    with open(path, "w") as stream:
        stream.write("[Slice]\nAllowedCPUs=0-3\nMemoryLimit=2147483648\n")
    monkeypatch.setattr(manager, "_drop_in_path", lambda _unit: path)

    manager._configure_systemd_slice("CGROUP_V2_CPUSET", None, "zstack-compute.slice", "4-7", 4 * 1024 ** 3)

    with open(path) as stream:
        content = stream.read()
    assert "AllowedCPUs=4-7" in content
    assert "MemoryLimit=2147483648" in content


def test_handle_failure_keeps_assignment_unsatisfied(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    def resolve(_root, _backend, _role, item):
        if item["value"] == "missing.service":
            raise ResourceControlError("Systemd unit does not exist")
        return "/sys/fs/cgroup/%s" % item["value"]

    monkeypatch.setattr(manager, "_resolve", resolve)
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")

    result = manager.apply("MANAGEMENT", "0-3", [handle("zstack.service"), handle("missing.service")], None,)

    assert not result["synced"], "任一必需 Handle 失败都必须让 Assignment 保持 Unsynced"


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

    actual = manager._apply_memory_limit(root, target, 2 * manager.MEBIBYTE, "CGROUP_V2_MEMORY", root)

    assert actual == 2 * manager.MEBIBYTE
    with open(memory_max) as stream:
        assert stream.read() == str(2 * manager.MEBIBYTE)

    actual = manager._apply_memory_limit(root, target, 0, "CGROUP_V2_MEMORY", root)

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
        stream.write(str(2 * manager.MEBIBYTE))

    with pytest.raises(ResourceControlError) as error:
        manager._apply_memory_limit(root, target, manager.MEBIBYTE, "CGROUP_V2_MEMORY", root)

    assert "is below current usage" in str(error.value)
    with open(memory_max) as stream:
        assert stream.read() == "max", ("低于当前用量的上限必须在写 memory.max 前拒绝，不能 OOM 杀死 Consumer")


def test_apply_memory_limit_v2_accounts_for_resident_memory_after_process_move(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstack-role-COMPUTE-owner-host-agent")
    os.makedirs(target)
    for name, value in (("memory.max", "max"), ("memory.current", "4096"), ("cgroup.procs", "1234\n")):
        with open(os.path.join(target, name), "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager, "_resident_memory_usage", lambda _process_file: 200 * manager.MEBIBYTE, raising=False)

    with pytest.raises(ResourceControlError) as error:
        manager._apply_memory_limit(root, target, manager.MEBIBYTE, "CGROUP_V2_MEMORY", root)

    assert "is below current usage" in str(error.value)
    with open(os.path.join(target, "memory.max")) as stream:
        assert stream.read() == "max", ("迁移不会同步迁移已有 memory charge，必须用 PID RSS 阻止自杀式限额")


def test_resident_memory_usage_sums_process_rss(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager, "_process_ids", lambda _path: ["11", "12"])
    real_isfile = resource_control.os.path.isfile
    expected_files = {"/sys/fs/cgroup/test/cgroup.procs", "/proc/11/status", "/proc/12/status",}
    monkeypatch.setattr(resource_control.os.path, "isfile", lambda path: path in expected_files or real_isfile(path))
    monkeypatch.setattr(
        manager, "_read",
        lambda path: "Name:\ttest\nVmRSS:\t%s kB\n" % ("1024" if path.endswith("/11/status") else "2048"))

    assert manager._resident_memory_usage("/sys/fs/cgroup/test/cgroup.procs") == (3 * manager.MEBIBYTE)


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
            (os.path.join(memory_target, "memory.usage_in_bytes"), str(2 * manager.MEBIBYTE)),
            (os.path.join(memory_target, "cgroup.procs"), "")):
        with open(path, "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager, "CGROUP_V1_MEMORY_ROOT", memory_root)

    with pytest.raises(ResourceControlError) as error:
        manager._apply_memory_limit(cpuset_root, target, manager.MEBIBYTE, "CGROUP_V1_MEMORY", memory_root)

    assert "is below current usage" in str(error.value)
    with open(os.path.join(memory_target, "memory.limit_in_bytes")) as stream:
        assert stream.read() == "9223372036854771712", ("低于当前用量的 v1 上限必须在写入前拒绝")


def test_apply_reports_memory_controller_unavailable_per_handle(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstack.service")
    os.makedirs(target)
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", root))
    monkeypatch.setattr(
        manager,
        "_memory_backend",
        lambda: (_ for _ in ()).throw(MemoryControllerUnavailableError("No available memory controller was found")))
    monkeypatch.setattr(manager, "_resolve", lambda *_args: target)
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    result = manager.apply("MANAGEMENT", "0-3", [handle("zstack.service")], manager.MEBIBYTE)

    assert not result["synced"], "请求内存限制时缺少内存控制器必须返回未同步"


@pytest.mark.parametrize(
    "cpu_backend,memory_backend",
    [("CGROUP_V2_CPUSET", "CGROUP_V1_MEMORY"), ("CGROUP_V1_CPUSET", "CGROUP_V2_MEMORY"),],
)
def test_hybrid_apply_uses_memory_controller_independently_from_cpuset(
        tmp_path, monkeypatch, cpu_backend, memory_backend):
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
    if memory_backend == "CGROUP_V2_MEMORY":
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
    monkeypatch.setattr(manager, "_backend", lambda: (cpu_backend, cpu_root))
    monkeypatch.setattr(manager, "_memory_backend", lambda: (memory_backend, memory_root))
    monkeypatch.setattr(manager, "_resolve", lambda *_args: cpu_target)
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)

    result = manager.apply("MANAGEMENT", "0-3", [handle("zstack.service")], 3 * manager.MEBIBYTE)

    assert result["synced"], "hybrid 环境中独立的 CPU 和内存控制器都生效后必须同步"
    limit_name = ("memory.max" if memory_backend == "CGROUP_V2_MEMORY" else "memory.limit_in_bytes")
    with open(os.path.join(memory_target, limit_name)) as stream:
        assert stream.read() == str(3 * manager.MEBIBYTE)


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

    real_mkdir = manager._mkdir
    real_isdir = os.path.isdir

    def mkdir(path):
        real_mkdir(path)
        if path == target:
            for name, value in (("cgroup.procs", ""), ("cpuset.cpus", ""), ("cpuset.mems", "0")):
                with open(os.path.join(path, name), "w") as stream:
                    stream.write(value)

    monkeypatch.setattr(manager, "_mkdir", mkdir)
    monkeypatch.setattr(manager, "CGROUP_SYSTEMD_V1_ROOT", systemd_root)
    monkeypatch.setattr(resource_control.os.path, "isdir", lambda path: path == "/proc/987654" or real_isdir(path))

    resolved = manager._resolve_systemd_fallback(
        root,
        "CGROUP_V2_CPUSET",
        "MANAGEMENT",
        handle("zstack.service"),
        "/system.slice/zstack.service",
        False,
        target)

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

    real_mkdir = manager._mkdir
    real_write = manager._write
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

    monkeypatch.setattr(manager, "_mkdir", mkdir)
    monkeypatch.setattr(manager, "_write", write)
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V1_CPUSET", cpuset_root))
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V1_MEMORY", memory_root))
    monkeypatch.setattr(manager, "_resolve", lambda *_args: target)
    monkeypatch.setattr(manager, "_resolve_for_release", lambda *_args: target)
    monkeypatch.setattr(manager, "_apply_to_group", lambda _root, _backend, _target, desired: desired)
    monkeypatch.setattr(manager, "_release_cpu_boundary", lambda *_args: None)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value: value)
    monkeypatch.setattr(manager, "CGROUP_V1_MEMORY_ROOT", memory_root)
    monkeypatch.setattr(resource_control.os.path, "isdir", lambda path: path == "/proc/987654" or real_isdir(path))

    limited = manager.apply("MANAGEMENT", "0-3", [handle("zstack.service")], 3 * manager.MEBIBYTE)
    memory_target = os.path.join(memory_root, os.path.basename(target))

    assert limited["synced"]
    with open(os.path.join(memory_target, "memory.limit_in_bytes")) as stream:
        assert stream.read() == str(3 * manager.MEBIBYTE)
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
