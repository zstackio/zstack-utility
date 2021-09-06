'''

@author: zaifeng.wang
'''

import sys
import unittest
from kvmagent import kvmagent
from zstacklib.utils import xmlhook

#------------------------------------------------

create_usb_device_INPUT = """
<domain>
    <devices>
        <disk>somevalue</disk>
    </devices>
</domain>
"""

create_usb_device_EXPECT_OUTPUT = """
<domain>
    <devices>
        <disk>somevalue</disk>
        <hostdev mode="subsystem" type="usb">
            <source>
                <vendor id="0x1234"/>
                <product id="0xbeef"/>
            </source>
        </hostdev>
    </devices>
</domain>
"""

create_usb_device_HOOK_SCRIPT = """
def create_usb_device(root, hook):
    for devices in root.findall("devices"):
        # create <hostdev mode='subsystem' type='usb'> from <devices>
        hostdev = hook.create_element("hostdev")
        hook.add_attribute(hostdev, "mode", "subsystem")
        hook.add_attribute(hostdev, "type", "usb")
        hook.add_element_to_parent(hostdev, devices)

        # create <source> from <hostdev mode='subsystem' type='usb'>
        source = hook.create_element("source")
        hook.add_element_to_parent(source, hostdev)

        # create <vendor id='0x1234'> from <source>
        vendor = hook.create_element("vendor")
        hook.add_attribute(vendor, "id", "0x1234")
        hook.add_element_to_parent(vendor, source)

        # create <product id='0xbeef'> from <source>
        product = hook.create_element("product")
        hook.add_attribute(product, "id", "0xbeef")
        hook.add_element_to_parent(product, source)

create_usb_device(root, hook)
"""

#------------------------------------------------

remove_usb_device_if_has_cdrom_INPUT = """
<domain>
    <devices>
        <disk device="cdrom" type="file">
            <driver name="qemu" type="raw"/>
            <target bus="ide" dev="hdc"/>
        </disk>
        <hostdev mode="subsystem" type="usb">
            <source>
                <vendor id="0x1234"/>
                <product id="0xbeef"/>
            </source>
        </hostdev>
    </devices>
</domain>
"""

remove_usb_device_if_has_cdrom_EXPECT_OUTPUT = """
<domain>
    <devices>
        <disk device="cdrom" type="file">
            <driver name="qemu" type="raw"/>
            <target bus="ide" dev="hdc"/>
        </disk>
    </devices>
</domain>
"""

remove_usb_device_if_has_cdrom_HOOK_SCRIPT = """
def remove_usb_device_if_has_cdrom(root, hook):
    def has_cdrom(root):
        for devices in root.findall("devices"):
            for disks in devices.findall("disk"):
                disk_device = hook.get_value_of_attribute(disks, "device")
                if disk_device == "cdrom":
                    return True
        return False

    def remove_usb_device(root):
        for devices in root.findall("devices"):
            for hostdev in devices.findall("hostdev"):
                hostdev_type = hook.get_value_of_attribute(hostdev, "type")
                if hostdev_type == "usb":
                    hook.delete_element_from_parent(hostdev, devices)
    
    if has_cdrom(root) is True:
        remove_usb_device(root)

remove_usb_device_if_has_cdrom(root, hook)
"""

#------------------------------------------------

config_cpu_mode_INPUT = """
<domain>
    <cpu mode='custom' match='exact' check='full'>
        <topology sockets='1' cores='1' threads='1'/>
        <feature policy='require' name='hypervisor'/>
    </cpu>
</domain>
"""

config_cpu_mode_EXPECT_OUTPUT = """
<domain>
    <cpu mode='host-model' match='exact' check='full'>
        <topology sockets='1' cores='1' threads='1'/>
        <feature policy='require' name='hypervisor'/>
    </cpu>
</domain>
"""

config_cpu_mode_HOOK_SCRIPT = """
def config_cpu_mode(root, cpu_mode, hook):
    for cpu in root.findall("cpu"):
        hook.modify_value_of_attribute(cpu, "mode", cpu_mode)

config_cpu_mode(root, "host-model", hook)
"""

#------------------------------------------------

config_numatune_INPUT = """
<domain>
    <vcpu placement='static' cpuset="1-4,^3,6" current="1">2</vcpu>
    <cputune>
        <vcpupin vcpu="0" cpuset="1-4,^2"/>
        <emulatorpin cpuset="1-3"/>
    </cputune>
</domain>
"""

config_numatune_EXPECT_OUTPUT = """
<domain>
    <vcpu placement='static' cpuset="1-4,^3,6" current="1">2</vcpu>
    <cputune>
        <vcpupin vcpu="0" cpuset="1-4,^2"/>
        <emulatorpin cpuset="1-3"/>
    </cputune>
    <numatune>
        <memory mode="strict" nodeset="1-4,^3"/>
        <memnode cellid="0" mode="strict" nodeset="1"/>
        <memnode cellid="2" mode="preferred" nodeset="2"/>
    </numatune>
</domain>
"""

config_numatune_HOOK_SCRIPT = """
def config_numatune(root, need_sequence_after_cputune, hook):
    def create_memory_from_numatune(numatune, mode, nodeset):
        memory = hook.create_element("memory")
        hook.add_attribute(memory, "mode", mode)
        hook.add_attribute(memory, "nodeset", nodeset)
        hook.add_element_to_parent(memory, numatune)

    def create_memnode_from_numatune(memnode, cellid, mode, nodeset):
        memnode = hook.create_element("memnode")
        hook.add_attribute(memnode, "cellid", cellid)
        hook.add_attribute(memnode, "mode", mode)
        hook.add_attribute(memnode, "nodeset", nodeset)
        hook.add_element_to_parent(memnode, numatune)

    # create <numatune> from root
    numatune = hook.create_element("numatune")
    if need_sequence_after_cputune is True:
        index_of_cputune = hook.get_index_of_element(root, "cputune")
        hook.add_element_to_parent(numatune, root, index_of_cputune)
    else:
        hook.add_element_to_parent(numatune, root)

    # create <memory> & <memnode> from <numatune>
    create_memory_from_numatune(numatune, "strict", "1-4,^3")
    create_memnode_from_numatune(numatune, "0", "strict", "1")
    create_memnode_from_numatune(numatune, "2", "preferred", "2")

config_numatune(root, True, hook)
"""

#------------------------------------------------

config_virtio_disk_queue_number_INPUT = """
<domain>
    <devices>
        <disk type="file" device="disk">
            <driver name='qemu' type='qcow2'/>
            <target bus="virtio" dev="vda"/>
        </disk>
        <disk type="file" device="cdrom">
            <target bus="ide" dev="hdc"/>
            <driver name='qemu' type='raw'/>
        </disk>
        <disk type="file" device="disk">
            <driver name='qemu' type='qcow2'/>
            <target bus="ide" dev="vdb"/>
        </disk>
        <disk type="file" device="disk">
            <driver name='qemu' type='qcow2'/>
            <target bus="virtio" dev="vdc"/>
        </disk>
    </devices>
</domain>
"""

config_virtio_disk_queue_number_EXPECT_OUTPUT = """
<domain>
    <devices>
        <disk type="file" device="disk">
            <driver name='qemu' type='qcow2' queues="4"/>
            <target bus="virtio" dev="vda"/>
        </disk>
        <disk type="file" device="cdrom">
            <target bus="ide" dev="hdc"/>
            <driver name='qemu' type='raw'/>
        </disk>
        <disk type="file" device="disk">
            <driver name='qemu' type='qcow2'/>
            <target bus="ide" dev="vdb"/>
        </disk>
        <disk type="file" device="disk">
            <driver name='qemu' type='qcow2' queues="4"/>
            <target bus="virtio" dev="vdc"/>
        </disk>
    </devices>
</domain>
"""

config_virtio_disk_queue_number_HOOK_SCRIPT = """
def config_virtio_disk_queue_number(root, queue_number, hook):
    def config_disk_queue_number(disk):
        for driver in disk.findall("driver"):
            hook.set_value_of_attribute(driver, "queues", str(queue_number))
    
    # find virtio_disks from all_disks
    for devices in root.findall("devices"):
        for disks in devices.findall("disk"):
            for target in disks.findall("target"):
                bus = hook.get_value_of_attribute(target, "bus")
                if bus == "virtio":
                    config_disk_queue_number(disks)

config_virtio_disk_queue_number(root, 4, hook)
"""

#------------------------------------------------

print_snapshot_from_data_disk_INPUT = """
<domain>
    <devices>
        <disk type="file" device="disk">
            <driver name='qemu' type='qcow2'/>
            <source file='/zstack_ps/dataVolumes/root_backing_file.qcow2'/>
            <backingStore type='file' index='1'>
                <format type='qcow2'/>
                <source file='/zstack_ps/dataVolumes/root_snapshot_first.qcow2'/>
                <backingStore/>
            </backingStore>
            <boot order='1'/>
        </disk>
        <disk type="file" device="disk">
            <driver name='qemu' type='qcow2'/>
            <source file='/zstack_ps/dataVolumes/data_backing_file.qcow2'/>
            <backingStore type='file' index='1'>
                <format type='qcow2'/>
                <source file='/zstack_ps/dataVolumes/data_snapshot_first.qcow2'/>
                <backingStore type='file' index='2'>
                    <format type='qcow2'/>
                    <source file='/zstack_ps/dataVolumes/data_snapshot_second.qcow2'/>
                    <backingStore type='file' index='3'>
                        <format type='qcow2'/>
                        <source file='/zstack_ps/dataVolumes/data_snapshot_third.qcow2'/>
                        <backingStore/>
                    </backingStore>
                </backingStore>
            </backingStore>
        </disk>
    </devices>
</domain>
"""

print_snapshot_from_data_disk_EXPECT_OUTPUT = """
/zstack_ps/dataVolumes/data_snapshot_first.qcow2
/zstack_ps/dataVolumes/data_snapshot_second.qcow2
/zstack_ps/dataVolumes/data_snapshot_third.qcow2
"""

print_snapshot_from_data_disk_HOOK_SCRIPT = """
def print_snapshot_from_data_disk(root, hook):
    def print_all_snapshots(disk):
        backing_file_ignored = False
        # choose iterator instead of using dom-tree hard code
        for snapshots in disk.iter("source"):
            snapshot = hook.get_value_of_attribute(snapshots, "file")
            if backing_file_ignored is True:
                print(snapshot)
            else:
                backing_file_ignored = True

    # find data_disks from all_disks
    for devices in root.findall("devices"):
        for disks in devices.findall("disk"):
            if hook.found_element(disks, "boot") is False:
                print_all_snapshots(disks)

print_snapshot_from_data_disk(root, hook)
"""

#------------------------------------------------

config_mtu_by_mac_address_INPUT = """
<domain>
    <devices>
        <interface type='default'>
            <mac address='23:1a:d0:4e:3b:1e'/>
            <mtu size='888'/>
        </interface>
        <interface type='bridge'>
            <mac address='fa:f5:12:cf:67:00'/>
            <mtu size='888'/>
        </interface>
    </devices>
</domain>
"""

config_mtu_by_mac_address_EXPECT_OUTPUT = """
<domain>
    <devices>
        <interface type='default'>
            <mac address='23:1a:d0:4e:3b:1e'/>
            <mtu size='888'/>
        </interface>
        <interface type='bridge'>
            <mac address='fa:f5:12:cf:67:00'/>
            <mtu size='1200'/>
        </interface>
    </devices>
</domain>
"""

config_mtu_by_mac_address_HOOK_SCRIPT = """
def config_mtu_by_mac_address(root, hook, mtu_number, mac_address):
    def config_mtu(interface):
        for mtu in interface.findall("mtu"):
            hook.modify_value_of_attribute(mtu, "size", str(mtu_number))

    # find network (interface) card with specific mac_address
    for devices in root.findall("devices"):
        for interface in devices.findall("interface"):
            for mac in interface.findall("mac"):
                address = hook.get_value_of_attribute(mac, "address")
                if address == mac_address:
                    config_mtu(interface)

config_mtu_by_mac_address(root, hook, 1200, "fa:f5:12:cf:67:00")
"""

#------------------------------------------------

config_mac_address_by_mtu_INPUT = """
<domain>
    <devices>
        <interface type='default'>
            <mac address='fa:af:36:ba:c2:00'/>
            <mtu size='1500'/>
        </interface>
        <interface type='bridge'>
            <mac address='fa:88:98:8e:73:01'/>
            <mtu size='8888'/>
        </interface>
    </devices>
</domain>
"""

config_mac_address_by_mtu_EXPECT_OUTPUT = """
<domain>
    <devices>
        <interface type='default'>
            <mac address='fa:af:36:ba:c2:00'/>
            <mtu size='1500'/>
        </interface>
        <interface type='bridge'>
            <mac address='23:1a:d0:4e:3b:1e'/>
            <mtu size='8888'/>
        </interface>
    </devices>
</domain>
"""

config_mac_address_by_mtu_HOOK_SCRIPT = """
def config_mac_address_by_mtu(root, hook, mac_address, expect_mtu_number):
    def config_mac_address(interface):
        for mac in interface.findall("mac"):
            hook.modify_value_of_attribute(mac, "address", mac_address)

    # find network (interface) card with specific mtu
    for devices in root.findall("devices"):
        for interface in devices.findall("interface"):
            for mtu in interface.findall("mtu"):
                mtu_number = hook.get_value_of_attribute(mtu, "size")
                if mtu_number == str(expect_mtu_number):
                    config_mac_address(interface)

config_mac_address_by_mtu(root, hook, "23:1a:d0:4e:3b:1e", 8888)
"""

#------------------------------------------------

config_mac_address_by_bandwidth_INPUT = """
<domain>
    <devices>
        <interface type='default'>
            <mac address='fa:af:36:ba:c2:00'/>
        </interface>
        <interface type='bridge'>
            <mac address='fa:88:98:8e:73:01'/>
            <bandwidth>
                <inbound average='85248'/>
                <outbound average='85248'/>
            </bandwidth>
        </interface>
    </devices>
</domain>
"""

config_mac_address_by_bandwidth_EXPECT_OUTPUT = """
<domain>
    <devices>
        <interface type='default'>
            <mac address='fa:af:36:ba:c2:00'/>
        </interface>
        <interface type='bridge'>
            <mac address='23:1a:d0:4e:3b:1e'/>
            <bandwidth>
                <inbound average='85248'/>
                <outbound average='85248'/>
            </bandwidth>
        </interface>
    </devices>
</domain>
"""

config_mac_address_by_bandwidth_HOOK_SCRIPT = """
def config_mac_address_by_bandwidth(root, hook, mac_address, expect_bandwidth_mbps):
    def config_mac_address(interface):
        for mac in interface.findall("mac"):
            hook.modify_value_of_attribute(mac, "address", mac_address)

    # find network (interface) card with specific bandwidth
    for devices in root.findall("devices"):
        for interface in devices.findall("interface"):
            for bandwidth in interface.findall("bandwidth"):
                inbound = int(hook.get_value_of_attribute_from_parent(bandwidth, "inbound", "average"))/128
                outbound = int(hook.get_value_of_attribute_from_parent(bandwidth, "outbound", "average"))/128
                if inbound == expect_bandwidth_mbps and outbound == expect_bandwidth_mbps:
                    config_mac_address(interface)

config_mac_address_by_bandwidth(root, hook, "23:1a:d0:4e:3b:1e", 666)
"""

#------------------------------------------------

config_disk_serial_number_INPUT = """
<domain>
    <devices>
        <disk type="file" device="disk">
            <serial>a2421660c25845568a3d88b5386d3213</serial>
        </disk>
        <disk type="file" device="disk">
            <serial>85bbdfc098e44110a31922d5bc0ba603</serial>
        </disk>
        <disk type="file" device="disk">
            <serial>1dfdb29942f34eaf9c62e21d78d5c340</serial>
        </disk>
    </devices>
</domain>
"""

config_disk_serial_number_EXPECT_OUTPUT = """
<domain>
    <devices>
        <disk type="file" device="disk">
            <serial>7dfdb29942f34eaf9c62e21d78d5c340</serial>
        </disk>
        <disk type="file" device="disk">
            <serial>7dfdb29942f34eaf9c62e21d78d5c340</serial>
        </disk>
        <disk type="file" device="disk">
            <serial>7dfdb29942f34eaf9c62e21d78d5c340</serial>
        </disk>
    </devices>
</domain>
"""

config_disk_serial_number_HOOK_SCRIPT = """
def config_disk_serial_number(root, hook, serial_number):
    for devices in root.findall("devices"):
        for disks in devices.findall("disk"):
            for serial in disks.findall("serial"):
                hook.modify_value_of_element(serial, serial_number)

config_disk_serial_number(root, hook, "7dfdb29942f34eaf9c62e21d78d5c340")
"""

#------------------------------------------------

mock_identical_host_INPUT = """
<domain>
    <devices>
        <disk type="file" device="disk">
            <serial>a2421660c25845568a3d88b5386d3213</serial>
        </disk>
        <disk type="file" device="disk">
            <serial>85bbdfc098e44110a31922d5bc0ba603</serial>
        </disk>
        <disk type="file" device="disk">
            <serial>1dfdb29942f34eaf9c62e21d78d5c340</serial>
        </disk>
        <interface type='default'>
            <mac address='fa:af:36:ba:c2:00'/>
        </interface>
        <interface type='bridge'>
            <mac address='fa:88:98:8e:73:01'/>
            <bandwidth>
                <inbound average='85248'/>
                <outbound average='85248'/>
            </bandwidth>
        </interface>
    </devices>
</domain>
"""

mock_identical_host_EXPECT_OUTPUT = """
<domain>
    <devices>
        <disk type="file" device="disk">
            <serial>7dfdb29942f34eaf9c62e21d78d5c340</serial>
        </disk>
        <disk type="file" device="disk">
            <serial>7dfdb29942f34eaf9c62e21d78d5c340</serial>
        </disk>
        <disk type="file" device="disk">
            <serial>7dfdb29942f34eaf9c62e21d78d5c340</serial>
        </disk>
        <interface type='default'>
            <mac address='fa:af:36:ba:c2:00'/>
        </interface>
        <interface type='bridge'>
            <mac address='23:1a:d0:4e:3b:1e'/>
            <bandwidth>
                <inbound average='85248'/>
                <outbound average='85248'/>
            </bandwidth>
        </interface>
    </devices>
</domain>
"""

mock_identical_host_HOOK_SCRIPT = """
def config_mac_address_by_bandwidth(root, hook, mac_address, expect_bandwidth_mbps):
    def config_mac_address(interface):
        for mac in interface.findall("mac"):
            hook.modify_value_of_attribute(mac, "address", mac_address)

    # find network (interface) card with specific bandwidth
    for devices in root.findall("devices"):
        for interface in devices.findall("interface"):
            for bandwidth in interface.findall("bandwidth"):
                inbound = int(hook.get_value_of_attribute_from_parent(bandwidth, "inbound", "average"))/128
                outbound = int(hook.get_value_of_attribute_from_parent(bandwidth, "outbound", "average"))/128
                if inbound == expect_bandwidth_mbps and outbound == expect_bandwidth_mbps:
                    config_mac_address(interface)

def config_disk_serial_number(root, hook, serial_number):
    for devices in root.findall("devices"):
        for disks in devices.findall("disk"):
            for serial in disks.findall("serial"):
                hook.modify_value_of_element(serial, serial_number)

def mock_identical_host(root):
    config_mac_address_by_bandwidth(root, hook, "23:1a:d0:4e:3b:1e", 666)
    config_disk_serial_number(root, hook, "7dfdb29942f34eaf9c62e21d78d5c340")

mock_identical_host(root)
"""

#------------------------------------------------

class Test(unittest.TestCase):
    def test_function_is_bad_vm_root_volume(self):
        def test_xml_hook_works_or_not(hook_code, input_xmlstr, expect_output_xmlstr):
            modified_xml = xmlhook.get_modified_xml_from_hook(hook_code, input_xmlstr)
            expect_output_xmlstr_wet = xmlhook.get_modified_xml_from_hook("", expect_output_xmlstr)
            self.assertEqual(modified_xml, expect_output_xmlstr_wet)
        test_xml_hook_works_or_not(create_usb_device_HOOK_SCRIPT, create_usb_device_INPUT, create_usb_device_EXPECT_OUTPUT)
        test_xml_hook_works_or_not(remove_usb_device_if_has_cdrom_HOOK_SCRIPT, remove_usb_device_if_has_cdrom_INPUT, remove_usb_device_if_has_cdrom_EXPECT_OUTPUT)
        test_xml_hook_works_or_not(config_cpu_mode_HOOK_SCRIPT, config_cpu_mode_INPUT, config_cpu_mode_EXPECT_OUTPUT)
        test_xml_hook_works_or_not(config_numatune_HOOK_SCRIPT, config_numatune_INPUT, config_numatune_EXPECT_OUTPUT)
        test_xml_hook_works_or_not(config_virtio_disk_queue_number_HOOK_SCRIPT, config_virtio_disk_queue_number_INPUT, config_virtio_disk_queue_number_EXPECT_OUTPUT)
        test_xml_hook_works_or_not(config_mtu_by_mac_address_HOOK_SCRIPT, config_mtu_by_mac_address_INPUT, config_mtu_by_mac_address_EXPECT_OUTPUT)
        test_xml_hook_works_or_not(config_mac_address_by_mtu_HOOK_SCRIPT, config_mac_address_by_mtu_INPUT, config_mac_address_by_mtu_EXPECT_OUTPUT)
        test_xml_hook_works_or_not(config_mac_address_by_bandwidth_HOOK_SCRIPT, config_mac_address_by_bandwidth_INPUT, config_mac_address_by_bandwidth_EXPECT_OUTPUT)
        test_xml_hook_works_or_not(config_disk_serial_number_HOOK_SCRIPT, config_disk_serial_number_INPUT, config_disk_serial_number_EXPECT_OUTPUT)
        test_xml_hook_works_or_not(mock_identical_host_HOOK_SCRIPT, mock_identical_host_INPUT, mock_identical_host_EXPECT_OUTPUT)


if __name__ == "__main__":
    num_argv = len(sys.argv)
    num_hook_mode = 4      # test_vm_xml_hook.py + input_hook.txt + input_vm.xml + output_vm.xml
    num_unittest_mode = 1  # test_vm_xml_hook.py

    def read_text_file(path):
        with open(path, "r") as f:
            textstr = f.read()
            return textstr

    def write_text_file(path, textstr):
        with open(path, "w") as f:
            f.write(textstr)
            f.close()

    if num_argv == num_hook_mode:
        input_hook = read_text_file(str(sys.argv[1]))
        input_xmlstr = read_text_file(str(sys.argv[2]))
        output_xmlstr_path = sys.argv[3]
        modified_xml = xmlhook.get_modified_xml_from_hook(input_hook, input_xmlstr)
        write_text_file(output_xmlstr_path, modified_xml)
    elif num_argv == num_unittest_mode:
        unittest.main()
