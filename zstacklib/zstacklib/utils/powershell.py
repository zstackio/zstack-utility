import tempfile
import os

from zstacklib.utils import log
from zstacklib.utils import linux
from zstacklib.utils import shell

logger = log.get_logger(__name__)

HYPERV_V2V_EXPORT_PATH = "C:\\Users\\Administrator\\Desktop\\zstack-v2v"

class VolumeInfo(object):
    def __init__(self):
        self.name = None       # type: str
        self.size = -1         # type: long
        self.physicalSize = -1 # type: long
        self.type = None       # type: string
        self.path = None       # type: string
        self.bus = None        # type: string

class VmInfo(object):
    def __init__(self):
        self.name = None        # type: str
        self.uuid = None        # type: str
        self.cpuNum = -1        # type: int
        self.memorySize = -1    # type: long
        self.macAddresses = []  # type: list[str]
        self.volumes = []       # type: list[VolumeInfo]
        self.cdromNum = 0       # type: int
        self.bootMode = None    # type: str

class OpenRemotePS(object):
    def __init__(self, credential):
        self.remote_user = credential.remoteUser
        self.remote_password = credential.remotePassword
        self.remote_host = credential.remoteHost

    def test_winrm_connect(self):
        output = self.run_remote_script("Get-Host", "timeout 5s")
        logger.debug("test winrm connect success: %s", output)

    def get_vm_info(self, vmUuid=None):
        def make_vminfo_from_output(output):
            if output is None or output.strip() is "":
                return []

            vms = []
            vm = VmInfo()
            volume_prefix = "Volume@@@"
            volume_split = "@@@"

            for line in output.strip().split("\n"):
                content = line.strip().strip(",").strip("\"")
                if content.startswith(volume_prefix):
                    volume = VolumeInfo()
                    volume_struct = content.lstrip(volume_prefix)
                    logger.info("volume_struct: %s" % volume_struct)
                    for item in volume_struct.split(volume_split):
                        kv = item.split(":", 1)
                        key = kv[0].strip()
                        value = kv[1].strip()
                        if key == "name":
                            volume.name = value
                        elif key == "type":
                            volume.type = value
                        elif key == "size":
                            volume.size = value
                        elif key == "physicalSize":
                            volume.physicalSize = value
                        elif key == "path":
                            volume.path = value
                            s = value.split("\\\\")
                            volume.name = s[len(s) - 1]
                    vm.volumes.append(volume)
                    continue

                a = line.strip().rstrip(",").split(":", 1)
                if len(a) != 2:
                    continue

                key = a[0].strip().strip("\"")
                value = a[1].strip().strip("\"")
                if key == "name":
                    vm.name = value
                elif key == "uuid":
                    vm.uuid = value
                elif key == "memorySize":
                    vm.memorySize = value
                elif key == "cpuNum":
                    vm.cpuNum = value
                elif key == "cdromNum":
                    vm.cdromNum = value
                elif key == "bootMode":
                    vm.bootMode = value
                    vms.append(vm)
                    vm = VmInfo()
                elif key == "macs":
                    macs = []
                    for mac in value.strip().split(","):
                        if len(mac) != 12:
                            raise Exception("found wrong mac address %s" % mac)
                        macs.append(':'.join(mac[i:i + 2] for i in range(0, 12, 2)))
                    vm.macAddresses = macs
                else:
                    continue
            return vms

        if vmUuid:
            srcVm = "-ID %s" % vmUuid
        else:
            srcVm = ""
        self.test_winrm_connect()
        script = """
$vmInfos = New-Object -TypeName System.Collections.ArrayList
$vms = Get-Vm %s | select VMname, VMID, MemoryStartup, ProcessorCount, Generation
foreach ($vm in $vms) 
{
    $pso = [PSCustomObject]@{
        PSTypeName = "VmInfo"
        name = ""
        uuid = ""
        memorySize = ""
        cpuNum = ""
        cdromNum = ""
        macs = ""
        volumes = ""
        bootMode = ""
    }

    # fix vm info
    $cdromNum = (Get-VM -ID $vm.VMId| Get-VMDvdDrive).length
    $pso.name = $vm.vmname
    $pso.uuid = $vm.vmid
    $pso.memorySize = $vm.memoryStartup
    $pso.cpuNum = $vm.ProcessorCount
    $pso.cdromNum = $cdromNum
    if ($vm.Generation -eq 2) {
        $pso.bootMode = "UEFI"
    } else {
        $pso.bootMode = "Legacy"
    }

    # fix mac info
    $macs = Get-VM -ID $vm.VMId | Get-VMNetworkAdapter | select MacAddress
    $macarray = New-Object -TypeName System.Collections.ArrayList
    foreach ($mac in $macs)
    {
        $macindex = $macarray.Add($mac.macaddress)
    }

    $diskarray = New-Object -TypeName System.Collections.ArrayList
    $disks = Get-VHD -VMId $vm.VMId
    $i = 0

    # fix volume info
    foreach ($disk in $disks)
    {
        $voltype = $null
        if ($i -eq 0) {
            $voltype = "Root"
        } else {
            $voltype = "Data"
        }
        $volsize = $disk.Size
        $volphysicalSize = $disk.FileSize
        $volpath = $disk.Path

        $volstring = "Volume@@@type:$voltype@@@size:$volsize@@@physicalSize:$volphysicalSize@@@path:$volpath"
        $diskindex = $diskarray.Add($volstring)

        $i = $i+1
    }

    $pso.macs = $macarray -join ","
    $pso.volumes = $diskarray
    $index = $vmInfos.Add($pso)
}

$vmInfos | ConvertTo-Json
""" % srcVm
        output = self.run_remote_script(script)
        vms = make_vminfo_from_output(output)
        return vms

    def fetch_vm_disk(self, vmInfo, dest_path, conversionHostIp):
        export_path = "%s\%s" % (HYPERV_V2V_EXPORT_PATH, vmInfo.uuid)
        disk_path = "%s\%s\%s" % (export_path, vmInfo.name, "Virtual Hard Disks")

        ftp_path = "ftp://%s/%s/" % (conversionHostIp, vmInfo.uuid)
        linux.mkdir(dest_path, 0777)

        script = """
# create directory
$export_path = "%s"
Remove-Item $export_path -Recurse -ErrorAction Ignore
New-Item -ItemType Directory -Force -Path $export_path

# export vm
$vm = Get-VM -ID %s
Export-VM -VM $vm -Path $export_path

# ftp put to conversion host
$source = "%s"
$destination = "%s"
$username = "anonymous"
$password = ""
# $cred = Get-Credential
$wc = New-Object System.Net.WebClient
$wc.Credentials = New-Object System.Net.NetworkCredential($username, $password)

$files = get-childitem $source -recurse -force
foreach ($file in $files)
{
    Write-Host "Uploading $file"
    $wc.UploadFile("$destination$file", $file.FullName)
}

$wc.Dispose()

# delete export directory
Remove-Item $export_path -Recurse -ErrorAction Ignore
""" % (export_path, vmInfo.uuid, disk_path, ftp_path)

        output = self.run_remote_script(script)
        logger.debug(output)
        return dest_path

    def run_remote_script(self, script, options=""):
        ps_script = """
$securePassword = ConvertTo-SecureString %s -AsPlainText -Force
$credential = new-object Management.Automation.PSCredential('%s', $securePassword)
invoke-command -computername %s -credential $credential -scriptblock {
%s
} -Authentication Negotiate        
""" % (self.remote_password, self.remote_user, self.remote_host, script)
        fd, ps_script_path = tempfile.mkstemp()
        os.fdopen(fd, 'w').write(ps_script)
        logger.info('run remote powershell script: %s' % script)
        ps = shell.ShellCmd('%s pwsh -f %s' % (options, ps_script_path))
        ps(False)
        if ps.return_code != 0:
            logger.debug('powershell script run failed, cause: %s' % ps.stderr)
            ps.raise_error()
        os.remove(ps_script_path)
        return ps.stdout