import os
from unittest.mock import Mock

import pytest

from zstacklib.utils import resource_control
from zstacklib.utils.resource_control import ResourceControlError, ResourceControlManager


def handle(value, consumer_key="mn-core:node-1"):
    return {
        "handleType": "SYSTEMD_UNIT",
        "value": value,
        "serviceName": value.rsplit(".service", 1)[0],
        "consumerKey": consumer_key,
        "optional": False,
        "restartable": False,
    }


def owner_handle(value, consumer_key="mn-core:node-1"):
    return {
        "handleType": "OWNER_PID_FILE",
        "value": value,
        "consumerKey": consumer_key,
        "optional": False,
    }


def optional_handle(value, consumer_key="mn-aux:node-1"):
    item = handle(value, consumer_key)
    item["optional"] = True
    return item


def test_release_with_only_optional_handles_is_an_idempotent_success(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(
        manager,
        "_backend",
        lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"),
    )
    monkeypatch.setattr(
        manager,
        "_memory_backend",
        lambda: ("CGROUP_V2_MEMORY", "/sys/fs/cgroup"),
    )
    monkeypatch.setattr(manager, "_resolve", lambda *_args: None)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value, _enabled: value)

    result = manager.apply(
        "MANAGEMENT",
        "0-3",
        [optional_handle("collectd.service")],
        "RELEASE",
        96 * manager.MEBIBYTE,
    )

    assert result["synced"], "释放不存在的可选 Handle 必须保持幂等成功"


def test_role_memory_limit_is_applied_once_at_slice_boundary(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V2_MEMORY", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_validate_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager, "_configure_systemd_slice", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: False)
    monkeypatch.setattr(manager, "_active_slice_target",
                        lambda *_args: "/sys/fs/cgroup/zstack-management.slice")
    monkeypatch.setattr(manager, "_active_controller_slice_target",
                        lambda *_args: "/sys/fs/cgroup/zstack-management.slice")
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")
    apply_memory = Mock(return_value=("CGROUP_V2_MEMORY", 4 * 1024 * 1024 * 1024))
    monkeypatch.setattr(manager, "_apply_memory_target", apply_memory)
    monkeypatch.setattr(manager, "_systemd_properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/zstack-management.slice/%s" % unit,
    })
    monkeypatch.setattr(manager, "_systemd_target",
                        lambda _root, group: "/sys/fs/cgroup%s" % group)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value, _enabled: value)

    result = manager.apply(
        "MANAGEMENT",
        "0-3",
        [handle("zstack.service"), handle("mariadb.service")],
        "APPLY",
        4 * 1024 * 1024 * 1024,
        "zstack-management.slice",
    )

    apply_memory.assert_called_once_with(
        "CGROUP_V2_MEMORY", "/sys/fs/cgroup",
        "/sys/fs/cgroup/zstack-management.slice",
        4 * 1024 * 1024 * 1024, False, None)
    assert result["synced"], "Role Slice 的 CPU 和内存边界均生效后才能返回 synced"


def test_apply_stages_service_slice_without_restarting_running_service(monkeypatch):
    manager = ResourceControlManager()
    commands = []
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_memory_backend", lambda: ("CGROUP_V2_MEMORY", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "_validate_active_slice_memory", lambda *_args: None)
    monkeypatch.setattr(manager, "_configure_systemd_slice", lambda *_args: True)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: True)
    monkeypatch.setattr(manager, "_systemctl",
                        lambda args, _timeout: commands.append(args) or "")
    monkeypatch.setattr(manager, "_active_slice_target",
                        lambda *_args: "/sys/fs/cgroup/zstack-compute.slice")
    monkeypatch.setattr(manager, "_active_controller_slice_target",
                        lambda *_args: "/sys/fs/cgroup/zstack-compute.slice")
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")
    monkeypatch.setattr(manager, "_apply_memory_target",
                        lambda *_args: ("CGROUP_V2_MEMORY", 2 * 1024 ** 3))
    monkeypatch.setattr(manager, "_systemd_properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": ("/zstack-compute.slice" if unit.endswith(".slice")
                         else "/system.slice/node_exporter.service"),
    })
    monkeypatch.setattr(manager, "_validate_active_slice_memory",
                        lambda *_args: None)
    monkeypatch.setattr(manager, "_systemd_target",
                        lambda _root, group: "/sys/fs/cgroup%s" % group)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value, _enabled: value)

    result = manager.apply(
        "COMPUTE", "0-3", [handle("node_exporter.service")],
        "APPLY", 2 * 1024 ** 3, "zstack-compute.slice")

    assert commands == [["daemon-reload"]]
    assert not result["synced"], "仅写入 drop-in、进程尚未进入 Slice 时不能返回 synced"


def test_legacy_systemd_hybrid_keeps_cpu_fallback_and_stages_role_memory(
        monkeypatch):
    manager = ResourceControlManager()
    service = handle("node_exporter.service")
    cpu_fallback = Mock(return_value={
        "state": "READY", "cpuSet": "0-3", "memory": None})
    monkeypatch.setattr(manager, "_backend",
                        lambda: ("CGROUP_V2_CPUSET", "/cgroup2"))
    monkeypatch.setattr(manager, "_memory_backend",
                        lambda: ("CGROUP_V1_MEMORY", "/memory"))
    monkeypatch.setattr(manager, "_configure_systemd_slice", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: False)
    monkeypatch.setattr(
        manager, "_active_slice_target",
        lambda *_args: (_ for _ in ()).throw(
            ResourceControlError("SYSTEMD_CONTROL_GROUP_NOT_FOUND")))
    monkeypatch.setattr(manager, "_apply_non_systemd_handle", cpu_fallback)
    monkeypatch.setattr(manager, "_active_controller_slice_target",
                        lambda *_args: "/memory/zstack-compute.slice")
    monkeypatch.setattr(manager, "_apply_memory_target",
                        lambda *_args: ("CGROUP_V1_MEMORY", 2 * 1024 ** 3))
    monkeypatch.setattr(manager, "_control_group_in_target",
                        lambda *_args: False)
    monkeypatch.setattr(manager, "_systemd_properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": ("/zstack-compute.slice" if unit.endswith(".slice")
                         else "/system.slice/node_exporter.service"),
    })
    monkeypatch.setattr(manager, "_validate_active_slice_memory",
                        lambda *_args: None)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value, _enabled: value)

    result = manager.apply(
        "COMPUTE", "0-3", [service], "APPLY",
        2 * 1024 ** 3, "zstack-compute.slice")

    assert cpu_fallback.call_count == 1
    assert not result["synced"], "遗留 systemd 服务重启前必须保持 Unsynced"


def test_legacy_systemd_release_preserves_cpu_fallback_failure(monkeypatch):
    manager = ResourceControlManager()
    service = handle("node_exporter.service")
    monkeypatch.setattr(manager, "_configure_systemd_slice", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: False)
    monkeypatch.setattr(
        manager, "_active_slice_target",
        lambda *_args: (_ for _ in ()).throw(
            ResourceControlError("SYSTEMD_CONTROL_GROUP_NOT_FOUND")))
    monkeypatch.setattr(manager, "_apply_non_systemd_handle", lambda *_args: {
        "state": "ERROR", "cpuSet": None, "memory": None})
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/system.slice/node_exporter.service",
    })

    result = manager._apply_systemd_slice(
        "/cpuset", "CGROUP_V1_CPUSET", "COMPUTE",
        "zstack-compute.slice", [service], "", None,
        False, False, None, None)

    assert not result["synced"], "释放失败不能被成功的 HTTP 调用掩盖"


def test_cgroup_v1_systemd_slice_uses_managed_cpuset_and_role_memory_boundary(
        monkeypatch):
    manager = ResourceControlManager()
    service = handle("node_exporter.service")
    cpu_fallback = Mock(return_value={
        "state": "READY", "cpuSet": "0-3", "memory": None})
    apply_memory = Mock(return_value=(
        "CGROUP_V1_MEMORY", 2 * 1024 ** 3))
    monkeypatch.setattr(manager, "_backend",
                        lambda: ("CGROUP_V1_CPUSET", "/cpuset"))
    monkeypatch.setattr(manager, "_memory_backend",
                        lambda: ("CGROUP_V1_MEMORY", "/memory"))
    monkeypatch.setattr(manager, "_configure_systemd_slice", lambda *_args: False)
    monkeypatch.setattr(manager, "_configure_systemd_service", lambda *_args: False)
    monkeypatch.setattr(
        manager, "_active_slice_target",
        lambda *_args: (_ for _ in ()).throw(
            ResourceControlError("SYSTEMD_CONTROL_GROUP_NOT_FOUND")))
    monkeypatch.setattr(manager, "_apply_non_systemd_handle", cpu_fallback)
    monkeypatch.setattr(manager, "_active_controller_slice_target",
                        lambda *_args: "/memory/zstack-compute.slice")
    monkeypatch.setattr(manager, "_apply_memory_target", apply_memory)
    monkeypatch.setattr(manager, "_control_group_in_target",
                        lambda *_args: True)
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": "/zstack-compute.slice/node_exporter.service",
    })
    monkeypatch.setattr(manager, "_validate_active_slice_memory",
                        lambda *_args: None)
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value, _enabled: value)

    result = manager.apply(
        "COMPUTE", "0-3", [service], "APPLY",
        2 * 1024 ** 3, "zstack-compute.slice")

    assert cpu_fallback.call_count == 1
    apply_memory.assert_called_once_with(
        "CGROUP_V1_MEMORY", "/memory",
        "/memory/zstack-compute.slice", 2 * 1024 ** 3, False, None)
    assert result["synced"], "v1 CPU 和内存总体边界都生效后必须返回 synced"


def test_restart_fully_stops_units_before_start_so_new_slice_is_applied(monkeypatch):
    manager = ResourceControlManager()
    node_exporter = handle("node_exporter.service")
    prometheus = handle("prometheus.service")
    node_exporter["restartable"] = True
    prometheus["restartable"] = True
    commands = []
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded", "ActiveState": "active"})
    monkeypatch.setattr(manager, "_systemctl",
                        lambda args, _timeout: commands.append(args) or "")

    manager.restart([node_exporter, prometheus])

    assert commands == [
        ["stop", "node_exporter.service"],
        ["start", "node_exporter.service"],
        ["stop", "prometheus.service"],
        ["start", "prometheus.service"],
    ]


def test_restart_recovers_stopped_unit_after_first_start_failure(monkeypatch):
    manager = ResourceControlManager()
    service = handle("node_exporter.service")
    service["restartable"] = True
    commands = []

    def systemctl(args, _timeout):
        commands.append(args)
        if args == ["start", "node_exporter.service"] \
                and commands.count(args) == 1:
            raise ResourceControlError("START_FAILED")
        return ""

    monkeypatch.setattr(manager, "_systemctl", systemctl)
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded", "ActiveState": "active"})

    with pytest.raises(ResourceControlError) as error:
        manager.restart([service])

    assert commands == [
        ["stop", "node_exporter.service"],
        ["start", "node_exporter.service"],
        ["start", "node_exporter.service"],
    ]
    assert str(error.value) == (
        "SYSTEMD_UNIT_RESTART_FAILED:node_exporter.service:START_FAILED")


def test_restart_reports_unit_when_recovery_stays_inactive(monkeypatch):
    manager = ResourceControlManager()
    service = handle("node_exporter.service")
    service["restartable"] = True
    commands = []
    states = iter(["active", "inactive", "inactive"])
    monkeypatch.setattr(
        manager, "_systemctl",
        lambda args, _timeout: commands.append(args) or "")
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded", "ActiveState": next(states)})

    with pytest.raises(ResourceControlError) as error:
        manager.restart([service])

    assert commands == [
        ["stop", "node_exporter.service"],
        ["start", "node_exporter.service"],
        ["start", "node_exporter.service"],
    ]
    assert str(error.value) == (
        "SYSTEMD_UNIT_RESTART_FAILED:node_exporter.service:"
        "SYSTEMD_UNIT_NOT_ACTIVE:RECOVERY_FAILED:SYSTEMD_UNIT_NOT_ACTIVE")


def test_systemctl_start_failure_is_a_resource_control_error(monkeypatch):
    manager = ResourceControlManager()

    def fail_to_start(*_args, **_kwargs):
        raise OSError("systemctl is unavailable")

    monkeypatch.setattr(resource_control.subprocess, "Popen", fail_to_start)

    with pytest.raises(ResourceControlError) as error:
        manager._systemctl(["show", "zstack.service"], 5)

    assert str(error.value) == (
        "SYSTEMD_QUERY_FAILED:systemctl is unavailable")


def test_release_accepts_omitted_cpu_set():
    manager = ResourceControlManager()

    assert manager.validate_cpu_set(None, False) == ""

    with pytest.raises(ResourceControlError) as error:
        manager.validate_cpu_set(None, True)
    assert str(error.value) == "CPUSET_EMPTY"


def test_inspect_reports_effective_cpu_memory_and_parent_memory_limit(
        tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(
        root, "zstack-compute.slice", "node_exporter.service")
    os.makedirs(target)
    for path, value in (
            (os.path.join(root, "memory.max"), "max"),
            (os.path.join(root, "zstack-compute.slice", "memory.max"),
             str(2 * 1024 ** 3)),
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


def test_inspect_systemd_slices_reports_existing_cgroup_facts(
        tmp_path, monkeypatch):
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
    monkeypatch.setattr(
        manager, "_memory_backend", lambda: ("CGROUP_V2_MEMORY", root))
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


def test_inspect_reports_restart_required_until_service_enters_role_slice(
        tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    role = os.path.join(root, "zstack.slice", "zstack-compute.slice")
    old_target = os.path.join(root, "system.slice", "node_exporter.service")
    ready_target = os.path.join(role, "node_exporter.service")
    for target in (role, old_target, ready_target):
        os.makedirs(target)
        with open(os.path.join(target, "cpuset.cpus.effective"), "w") as stream:
            stream.write("1-4")
    drop_in = str(tmp_path / "units" / "node_exporter.service.d" /
                  manager.SYSTEMD_DROP_IN)
    os.makedirs(os.path.dirname(drop_in))
    with open(drop_in, "w") as stream:
        stream.write("[Service]\nSlice=zstack-compute.slice\n")
    current = {"group": "/system.slice/node_exporter.service"}
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", root))
    monkeypatch.setattr(manager, "_v2_roots", lambda: [root])
    monkeypatch.setattr(
        manager, "_memory_backend",
        lambda: (_ for _ in ()).throw(
            ResourceControlError("MEMORY_CONTROLLER_UNAVAILABLE")))
    monkeypatch.setattr(manager, "_drop_in_path", lambda _unit: drop_in)
    monkeypatch.setattr(manager, "_systemd_properties", lambda unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": ("/zstack.slice/zstack-compute.slice"
                         if unit == "zstack-compute.slice"
                         else current["group"]),
    })

    pending = manager.inspect(
        "COMPUTE", [handle("node_exporter.service")])[0]
    assert pending["restartRequired"] is True, (
        "已写入 Role Slice 配置但仍运行在旧 cgroup 的服务必须提示重启: "
        "expected=True actual=%s" % pending.get("restartRequired"))

    current["group"] = (
        "/zstack.slice/zstack-compute.slice/node_exporter.service")
    ready = manager.inspect(
        "COMPUTE", [handle("node_exporter.service")])[0]
    assert ready["restartRequired"] is False, (
        "服务进入目标 Role Slice 后必须清除重启提示: "
        "expected=False actual=%s" % ready.get("restartRequired"))


def test_inspect_reports_cpu_inherited_from_role_slice(
        tmp_path, monkeypatch):
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

    usage = manager.inspect(
        "COMPUTE", [handle("zstack-kvmagent.service")])[0]

    assert usage["state"] == "RUNNING"
    assert usage["cpuSet"] == "2-5", (
        "service cgroup 未启用 cpuset controller 时必须展示 Role Slice 的继承 CPU 范围")
    assert usage["cpuTime"] == 123000
    assert usage["memory"] == 96 * 1024 ** 2


def test_cgroup_v1_inspect_uses_main_pid_without_reporting_root_cpu_time(
        tmp_path, monkeypatch):
    manager = ResourceControlManager()
    cpu_root = str(tmp_path / "cpuset")
    memory_root = str(tmp_path / "memory")
    memory_target = os.path.join(
        memory_root, "zstack.slice", "zstack-compute.slice",
        "node_exporter.service")
    os.makedirs(cpu_root)
    os.makedirs(memory_target)
    for path, value in (
            (os.path.join(cpu_root, "cpuset.cpus"), "0-5"),
            (os.path.join(memory_root, "memory.limit_in_bytes"),
             "9223372036854771712"),
            (os.path.join(memory_target, "memory.limit_in_bytes"),
             str(2 * 1024 ** 3)),
            (os.path.join(memory_target, "memory.usage_in_bytes"),
             str(96 * 1024 ** 2))):
        with open(path, "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager, "_backend",
                        lambda: ("CGROUP_V1_CPUSET", cpu_root))
    monkeypatch.setattr(manager, "_memory_backend",
                        lambda: ("CGROUP_V1_MEMORY", memory_root))
    monkeypatch.setattr(manager, "_v2_roots", lambda: [])
    monkeypatch.setattr(manager, "CGROUP_V1_CPUACCT_ROOTS", ())
    monkeypatch.setattr(
        manager, "_drop_in_path",
        lambda _unit: str(tmp_path / "missing-drop-in"))
    monkeypatch.setattr(manager, "_process_group",
                        lambda _root, _backend, _pid: cpu_root)
    monkeypatch.setattr(manager, "_systemd_properties", lambda _unit: {
        "LoadState": "loaded",
        "ActiveState": "active",
        "ControlGroup": ("/zstack.slice/zstack-compute.slice/"
                         "node_exporter.service"),
        "MainPID": "1234",
    })

    usage = manager.inspect(
        "COMPUTE", [handle("node_exporter.service")])[0]

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


def test_hybrid_inspect_reads_each_controller_from_its_own_hierarchy(
        tmp_path, monkeypatch):
    manager = ResourceControlManager()
    cpu_root = str(tmp_path / "cgroup2")
    memory_root = str(tmp_path / "memory")
    cpuacct_root = str(tmp_path / "cpuacct")
    relative = os.path.join(
        "zstack-compute.slice", "node_exporter.service")
    cpu_target = os.path.join(cpu_root, relative)
    memory_target = os.path.join(memory_root, relative)
    cpuacct_target = os.path.join(cpuacct_root, relative)
    for target in (cpu_target, memory_target, cpuacct_target):
        os.makedirs(target)
    for path, value in (
            (os.path.join(cpu_target, "cpuset.cpus.effective"), "4-7"),
            (os.path.join(memory_root, "memory.limit_in_bytes"),
             "9223372036854771712"),
            (os.path.join(memory_target, "memory.limit_in_bytes"),
             str(2 * 1024 ** 3)),
            (os.path.join(memory_target, "memory.usage_in_bytes"),
             str(96 * 1024 ** 2)),
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

    usage = manager.inspect(
        "COMPUTE", [handle("node_exporter.service")])[0]

    assert usage["cpuSet"] == "4-7"
    assert usage["cpuTime"] == 123000
    assert usage["memory"] == 96 * 1024 ** 2
    assert usage["memoryLimit"] == 2 * 1024 ** 3


def test_hybrid_slice_drop_in_uses_independent_cpu_and_memory_backends(
        tmp_path, monkeypatch):
    manager = ResourceControlManager()
    path = str(tmp_path / "role.conf")
    monkeypatch.setattr(manager, "_drop_in_path", lambda _unit: path)

    manager._configure_systemd_slice(
        "CGROUP_V2_CPUSET", "CGROUP_V1_MEMORY",
        "zstack-compute.slice", "0-3", 2 * 1024 ** 3, True, True)
    with open(path) as stream:
        v2_cpu_v1_memory = stream.read()
    assert "AllowedCPUs=0-3" in v2_cpu_v1_memory
    assert "MemoryLimit=%s" % (2 * 1024 ** 3) in v2_cpu_v1_memory
    assert "MemoryMax=" not in v2_cpu_v1_memory

    manager._configure_systemd_slice(
        "CGROUP_V1_CPUSET", "CGROUP_V2_MEMORY",
        "zstack-compute.slice", "0-3", 2 * 1024 ** 3, True, True)
    with open(path) as stream:
        v1_cpu_v2_memory = stream.read()
    assert "AllowedCPUs=" not in v1_cpu_v2_memory
    assert "MemoryMax=%s" % (2 * 1024 ** 3) in v1_cpu_v2_memory
    assert "MemoryLimit=" not in v1_cpu_v2_memory


def test_cpuset_and_memory_backends_are_detected_independently(
        tmp_path, monkeypatch):
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
    assert manager._memory_backend() == (
        "CGROUP_V1_MEMORY", v1_memory_root)

    with open(os.path.join(v2_root, "cgroup.controllers"), "w") as stream:
        stream.write("memory io")

    assert manager._backend() == ("CGROUP_V1_CPUSET", v1_cpuset_root)
    assert manager._memory_backend() == ("CGROUP_V2_MEMORY", v2_root)


def test_missing_memory_controller_does_not_erase_staged_memory_limit(
        tmp_path, monkeypatch):
    manager = ResourceControlManager()
    path = str(tmp_path / "role.conf")
    with open(path, "w") as stream:
        stream.write("[Slice]\nAllowedCPUs=0-3\nMemoryLimit=2147483648\n")
    monkeypatch.setattr(manager, "_drop_in_path", lambda _unit: path)

    manager._configure_systemd_slice(
        "CGROUP_V2_CPUSET", None, "zstack-compute.slice",
        "4-7", 4 * 1024 ** 3, True, True)

    with open(path) as stream:
        content = stream.read()
    assert "AllowedCPUs=4-7" in content
    assert "MemoryLimit=2147483648" in content


def test_handle_failure_keeps_assignment_unsatisfied(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", "/sys/fs/cgroup"))
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value, _enabled: value)

    def resolve(_root, _backend, _role, item, _enabled):
        if item["value"] == "missing.service":
            raise ResourceControlError("SYSTEMD_UNIT_NOT_FOUND")
        return "/sys/fs/cgroup/%s" % item["value"]

    monkeypatch.setattr(manager, "_resolve", resolve)
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")

    result = manager.apply(
        "MANAGEMENT",
        "0-3",
        [handle("zstack.service"), handle("missing.service")],
        "APPLY",
        None,
    )

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

    backend, actual = manager._apply_memory_limit(
        root, target, 2 * manager.MEBIBYTE,
        "CGROUP_V2_MEMORY", root)

    assert backend == "CGROUP_V2_MEMORY"
    assert actual == 2 * manager.MEBIBYTE
    with open(memory_max) as stream:
        assert stream.read() == str(2 * manager.MEBIBYTE)

    backend, actual = manager._apply_memory_limit(
        root, target, 0, "CGROUP_V2_MEMORY", root)

    assert backend == "CGROUP_V2_MEMORY"
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
        manager._apply_memory_limit(
            root, target, manager.MEBIBYTE,
            "CGROUP_V2_MEMORY", root)

    assert str(error.value) == "MEMORY_LIMIT_BELOW_CURRENT_USAGE"
    with open(memory_max) as stream:
        assert stream.read() == "max", (
            "低于当前用量的上限必须在写 memory.max 前拒绝，不能 OOM 杀死 Consumer")


def test_apply_memory_limit_v2_accounts_for_resident_memory_after_process_move(
        tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstack-role-COMPUTE-owner-host-agent")
    os.makedirs(target)
    for name, value in (
            ("memory.max", "max"),
            ("memory.current", "4096"),
            ("cgroup.procs", "1234\n")):
        with open(os.path.join(target, name), "w") as stream:
            stream.write(value)
    monkeypatch.setattr(
        manager, "_resident_memory_usage",
        lambda _process_file: 200 * manager.MEBIBYTE,
        raising=False)

    with pytest.raises(ResourceControlError) as error:
        manager._apply_memory_limit(
            root, target, manager.MEBIBYTE,
            "CGROUP_V2_MEMORY", root)

    assert str(error.value) == "MEMORY_LIMIT_BELOW_CURRENT_USAGE"
    with open(os.path.join(target, "memory.max")) as stream:
        assert stream.read() == "max", (
            "迁移不会同步迁移已有 memory charge，必须用 PID RSS 阻止自杀式限额")


def test_resident_memory_usage_sums_process_rss(monkeypatch):
    manager = ResourceControlManager()
    monkeypatch.setattr(manager, "_process_ids", lambda _path: ["11", "12"])
    real_isfile = resource_control.os.path.isfile
    expected_files = {
        "/sys/fs/cgroup/test/cgroup.procs",
        "/proc/11/status",
        "/proc/12/status",
    }
    monkeypatch.setattr(
        resource_control.os.path,
        "isfile",
        lambda path: path in expected_files or real_isfile(path))
    monkeypatch.setattr(
        manager, "_read",
        lambda path: "Name:\ttest\nVmRSS:\t%s kB\n" % (
            "1024" if path.endswith("/11/status") else "2048"))

    assert manager._resident_memory_usage("/sys/fs/cgroup/test/cgroup.procs") == (
        3 * manager.MEBIBYTE)


def test_apply_memory_limit_v1_rejects_limit_below_current_usage(
        tmp_path, monkeypatch):
    manager = ResourceControlManager()
    cpuset_root = str(tmp_path / "cpuset")
    memory_root = str(tmp_path / "memory")
    target = os.path.join(cpuset_root, "zstack-role-COMPUTE-owner-host-agent")
    memory_target = os.path.join(
        memory_root, "zstack-role-COMPUTE-owner-host-agent")
    os.makedirs(target)
    os.makedirs(memory_target)
    for path, value in (
            (os.path.join(target, "cgroup.procs"), ""),
            (os.path.join(memory_root, "memory.limit_in_bytes"),
             "9223372036854771712"),
            (os.path.join(memory_target, "memory.limit_in_bytes"),
             "9223372036854771712"),
            (os.path.join(memory_target, "memory.usage_in_bytes"),
             str(2 * manager.MEBIBYTE)),
            (os.path.join(memory_target, "cgroup.procs"), "")):
        with open(path, "w") as stream:
            stream.write(value)
    monkeypatch.setattr(manager, "CGROUP_V1_MEMORY_ROOT", memory_root)

    with pytest.raises(ResourceControlError) as error:
        manager._apply_memory_limit(
            cpuset_root, target, manager.MEBIBYTE,
            "CGROUP_V1_MEMORY", memory_root)

    assert str(error.value) == "MEMORY_LIMIT_BELOW_CURRENT_USAGE"
    with open(os.path.join(memory_target, "memory.limit_in_bytes")) as stream:
        assert stream.read() == "9223372036854771712", (
            "低于当前用量的 v1 上限必须在写入前拒绝")


def test_apply_reports_memory_controller_unavailable_per_handle(tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(root, "zstack.service")
    os.makedirs(target)
    monkeypatch.setattr(manager, "_backend", lambda: ("CGROUP_V2_CPUSET", root))
    monkeypatch.setattr(
        manager,
        "_memory_backend",
        lambda: (_ for _ in ()).throw(
            ResourceControlError("MEMORY_CONTROLLER_UNAVAILABLE")))
    monkeypatch.setattr(manager, "_resolve", lambda *_args: target)
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value, _enabled: value)

    result = manager.apply("MANAGEMENT", "0-3", [handle("zstack.service")], "APPLY",
                           manager.MEBIBYTE)

    assert not result["synced"], "请求内存限制时缺少内存控制器必须返回未同步"


@pytest.mark.parametrize(
    "cpu_backend,memory_backend",
    [
        ("CGROUP_V2_CPUSET", "CGROUP_V1_MEMORY"),
        ("CGROUP_V1_CPUSET", "CGROUP_V2_MEMORY"),
    ],
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
                (os.path.join(memory_root, "memory.limit_in_bytes"),
                 "9223372036854771712"),
                (os.path.join(memory_target, "memory.limit_in_bytes"),
                 "9223372036854771712"),
                (os.path.join(memory_target, "memory.usage_in_bytes"), "0")):
            with open(path, "w") as stream:
                stream.write(value)
    monkeypatch.setattr(manager, "_backend", lambda: (cpu_backend, cpu_root))
    monkeypatch.setattr(
        manager, "_memory_backend",
        lambda: (memory_backend, memory_root))
    monkeypatch.setattr(manager, "_resolve", lambda *_args: cpu_target)
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value, _enabled: value)

    result = manager.apply(
        "MANAGEMENT", "0-3", [handle("zstack.service")],
        "APPLY", 3 * manager.MEBIBYTE)

    assert result["synced"], "hybrid 环境中独立的 CPU 和内存控制器都生效后必须同步"
    limit_name = ("memory.max" if memory_backend == "CGROUP_V2_MEMORY"
                  else "memory.limit_in_bytes")
    with open(os.path.join(memory_target, limit_name)) as stream:
        assert stream.read() == str(3 * manager.MEBIBYTE)


def test_hybrid_v2_cpuset_moves_systemd_members_from_v1_hierarchy(
        tmp_path, monkeypatch):
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
            for name, value in (
                    ("cgroup.procs", ""),
                    ("cpuset.cpus", ""),
                    ("cpuset.mems", "0")):
                with open(os.path.join(path, name), "w") as stream:
                    stream.write(value)

    monkeypatch.setattr(manager, "_mkdir", mkdir)
    monkeypatch.setattr(manager, "CGROUP_SYSTEMD_V1_ROOT", systemd_root)
    monkeypatch.setattr(
        resource_control.os.path, "isdir",
        lambda path: path == "/proc/987654" or real_isdir(path))

    resolved = manager._resolve_systemd_fallback(
        root,
        "CGROUP_V2_CPUSET",
        "MANAGEMENT",
        handle("zstack.service"),
        "/system.slice/zstack.service",
        False,
        True,
        target)

    assert resolved == target
    with open(os.path.join(target, "cgroup.procs")) as stream:
        assert stream.read() == "987654"


def test_pid_file_consumer_is_moved_to_a_cloud_managed_group(
        tmp_path, monkeypatch):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    os.makedirs(root)
    pid_file = str(tmp_path / "management.pid")
    with open(pid_file, "w") as stream:
        stream.write(str(os.getpid()))
    os.chmod(pid_file, 0o600)
    target = os.path.join(
        root, "zstack-role-MANAGEMENT-owner-mn-core-node-1")

    real_mkdir = manager._mkdir

    def mkdir(path):
        real_mkdir(path)
        if path == target:
            with open(os.path.join(path, "cgroup.procs"), "w") as stream:
                stream.write("")

    monkeypatch.setattr(manager, "_mkdir", mkdir)
    monkeypatch.setattr(manager, "_enable_v2_path", lambda *_args: None)
    monkeypatch.setattr(manager, "_initialize_mems", lambda *_args: None)
    monkeypatch.setattr(manager, "_initialize_cpus", lambda *_args: None)

    resolved = manager._resolve_pid_file(
        root,
        "CGROUP_V2_CPUSET",
        "MANAGEMENT",
        owner_handle(pid_file),
        True)

    assert resolved == target, (
        "PID file 只负责定位进程，Cloud 必须把进程移入自己管理的 cgroup，"
        "不能改写进程原来的 systemd/container cgroup: actual=%s" % resolved)
    with open(os.path.join(target, "cgroup.procs")) as stream:
        assert stream.read() == str(os.getpid())


def test_root_pid_file_cannot_use_command_token_to_bypass_write_permissions(
        tmp_path, monkeypatch):
    manager = ResourceControlManager()
    pid = os.getpid()
    pid_file = str(tmp_path / "management.pid")
    with open(pid_file, "w") as stream:
        stream.write(str(pid))
    command_token = manager._read(
        "/proc/%s/cmdline" % pid).replace("\x00", " ").split()[0]
    item = owner_handle(pid_file)
    item["expectedCommandToken"] = command_token

    monkeypatch.setattr(os, "lstat", lambda _path: Mock(
        st_mode=resource_control.stat.S_IFREG | 0o620,
        st_uid=0,
        st_mtime=10 ** 20))
    monkeypatch.setattr(os, "stat", lambda _path: Mock(
        st_mode=resource_control.stat.S_IFDIR | 0o555,
        st_uid=0))

    with pytest.raises(
            ResourceControlError,
            match="PID_FILE_PERMISSION_INVALID"):
        manager._pid_from_handle(item)


def test_pid_file_release_uses_existing_managed_group_without_live_pid_file(
        tmp_path):
    manager = ResourceControlManager()
    root = str(tmp_path / "cgroup2")
    target = os.path.join(
        root, "zstack-role-MANAGEMENT-owner-mn-core-node-1")
    os.makedirs(target)

    resolved = manager._resolve_pid_file(
        root,
        "CGROUP_V2_CPUSET",
        "MANAGEMENT",
        owner_handle(str(tmp_path / "missing.pid")),
        False)

    assert resolved == target, (
        "释放必须优先清理已创建的 Cloud cgroup，不能因 PID 文件先消失而跳过")


def test_apply_memory_limit_v1_managed_group_moves_processes_and_releases(
        tmp_path, monkeypatch):
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
            for name in ("memory.limit_in_bytes", "memory.usage_in_bytes",
                         "cgroup.procs"):
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
    monkeypatch.setattr(manager, "_apply_to_group", lambda *_args: "0-3")
    monkeypatch.setattr(manager, "validate_cpu_set", lambda value, _enabled: value)
    monkeypatch.setattr(manager, "CGROUP_V1_MEMORY_ROOT", memory_root)
    monkeypatch.setattr(
        resource_control.os.path, "isdir",
        lambda path: path == "/proc/987654" or real_isdir(path))

    limited = manager.apply("MANAGEMENT", "0-3", [handle("zstack.service")],
                            "APPLY", 3 * manager.MEBIBYTE)
    memory_target = os.path.join(memory_root, os.path.basename(target))

    assert limited["synced"]
    with open(os.path.join(memory_target, "memory.limit_in_bytes")) as stream:
        assert stream.read() == str(3 * manager.MEBIBYTE)
    with open(os.path.join(target, "cgroup.procs")) as stream:
        assert stream.read() == ""
    with open(os.path.join(memory_target, "cgroup.procs")) as stream:
        assert stream.read() == "987654\n"

    released = manager.apply("MANAGEMENT", "0-3", [handle("zstack.service")],
                             "RELEASE", 3 * manager.MEBIBYTE)

    assert released["synced"]
    with open(os.path.join(memory_target, "memory.limit_in_bytes")) as stream:
        assert stream.read() == "9223372036854771712"
    with open(os.path.join(memory_target, "cgroup.procs")) as stream:
        assert stream.read() == ""
    with open(os.path.join(memory_root, "cgroup.procs")) as stream:
        assert stream.read() == "987654\n"
