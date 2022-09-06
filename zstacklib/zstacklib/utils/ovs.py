'''

@author: haibiao.xiao
'''
import os
import shutil
import time
import yaml
import glob
import uuid
import re
from enum import Enum, unique

from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import iproute
from zstacklib.utils import lock
from zstacklib.utils import linux

logger = log.get_logger(__name__)

OvsPath = "/var/run/openvswitch/"
LogPath = "/var/log/zstack/openvswitch/"
SockPath = "/var/run/zstack/"
ConfPath = "/usr/local/etc/zstack-ovs/"
CONF_DB = "/usr/local/etc/zstack-ovs/conf.db"
DB_SOCK = "/var/run/openvswitch/db.sock"
DBPidPath = "/var/run/openvswitch/ovsdb-server.pid"
SwitchPidPath = "/var/run/openvswitch/ovs-vswitchd.pid"
DBLogPath = "/var/log/zstack/openvswitch/ovsdb-server.log"
SwitchLogPath = "/var/log/zstack/openvswitch/ovs-vswitchd.log"
DBCtlFilePath = "/var/run/openvswitch/ovsdb-server.zs.ctl"
SwitchCtlFilePath = "/var/run/openvswitch/ovs-vswitchd.zs.ctl"
CtlBin = "ovs-vsctl --db=unix:{} ".format(DB_SOCK)

OvsDpdkSupportVnic = ['vDPA', 'dpdkvhostuserclient']
OvsDpdkSupportBondType = ['dpdkBond', 'ovsBond']


class OvsError(Exception):
    '''ovs error'''


def writeSysfs(path, value, supressRaise=False):
    try:
        with open(path, 'w') as f:
            f.write(str(value))
    except Exception as e:
        logger.warn(str(e))
        if not supressRaise:
            raise OvsError(str(e))


def readSysfs(path, supressRaise=False):
    ret = None
    try:
        with open(path, 'r') as f:
            ret = f.read().rstrip()
    except Exception as e:
        logger.warn(str(e))
        if not supressRaise:
            raise OvsError(str(e))

    return ret


@linux.retry(times=10, sleep_time=5)
def confirmWriteSysfs(path, value):
    writeSysfs(path, value)
    if readSysfs(path) != value:
        raise OvsError("write sysfs failed")


def getOSReleaseInfo():
    osRelease = {}
    with open('/etc/os-release', 'r') as f:
        lines = f.readlines()
        for l in lines:
            l = l.strip()
            if l == '':
                continue
            lsplit = l.split("=")
            osRelease[lsplit[0].strip()] = lsplit[1].strip('"')

    return osRelease


def version_geq(v1, v2):
    """
    Compare (dot separated) version numbers. return true if 
    v1 is greater or equal v2, otherwise false.
    """
    v1 = v1.split(".")
    v2 = v2.split(".")
    vLen = len(v1) if len(v1) < len(v2) else len(v2)
    for i in range(0, vLen):
        if int(v1[i]) < int(v2[i]):
            return False
        elif int(v1[i]) > int(v2[i]):
            return True
    return True


def checkBDFFormat(bdfStr):
    pattern = re.compile(r'\d{4}(:[0-9a-fA-F]{2}){2}.\d$')
    ret = re.match(pattern, bdfStr)
    if ret is not None:
        if ret.span()[1] == 12:
            return

    raise OvsError("BDF format error. bdf:{}".format(bdfStr))


def isBDF(bdfStr):
    try:
        checkBDFFormat(bdfStr)
        return True
    except OvsError:
        return False


def getBDFOfInterface(ifName):
    """BDF alias of Bus Device Function."""
    try:
        pciPath = '/sys/class/net/{}/device'.format(ifName)
        if not os.path.exists(pciPath):
            raise OvsError("No such device:{}".format(pciPath))
        bdf = os.path.realpath(pciPath).split("/")[-1]
        return bdf
    except Exception as err:
        raise OvsError(str(err))


def getInterfaceOfBDF(bdf):
    try:
        checkBDFFormat(bdf)
        netPath = '/sys/bus/pci/devices/{}/net'
        ifName = os.listdir(netPath.format(bdf))[0].split('_')[0]
        return ifName
    except Exception as err:
        raise OvsError(str(err))


def getPciID(bdfOrIf):
    """
    pci id = vendor:device
    """
    vendorPath = '/sys/class/net/{}/device/vendor'
    devicePath = '/sys/class/net/{}/device/device'
    if isBDF(bdfOrIf):
        vendorPath = '/sys/bus/pci/devices/{}/vendor'
        devicePath = '/sys/bus/pci/devices/{}/device'

    vendorId = readSysfs(vendorPath.format(bdfOrIf))[2:6]
    deviceId = readSysfs(devicePath.format(bdfOrIf))[2:6]

    return vendorId + deviceId


def getOffloadStatus(interfaceName):
    try:
        venv = OvsVenv()
        pciId = getPciID(interfaceName)
        if pciId in venv.offloadStatus.keys():
            return venv.offloadStatus[pciId]
        return None
    except OvsError as err:
        logger.debug("Get offload status failed. {}".format(err))


def probeModules(moduleName):
    ret = shell.run("modprobe {}".format(moduleName))
    if ret != 0:
        raise OvsError("Can not find module:{}.".format(moduleName))


@unique
class BondType(Enum):
    NormalIface = 0
    KernelBond = 1
    DpdkBond = 2
    OvsBond = 3
    VfLag = 4


class Bond:
    def __init__(self):
        self.name = "default"
        self.policy = None
        self.mode = 1
        self.slaves = []
        self.lacp = "off"
        self.id = 0
        self.options = "dpdkBond"


@unique
class vNicType(Enum):
    vDPA = 0
    dpdkvhostuserclient = 1


class OvsVenv(object):
    """ prepare ovs workspace and env
        including:
        1. mlnx ofed driver
        2. hugepages(created in vswitchd starting process)
        3. offloadStatus of smart-nics
        4. some conf/log/sock directory
    """
    __cache__ = []  # list[int, OvsVenv]

    DEFAULT_HUGEPAGE_SIZE = 2048
    DEFAULT_NR_HUGEPAGES = 1024
    hugepagesPaths = {2048: "hugepages/hugepages-2048kB/",
                      1048576: "hugepages/hugepages-1048576kB/"}

    def __new__(cls):
        if len(cls.__cache__) == 2 and (time.time() - cls.__cache__[0]) <= 60:
            cls.__cache__[0] = time.time()
            return cls.__cache__[1]
        obj = super(OvsVenv, cls).__new__(cls)
        obj.init()
        cls.__cache__ = [int(time.time()), obj]
        return obj

    def init(self, hugepage_size=DEFAULT_HUGEPAGE_SIZE, nr_hugepages=DEFAULT_NR_HUGEPAGES):
        self.ofedVer = "unknow"
        self.vSwitchVer = "unknow"
        self.dpdkVer = "unknow"
        self.ovsDBVer = "unknow"
        self.offloadStatus = {}
        self.numaNodes = self._getNumaNodes()
        self.hugepage_size = hugepage_size
        self.nr_hugepages = nr_hugepages

        if self._hasOpenvSwitch():
            probeModules("bonding")
            self._getOpenvSwitchVersion()
            self._fillNicOffloadStatus()
            self._makeDirForOvs()

    def _hasOpenvSwitch(self):
        if os.path.exists("/usr/bin/ovs-vsctl") \
           and os.path.exists("/usr/sbin/ovs-vswitchd") \
           and os.path.exists("/usr/sbin/ovsdb-server"):
            return True
        return False

    def _getOpenvSwitchVersion(self):
        verList = shell.call(
            "ovs-vswitchd --version | grep -E 'DPDK|vSwitch'").splitlines()
        if len(verList) > 0 and verList[0] != '':
            self.vSwitchVer = verList[0].split()[-1]
        if len(verList) > 1 and verList[1] != '':
            self.dpdkVer = verList[1].split()[-1]
        self.ovsDBVer = shell.call(
            "ovsdb-server --version | awk 'NR==1{print $NF}'").strip()
        if os.path.exists("/usr/bin/ofed_info"):
            self.ofedVer = shell.call("ofed_info -n").strip()

    def _fillNicOffloadStatus(self):
        nicInfoPath = os.path.join(ConfPath, "smart-nics.yaml")
        if not os.path.exists(nicInfoPath):
            raise OvsError("no such file:{}".format(nicInfoPath))

        with open(nicInfoPath, 'r') as f:
            data = yaml.safe_load(f)

        for i in data:
            self.offloadStatus[str(i['nic']['vendor_device'])] = "|".join(
                str(x) for x in i['nic']['offloadstatus'])

    def _getHugepageInfoByNode(self, numaNodePath):
        hugepagesPath = os.path.join(
            numaNodePath, self.hugepagesPaths[self.hugepage_size])

        freeHugepages = int(
            readSysfs(os.path.join(hugepagesPath, "free_hugepages")))
        nrHugepages = int(
            readSysfs(os.path.join(hugepagesPath, "nr_hugepages")))
        return freeHugepages, nrHugepages

    def _getFreeMemByNode(self, numaNodePath):
        meminfo = {}
        with open(os.path.join(numaNodePath, "meminfo"), "r") as f:
            lines = f.readlines()
            for l in lines:
                lsplit = l.split(":")
                meminfo[lsplit[0].split()[-1].strip()] = lsplit[1].strip()

        memFree = int(meminfo['MemFree'].split()[0])
        return memFree

    def _makeDirForOvs(self):
        if not os.path.isdir(OvsPath):
            os.mkdir(OvsPath, 0o755)

        if not os.path.isdir(LogPath):
            os.mkdir(LogPath, 0o755)

        if not os.path.exists(SockPath):
            os.mkdir(SockPath, 0o755)

        if not os.path.exists(ConfPath):
            os.mkdir(ConfPath, 0o755)

    def _getNumaNodes(self):
        numaNodePaths = glob.glob("/sys/devices/system/node/node*/")
        if len(numaNodePaths) < 1:
            raise OvsError("Get numa nodes failed.")

        return len(numaNodePaths)

    def allocateHugepageMem(self):
        """
        prepare Hugepages for DPDK.
        since we can not tell in which numa node the dpdk device is located,
        we have to init hugepages in all numa nodes. 
        2G is enough for Shared memory mode.
        http://confluence.zstack.io/pages/viewpage.action?pageId=96493877
        """
        numaNodePaths = glob.glob("/sys/devices/system/node/node*/")
        if self.numaNodes < 1:
            raise OvsError("can not find numa node.")

        for numaNodePath in numaNodePaths:
            freeHugepages, nrHugepages = self._getHugepageInfoByNode(
                numaNodePath)
            memFree = self._getFreeMemByNode(numaNodePath)

            # freeHugepages is enough for dpdk.
            if freeHugepages >= self.nr_hugepages:
                continue

            pagesNeedAllocate = self.nr_hugepages + \
                (nrHugepages - freeHugepages)
            needFreeMem = self.nr_hugepages - freeHugepages

            # raise error if current free mem is not enough for the reset of hugepages needed by dpdk.
            if memFree < needFreeMem * self.hugepage_size:
                raise OvsError("chould not malloc enough hugepage for ovs dpdk, {} expected but {} left.".format(
                    pagesNeedAllocate * self.hugepage_size, memFree))

            writeSysfs(os.path.join(
                numaNodePath, self.hugepagesPaths[self.hugepage_size], "nr_hugepages"), str(pagesNeedAllocate))

    def isDpdkSupport(self):
        return self.dpdkVer != "unknow"

    def isMellonxSupport(self):
        return self.ofedVer != "unknow"


class Ovs(object):
    """ control the lifecycle of ovsdb and vswitchd.
        make sure OvsVenv is ready before start ovsdb/vswitchd.
    """

    def __init__(self):
        self.venv = OvsVenv()
        self.ovsSchema = self._getOvsSchema()

    def _getOvsSchema(self):
        ovsdir = "/usr/share/openvswitch/"
        path = os.path.join(ovsdir, 'vswitchd', 'vswitch.ovsschema')
        if os.path.isfile(path):
            return path
        return os.path.join(ovsdir, 'vswitch.ovsschema')

    def start(self):
        try:
            self.startDB()
            self.startSwitch()
        except OvsError:
            self.stop()
            raise

    def stop(self):
        self.stopDB()
        self.stopSwitch()

    def restart(self):
        self.stop()
        self.start()

    def isOvsProcRunning(self, procName=None):
        procNameToPids = {
            "ovsdb-server": self.pids[0], "ovs-vswitchd": self.pids[1]}
        ret = True

        if procName:
            pids = [procNameToPids[procName]]
        else:
            pids = self.pids

        for pid in pids:
            if pid <= 0:
                ret = False
            if not self._processExists(pid):
                ret = False

        return ret

    def _createOvsDB(self):
        ret = shell.run(
            'ovsdb-tool -v create {} {}'.format(CONF_DB, self.ovsSchema))
        if ret != 0:
            raise OvsError("Create ovsdb file failed.")

    def _backupOvsDB(self):
        getDBVerCmd = shell.ShellCmd(
            "ovsdb-tool db-version {}".format(CONF_DB))
        getDBVerCmd(False)
        if getDBVerCmd.return_code == 0:
            version = getDBVerCmd.stdout
        else:
            version = 'old'

        getDBCksumCmd = shell.ShellCmd(
            "ovsdb-tool db-cksum {} | awk '{print $1}'".format(CONF_DB))
        getDBCksumCmd(False)
        if getDBCksumCmd.return_code == 0:
            cksum = getDBCksumCmd.stdout
        else:
            cksum = 'unknow'

        backup = CONF_DB + ".backup" + version + "-" + cksum
        shutil.copy2(CONF_DB, backup)

    def _convertOvsDB(self):
        # Compact database.  This is important if the old schema did not enable
        # garbage collection (i.e. if it did not have any tables with "isRoot":
        # true) but the new schema does.  In that situation the old database
        # may contain a transaction that creates a record followed by a
        # transaction that creates the first use of the record.  Replaying that
        # series of transactions against the new database schema (as "convert"
        # does) would cause the record to be dropped by the first transaction,
        # then the second transaction would cause a referential integrity
        # failure (for a strong reference).
        #
        # Errors might occur on an Open vSwitch downgrade if ovsdb-tool doesn't
        # understand some feature of the schema used in the OVSDB version that
        # we're downgrading from, so we don't give up on error.
        shell.run("ovsdb-tool compact {}".format(CONF_DB))

        ret = shell.run(
            "ovsdb-tool convert {} {}".format(CONF_DB, self.ovsSchema))
        if ret != 0:
            logger.warn(
                "Schema conversion failed, using empty database instead")
            os.remove(CONF_DB)
            self._createOvsDB()

    def upgradeDB(self):
        """
        create ovsDB if not exist
        upgrade ovsDB if needs conversion
        """

        if not os.path.isfile(CONF_DB):
            self._createOvsDB()
            return

        s = shell.ShellCmd(
            "ovsdb-tool needs-conversion {} {}".format(CONF_DB, self.ovsSchema), None, False)
        s(False)
        if s.return_code != 0:
            logger.warn("upgrade ovsdb failed: {} {}".format(
                s.stderr, s.stdout))
            return
        elif s.stdout != "yes":
            logger.debug("current ovsdb do not need conversion.")
            return
        else:
            self._backupOvsDB()
            self._convertOvsDB()
            logger.debug("upgrade ovsdb success.")

    def _initOvsDBSetting(self):
        ret = shell.run(CtlBin +
                        "--no-wait -- init -- set Open_vSwitch . db-version={}".format(self.venv.ovsDBVer))
        if ret != 0:
            raise OvsError("Init openvswitch database settings failed.")

        time.sleep(1)
        # get os release info
        osRelease = getOSReleaseInfo()
        systemType = osRelease['ID']
        systemVersion = osRelease['VERSION_ID']

        cmd = CtlBin \
            + "--no-wait set Open_vSwitch . ovs-version={}".format(self.venv.vSwitchVer) \
            + " external-ids:system-id={}".format(uuid.uuid4()) \
            + " external-ids:rundir={}".format(OvsPath) \
            + " system-type={}".format(systemType) \
            + " system-version={}".format(systemVersion)

        if shell.run(cmd) != 0:
            logger.warn("Set OS informations to ovsdb failed.")

    @lock.lock('startDB')
    def startDB(self):
        if self.isOvsProcRunning("ovsdb-server"):
            return

        self.stopDB()
        self.upgradeDB()

        cmd = "ovsdb-server {}".format(CONF_DB) \
            + " -vconsole:emer -vsyslog:err -vfile:info" \
            + " --remote=punix:{}".format(DB_SOCK) \
            + " --private-key=db:Open_vSwitch,SSL,private_key" \
            + " --certificate=db:Open_vSwitch,SSL,certificate" \
            + " --bootstrap-ca-cert=db:Open_vSwitch,SSL,ca_cert" \
            + " --no-chdir --log-file={} --pidfile={} --unixctl={}".format(
                DBLogPath, DBPidPath, DBCtlFilePath) \
            + " --detach --monitor"

        startDBCmd = shell.ShellCmd(cmd)
        startDBCmd(False)
        if startDBCmd.return_code != 0:
            raise OvsError("start ovsdb failed: {} {}".format(
                startDBCmd.stderr, startDBCmd.stdout))

        self._initOvsDBSetting()

        logger.debug("ovsdb start success. pid:[{}]".format(self.pids[0]))

    def stopDB(self):
        return self.stopOvsProcess("ovsdb-server")

    def restartDB(self):
        self.stopDB()
        self.startDB()

    def checkOvsConfiguration(self, key, value):
        try:
            ret = shell.call(
                CtlBin + "get Open_vSwitch . other_config:{}".format(key)).strip("\n").strip('"')
            return ret == str(value)
        except shell.ShellError:
            return False

    def _getDpdkInitStates(self):
        if not self.venv.isDpdkSupport() or \
           not self.isOvsProcRunning("ovsdb-server") or \
           not self.checkOvsConfiguration("dpdk-init", "true"):
            return False

        return True

    @lock.lock('startSwitch')
    def startSwitch(self):

        if self.isOvsProcRunning("ovs-vswitchd"):
            return

        self.stopSwitch()

        if self._getDpdkInitStates():
            self.venv.allocateHugepageMem()

        cmd = "ovs-vswitchd unix:{}".format(DB_SOCK) \
            + " -vconsole:emer -vsyslog:err -vfile:info" \
            + " --mlockall --no-chdir" \
            + " --log-file={} --pidfile={} --unixctl={}".format(
                SwitchLogPath, SwitchPidPath, SwitchCtlFilePath) \
            + " --detach --monitor"
        startSwitchCmd = shell.ShellCmd(cmd)
        startSwitchCmd(False)
        if startSwitchCmd.return_code != 0:
            raise OvsError(
                "start ovs-vswitch failed: {} {}".format(startSwitchCmd.stderr, startSwitchCmd.stdout))

        self.setOvsLogrotate()
        logger.debug(
            "ovs-vswitch start success. pid:[{}]".format(self.pids[1]))

    def stopSwitch(self):
        return self.stopOvsProcess("ovs-vswitchd")

    def restartSwitch(self):
        self.stopSwitch()
        self.startSwitch()

    @property
    def pids(self):
        """ return [ovsdb_pid, ovs-vswitch_pid] """

        result = [-1, -1]
        try:
            ovsdbPidf = os.path.join(OvsPath, "ovsdb-server.pid")
            vswitchPidf = os.path.join(OvsPath, "ovs-vswitchd.pid")

            if os.path.exists(ovsdbPidf):
                with open(ovsdbPidf, 'r') as f:
                    result[0] = int(f.read().strip())

            if os.path.exists(vswitchPidf):
                with open(vswitchPidf, 'r') as f:
                    result[1] = int(f.read().strip())
        except OSError as err:
            logger.error("OSError: {}".format(err))
        finally:
            return result

    def _processExists(self, pid):
        return os.path.isdir(os.path.join("/proc", str(pid)))

    def _stopProcessInSchedule(self, procName, procInfoDict):

        pid = procInfoDict[procName]["pid"]
        ver = procInfoDict[procName]["ver"]
        ctl = procInfoDict[procName]["ctl"]
        pidPath = os.path.join(OvsPath, "{}.pid".format(procName))

        graceful = "EXIT 0.1 0.25 0.65 1"
        actions = "TERM 0.1 0.25 0.65 1 1 1 1 KILL 1 1 1 2 10 15 30 FAIL"
        # Use `ovs-appctl exit` only if the running daemon version
        # is >= 2.5.90.  This script might be used during upgrade to
        # stop older versions of daemons which do not behave correctly
        # with `ovs-appctl exit` (e.g. ovs-vswitchd <= 2.5.0 deletes
        # internal ports).
        if version_geq(ver, "2.5.90"):
            actions = graceful + ' ' + actions

        forceStop = False
        for action in actions.split():

            if not self._processExists(pid):
                if forceStop:
                    return
                else:
                    # check one more time
                    if not os.path.exists(pidPath) and not self._processExists(pid):
                        return

            if action == 'EXIT':
                shell.run(
                    "ovs-appctl -T 1 -t {} exit ".format(ctl))
            elif action == 'TERM':
                shell.run("kill {}".format(pid))
                forceStop = True
            elif action == 'KILL':
                shell.run("kill -9 {}".format(pid))
                forceStop = True
            elif action == 'FAIL':
                raise OvsError("Killing {} {} failed".format(procName, pid))
            else:
                time.sleep(float(action))

    def stopOvsProcess(self, procName):
        """
        stop ovsdb or vswitch by ovs-appctl,
        if not work, kill it.
        """
        dict = {"ovsdb-server": {"pid": self.pids[0], "ver": self.venv.ovsDBVer, "ctl": DBCtlFilePath},
                "ovs-vswitchd": {"pid": self.pids[1], "ver": self.venv.vSwitchVer, "ctl": SwitchCtlFilePath}}

        pid = dict[procName]["pid"]
        ctl = dict[procName]["ctl"]
        if pid < 0:
            return

        try:
            pidPath = os.path.join(OvsPath, "{}.pid".format(procName))
            if not self._processExists(pid):
                os.remove(pidPath)
                os.remove(ctl)
                return
            else:
                self._stopProcessInSchedule(procName, dict)
        except OSError as err:
            logger.error("OSError: {}".format(err))
            raise OvsError(str(err))

    def setOvsLogrotate(self):
        logrotateFile = "/etc/logrotate.d/openvswitch-zstack"
        logrotateConf = """
/var/log/zstack/openvswitch/*.log {
    daily
    compress
    sharedscripts
    missingok
    postrotate
        # Tell Open vSwitch daemons to reopen their log files
        if [ -d /var/run/openvswitch ]; then
            for ctl in /var/run/openvswitch/*.ctl; do
                ovs-appctl -t "$ctl" vlog/reopen 2>/dev/null || :
            done
        fi
    endscript
}
"""
        firstTimeLogrotate = False
        if not os.path.exists(logrotateFile):
            firstTimeLogrotate = True

        with open(logrotateFile, "w") as f:
            f.write(logrotateConf)

        if firstTimeLogrotate:
            ret = shell.run("logrotate --force /etc/logrotate.d/openvswitch-zstack")
            if ret != 0:
                raise OvsError("set logrotate for openvswitch failed.")

        logger.debug("set logrotate for openvswitch success.")
        

class OvsBaseCtl(object):
    def __init__(self):
        self.ovs = Ovs()
        self.venv = self.ovs.venv
        # use dpdk while dpdk support and opened.
        self.dpdkSup = self.venv.isDpdkSupport()
        self.dpdkOpen = False

    def checkOvs(func):
        def wrapper(self, *args, **kw):
            if not self.ovs.isOvsProcRunning():
                # if ovsdb/vswitchd state abnormality, try to restart it.
                self.ovs.restart()
            return func(self, *args, **kw)
        return wrapper

    def listBrs(self, *args):
        try:
            ret = shell.call(CtlBin + "list-br")
        except shell.ShellError as err:
            logger.error("List ovs bridges failed. {}".format(err))
            return []
        else:
            return ret.strip().splitlines()

    def createBr(self, brName, *args):
        brs = self.listBrs()
        if brName in brs:
            logger.debug("Bridge {} already created".format(brName))
            return

        try:
            shell.check_run(CtlBin + 'add-br {} -- set Bridge {} datapath_type=netdev'.format(
                brName, brName, "netdev"))
        except Exception as err:
            logger.error(
                "Create ovs bridges {} failed. {}".format(brName, err))
            raise OvsError(str(err))

    def deleteBr(self, *args):
        try:
            brs = self.listBrs()
            for arg in args:
                if arg in brs:
                    shell.call(CtlBin + "--timeout=5 del-br {}".format(arg))
        except Exception as err:
            logger.error("delete bridge {} failed. {}".format(arg, err))
            raise OvsError(str(err))

    def deleteBrs(self):
        try:
            brs = self.listBrs()
            for br in brs:
                shell.call(CtlBin + "--timeout=5 del-br {}".format(br))
        except Exception as err:
            logger.error("delete bridge {} failed. {}".format(br, err))
            raise OvsError(str(err))

    def listIfaces(self, brName, *args):
        try:
            ret = shell.call(
                CtlBin + "--timeout=5 list-ifaces {}".format(brName))
        except Exception as err:
            logger.error(
                "List interface of bridge {} failed. {}".format(brName, err))
            return []
        else:
            return ret.strip().splitlines()

    def listPorts(self, brName, *args):
        try:
            ret = shell.call(CtlBin +
                             "--timeout=5 list-ports {}".format(brName))
        except Exception as err:
            logger.error(
                "List ports of bridge {} failed. {}".format(brName, err))
            return []
        else:
            return ret.strip().splitlines()

    def addOuterToBridge(self, brName, outerName):
        if outerName not in self.listPorts(brName):
            self.addAnonymousPort(brName, outerName)
        else:
            logger.debug("Port {} already exsited before add to {}."
                         .format(outerName, brName))

    def deleteOuterFromBridge(self, brName, outerName):
        if outerName in self.listPorts(brName):
            self.delPort(brName, outerName)
        else:
            logger.debug("Port {} do not exsited in {}."
                         .format(outerName, brName))

    def addAnonymousPort(self, brName, phyIfName):
        try:
            cmd = CtlBin + \
                'add-port {} {}'.format(brName, phyIfName)
            shell.call(cmd)
        except Exception as err:
            logger.error(
                "Add port for brdige {} failed. {}".format(brName, err))
            self.delPort(brName, phyIfName)
            raise OvsError(str(err))

    def addPort(self, brName, phyIfName, type, *args):
        try:
            cmd = CtlBin + \
                'add-port {} {} -- set Interface {} type={} '.format(
                    brName, phyIfName, phyIfName, type)
            for arg in args:
                cmd = cmd + "options:{} ".format(arg)
            shell.call(cmd)
        except Exception as err:
            logger.error(
                "Add port for brdige {} failed. {}".format(brName, err))
            self.delPort(brName, phyIfName)
            raise OvsError(str(err))

    def delPort(self, brName, phyIfName, *args):
        try:
            shell.call(CtlBin + 'del-port {} {}'.format(brName, phyIfName))
        except Exception as err:
            logger.error(
                "Delete port of bridge {} failed. {}".format(brName, err))
            raise OvsError(str(err))

    def setPort(self, portName, tag):
        try:
            shell.call(CtlBin +
                       'set Port {} tag={} '.format(portName, tag))
        except Exception as err:
            logger.error("Set port {} failed. {}".format(portName, err))
            raise OvsError(str(err))

    def setIfaces(self, ifName, *args):
        try:
            cmd = CtlBin + 'set Interface {} '.format(ifName)
            for arg in args:
                cmd = cmd + "{} ".format(arg)

            shell.call(cmd)
        except Exception as err:
            logger.error("Set interface {} failed. {}".format(err))
            raise OvsError(str(err))

    @property
    def isDpdkReady(self):
        return self.dpdkSup and self.dpdkOpen

    @staticmethod
    def getBondFromFile(bondName):
        try:
            bondFile = os.path.join(ConfPath, "dpdk-bond.yaml")

            dpdkBond = Bond()
            with open(bondFile, "r") as f:
                data = yaml.safe_load(f)

            for d in data:
                if d['bond']['name'] == bondName:
                    dpdkBond.name = d['bond']['name']
                    dpdkBond.mode = d['bond']['mode']
                    if d['bond'].has_key('lacp'):
                        dpdkBond.lacp = d['bond']['lacp']
                    if d['bond'].has_key('options'):
                        dpdkBond.options = d['bond']['options']
                    if d['bond'].has_key('policy'):
                        dpdkBond.policy = d['bond']['policy']
                    dpdkBond.id = d['bond']['id']
                    for i in d['bond']['slaves']:
                        dpdkBond.slaves.append(str(i))

                    return dpdkBond
            return None
        except Exception:
            return None

    def _getBondSlaves(self, bondName):
        slaves_p = "/sys/class/net/{}/bonding/slaves".format(bondName)
        ifList = []
        # kernel bond
        if os.path.exists(slaves_p):
            ifList = readSysfs(slaves_p).split()
            return ifList

        # dpdk bond
        dpdkBond = OvsDpdkCtl.getBondFromFile(bondName)
        if dpdkBond is not None:
            ifList = dpdkBond.slaves

        return ifList

    def _isKernelBond(self, name):
        bondList = readSysfs('/sys/class/net/bonding_masters').strip().split()
        return name in bondList

    def getBondType(self, name):
        # dpdk bond and ovs bond configurations are store in file 'dpdk-bond.xml'
        bond = OvsDpdkCtl.getBondFromFile(name)
        if bond:
            if bond.options == "dpdkBond":
                return BondType.DpdkBond
            elif bond.options == "ovsBond":
                return BondType.OvsBond
            elif bond.options == "vfLag":
                if self._isKernelBond(name):
                    return BondType.VfLag
            else:
                raise OvsError("Unexpected bond type {}.".format(bond.options))

        if self._isKernelBond(name):
            return BondType.KernelBond

        infacePath = '/sys/class/net/{}'.format(name)
        if os.path.exists(infacePath):
            return BondType.NormalIface

        raise OvsError("Can not find interface:{}.".format(name))

    @linux.retry(times=3, sleep_time=1)
    def configPmdCpuMaskForOvs(self, cpuMask):
        if cpuMask is None:
            shell.run(CtlBin +
                  "--no-wait remove Open_vSwitch . other_config pmd-cpu-mask")
        else:
            shell.run(CtlBin +
                  "--no-wait set Open_vSwitch . other_config:pmd-cpu-mask={}".format(cpuMask))

            if not self.ovs.checkOvsConfiguration("pmd-cpu-mask", cpuMask):
                raise OvsError("Config pmd cpu mask for ovs failed.")

    @linux.retry(times=3, sleep_time=1)
    def configLacpFallbackAbForOvs(self):
        # TODO: lacp-time bond-detect-mode bond-miimon-interval bond_updelay bond-rebalance-interval
        shell.run(CtlBin +
                  "--no-wait set Open_vSwitch . other-config:lacp-fallback-ab=true")

        if not self.ovs.checkOvsConfiguration("lacp-fallback-ab", "true"):
            raise OvsError("Config lacp fallback ab for ovs failed.")

    def _nicBackendGC(self):
        """
        release the vdpa/dpdkvhostuserclient while associated vm is no exists.
        """
        try:
            rawData = shell.call(
                CtlBin + " --columns=name,external_ids find interface external_ids!={}").splitlines()
            tmp = {}
            nicAndVmUuid = {}
            for row in rawData:
                if len(row) == 0:
                    if 'name' not in tmp.keys() or 'external_ids' not in tmp.keys():
                        tmp = {}
                        continue
                    nicAndVmUuid[tmp['name']] = tmp['external_ids'].lstrip(
                        '{').rstrip('}').split('=')[1].strip('"')
                    tmp = {}
                else:
                    name, value = row.split(':')
                    tmp[name.strip()] = value.strip()

            files = os.listdir('/var/run/libvirt/qemu/')
            runningVmList = set(vm.split('.')[0] for vm in files)

            for d in nicAndVmUuid:
                if nicAndVmUuid[d] not in runningVmList:
                    self.destoryNicBackend(nicAndVmUuid[d])
        except shell.ShellError as err:
            raise OvsError(str(err))

    def clearOvsConfig(self):
        shell.run(CtlBin + "--no-wait clear Open_vSwitch . other-config")

    def reconfigOvsBridge(self):
        brs = self.listBrs()
        for b in brs:
            if b == '':
                continue
            self._addIntfaceToBridge(b[3:], b)

        # do not start ovs-vswitchd while
        # there is no bridges.
        if len(brs) == 0:
            self.ovs.stop()
        else:
            self.ovs.start()
            self._nicBackendGC()

    def addNormalIfToBr(self, interface, bridgeName):
        raise OvsError("Not implemented")

    def addVfLagToBr(self, bondName, bridgeName):
        raise OvsError("Not implemented")

    def addDpdkBondToBr(self, bondName, bridgeName):
        raise OvsError("Not implemented")

    def addOvsBondToBr(self, bondName, bridgeName):
        raise OvsError("Not implemented")

    def addKernalBondToBr(self, bondName, bridgeName):
        raise OvsError("Not implemented")

    def _addIntfaceToBridge(self, interface, bridgeName):
        ifType = self.getBondType(interface).value

        if ifType == BondType.NormalIface.value:
            self.addNormalIfToBr(interface, bridgeName)
        elif ifType == BondType.KernelBond.value:
            self.addKernalBondToBr(interface, bridgeName)
        elif ifType == BondType.DpdkBond.value:
            self.addDpdkBondToBr(interface, bridgeName)
        elif ifType == BondType.OvsBond.value:
            self.addOvsBondToBr(interface, bridgeName)
        elif ifType == BondType.VfLag.value:
            self.addVfLagToBr(interface, bridgeName)
        else:
            raise OvsError("Unexpected bond type.")

    def isInterfaceExist(self, interface, bridgeName):
        if bridgeName not in self.listBrs():
            return False
        if interface not in self.listPorts(bridgeName):
            return False
        return True        

    @checkOvs
    def prepareBridge(self, interface, bridgeName):
        if self.isInterfaceExist(interface, bridgeName):
            return
        try:
            self.createBr(bridgeName)
            self._addIntfaceToBridge(interface, bridgeName)
            self.ovs.restartSwitch()
        except OvsError:
            self.deleteBr(bridgeName)
            raise

    def configDpdkForOvs(self):
        pass

    def convertOvsConfigByVersion(self):
        pass

    @lock.lock('reconfigOvs')
    def reconfigOvs(self):
        try:
            if not self.ovs.isOvsProcRunning("ovsdb-server"):
                self.ovs.startDB()

            if self.isDpdkReady:
                self.configDpdkForOvs()
                self.convertOvsConfigByVersion(self.venv.dpdkVer)
            else:
                logger.debug("ovs do not support dpdk.")

            self.configLacpFallbackAbForOvs()
            self.reconfigOvsBridge()
        except OvsError as err:
            self.deleteBrs()
            self.clearOvsConfig()
            raise
        except Exception as err:
            raise OvsError(str(err))

    @checkOvs
    def createNicBackend(self, vmUuid, nic):
        raise OvsError("Not implemented")

    @checkOvs
    def destoryNicBackend(self, vmUuid, specificNic=None):
        raise OvsError("Not implemented")


class OvsDpdkCtl(OvsBaseCtl):
    def __init__(self):
        super(OvsDpdkCtl, self).__init__()
        self.dpdkOpen = True
        self._initDpdk()

    def _initDpdk(self):
        if self.ovs._getDpdkInitStates():
            return
        self._startOpenvSwitchDataBase()
        self._configOpenvSwitchIfReady()

    def _startOpenvSwitchDataBase(self):
        if not self.ovs.isOvsProcRunning("ovsdb-server"):
            self.ovs.startDB()

    def _configOpenvSwitchIfReady(self):
        if self.isDpdkReady:
            self.configDpdkForOvs()
            self.convertOvsConfigByVersion(self.venv.dpdkVer)

    def _clearSriovVfs(self, bdf):
        numvfs = '/sys/bus/pci/devices/{}/sriov_numvfs'.format(bdf)
        confirmWriteSysfs(numvfs, "0")

    def _splitSriovToMax(self, bdf):
        numvfs = '/sys/bus/pci/devices/{}/sriov_numvfs'.format(bdf)
        totalvfs = readSysfs(
            '/sys/bus/pci/devices/{}/sriov_totalvfs'.format(bdf))
        confirmWriteSysfs(numvfs, totalvfs)

    @linux.retry(times=3, sleep_time=3)
    def _resplitVfs(self, bdf):
        try:
            self._clearSriovVfs(bdf)
            self._splitSriovToMax(bdf)
        except OvsError as err:
            raise OvsError("resplit vfs failed. {}".format(err))

    def _getVfToBdfMap(self, bdf):
        """
        vfsDict{'virtfnx', '0000:65:00.1'}
        """

        devicePath = "/sys/bus/pci/devices/{}/".format(bdf)
        vfToBDF = {}
        for vf in os.listdir(devicePath):
            if vf.startswith("virtfn"):
                bdf = os.path.realpath(devicePath + vf).split("/")[-1]
                vfToBDF[vf] = bdf

        return vfToBDF

    def _unbindVfs(self, pfBdf):
        devicePath = '/sys/bus/pci/devices/{}/'.format(pfBdf)
        unbindPath = '/sys/bus/pci/devices/{}/driver/unbind'.format(pfBdf)

        vfToBDF = self._getVfToBdfMap(pfBdf)
        for i in vfToBDF:
            writeSysfs(unbindPath, vfToBDF[i])
            # wait unbind finished, It may take some time to unbind VFS
            for _ in range(0, 5):
                if os.path.exists(os.path.join(devicePath, i, "driver")):
                    time.sleep(0.5)

    def _bindVfs(self, pfBdf):
        devicePath = '/sys/bus/pci/devices/{}/'.format(pfBdf)
        bindPath = '/sys/bus/pci/devices/{}/driver/bind'.format(pfBdf)

        vfToBDF = self._getVfToBdfMap(pfBdf)
        for i in vfToBDF:
            if not os.path.exists(os.path.join(devicePath, i, "driver")):
                writeSysfs(bindPath, vfToBDF[i], True)
            # wait bind finished, It will take some time
            for _ in range(0, 5):
                if not os.path.exists(os.path.join(devicePath, i, "driver")):
                    time.sleep(0.5)

    def _changeDevlinkMode(self, bdf, mode="switchdev"):
        try:
            ifName = getInterfaceOfBDF(bdf)
            devlink_mode = '/sys/class/net/{}/compat/devlink/mode'.format(
                ifName)
            numvfs = '/sys/bus/pci/devices/{}/sriov_numvfs'.format(bdf)
            totalvfs = readSysfs(
                '/sys/bus/pci/devices/{}/sriov_totalvfs'.format(bdf))

            if readSysfs(devlink_mode, True) == mode and readSysfs(numvfs, True) == totalvfs:
                return

            iproute.set_link_down_no_error(ifName)

            self._resplitVfs(bdf)
            # unbind vfs before change devlink mode
            self._unbindVfs(bdf)
            confirmWriteSysfs(devlink_mode, mode)
            self._bindVfs(bdf)

            iproute.set_link_up_no_error(ifName)
            logger.debug("set {} for {} success.".format(mode, bdf))
        except OvsError as err:
            logger.error(
                "Change devlink mode for device bdf:{} failed. {}".format(bdf, err))
            raise

    def _getOvsDpdkExtra(self):
        try:
            dpdkExtra = shell.call(CtlBin +
                                   "get Open_vSwitch . other_config:dpdk-extra").strip().strip('\n').strip('"')
            return dpdkExtra
        except Exception:
            return ''

    def _configDpdkExtraForOvs(self, bdf):
        try:
            dpdkExtra = self._getOvsDpdkExtra()
            if bdf in dpdkExtra:
                return

            if version_geq(self.venv.dpdkVer, "20.11"):
                dpdkExtra = dpdkExtra + \
                    "-a {},representor=[0-127],dv_flow_en=1,dv_esw_en=1 ".format(
                        bdf)
            else:
                dpdkExtra = dpdkExtra + \
                    "-w {},representor=[0-127],dv_flow_en=1,dv_esw_en=1 ".format(
                        bdf)

            shell.run(
                CtlBin + '--no-wait set Open_vSwitch . other_config:dpdk-extra="{}"'.format(dpdkExtra))
        except shell.ShellError as err:
            raise OvsError(
                "Set dpdk wihite list for pci:{} failed, {}".format(bdf, err))

    def addNormalIfToBr(self, interface, bridgeName):
        bdf = getBDFOfInterface(interface)
        self._changeDevlinkMode(bdf)
        self._configDpdkExtraForOvs(bdf)
        if bridgeName not in self.listBrs():
            raise OvsError("Can not find bridge:{} in ovs.".format(bridgeName))

        if interface not in self.listPorts(bridgeName):
            self.addPort(bridgeName, interface, "dpdk",
                         "dpdk-devargs={}".format(bdf))

    def addVfLagToBr(self, bondName, bridgeName):
        slavesPath = "/sys/class/net/{}/bonding/slaves".format(bondName)

        if not os.path.exists(slavesPath):
            raise OvsError(
                "Can not find file:{}, please check the bond settings.".format(slavesPath))

        interfaces = self._getBondSlaves(bondName)
        interfaceBDFs = [getBDFOfInterface(i) for i in interfaces]
        interfaceBDs = set()
        interfacePciIds = set()

        for bdf in interfaceBDFs:
            interfaceBDs.add(bdf.split(".")[0])
            interfacePciIds.add(getPciID(bdf))

        if len(interfacePciIds) != 1 or len(interfaceBDs) != 1:
            raise OvsError(
                "The pfs under vflag should come from the same nic.")

        if interfacePciIds[0] not in self.venv.offloadStatus.keys():
            raise OvsError("Device:{} not in support vf lag list {}."
                           .format(interfacePciIds[0], self.venv.offloadStatus.keys()))

        for i in interfaces:
            self._changeDevlinkMode(i)
            self._configDpdkExtraForOvs(i)

        if bridgeName not in self.listBrs():
            raise OvsError("Can not find bridge:{} in ovs.".format(bridgeName))

        if bondName not in self.listPorts(bridgeName):
            # To work with VF-LAG with OVS-DPDK, add the bond master (PF) to the bridge. Note that the first
            # PF on which you run "ip link set <PF> master bond0" becomes the bond master.
            self.addPort(bridgeName, bondName, "dpdk",
                         "dpdk-devargs={}".format(interfaces[0]),
                         "dpdklsc-interrupt=true")

    def _bindDpdkDriverToDevice(self, pciNum, drvName=None):

        if drvName is None:
            drvName = "vfio-pci"

        bindPath = '/sys/bus/pci/drivers/{}/bind'.format(drvName)
        unbindPath = '/sys/bus/pci/devices/{}/driver/unbind'.format(pciNum)
        overridePath = '/sys/bus/pci/devices/{}/driver_override'.format(pciNum)
        newidPath = "/sys/bus/pci/drivers/{}/new_id".format(drvName)
        deviceDriverPath = "/sys/bus/pci/drivers/{}/{}".format(drvName, pciNum)

        # check whether driver module exists,
        # if not modprobe it.
        if not os.path.exists(bindPath):
            probeModules(drvName)
            if not os.path.exists(bindPath):
                logger.warn("can not probe module {}.".format(drvName))

        # check if already using driver
        if os.path.exists(deviceDriverPath):
            return

        # unbind old driver if exists.
        if os.path.exists(unbindPath):
            writeSysfs(unbindPath, str(pciNum))
            time.sleep(0.5)

        # For kernel >= 3.15 driver_override can be used to specify the driver
        # for a device rather than relying on the driver to provide a positive
        # match of the device.
        if os.path.exists(overridePath):
            writeSysfs(overridePath, str(drvName))
        else:
            vd = getPciID(pciNum)
            writeSysfs(newidPath, vd[:4]+' '+vd[4:])

        # do the bind
        for _ in range(0, 3):
            # check if module probed
            if not os.path.exists(deviceDriverPath):
                writeSysfs(bindPath, str(pciNum))
            else:
                break

        # clear override
        if os.path.exists(overridePath):
            writeSysfs(overridePath, "\00")

    def _prepareSlaves(self, slaves):
        for bdf in slaves:
            # Mlnx nics is driverd by mlx5_core, but other nics use vfio-pci instead.
            # For mlnx nics they do not need to change driver,
            # but the others need change driver to vfio-pci/igb_uio/uio_pci_generic.
            if getPciID(bdf) not in self.venv.offloadStatus.keys():
                self._bindDpdkDriverToDevice(bdf)
            else:
                self._changeDevlinkMode(bdf)
            self._configDpdkExtraForOvs(bdf)

    def _convertIfToBDF(self, rawSlaves):
        slaves = []
        for i in rawSlaves:
            if not isBDF(i):
                slaves.append(getBDFOfInterface(i))
            else:
                slaves.append(i)

        return slaves

    def addDpdkBondToBr(self, bondName, bridgeName):
        bond = OvsDpdkCtl.getBondFromFile(bondName)
        slaves = self._convertIfToBDF(bond.slaves)

        if len(slaves) < 2:
            raise OvsError(
                "Number of slaves in dpdk bond:{} should >=2".format(bond.name))

        self._prepareSlaves(slaves)

        if bridgeName not in self.listBrs():
            raise OvsError("Can not find bridge:{} in ovs.".format(bridgeName))

        if bond.name in self.listPorts(bridgeName):
            return

        # ovs-vsctl add-port br_test bondtest -- \
        # set Interface bondtest type=dpdk dpdk-devargs="eth_bond0,mode=2,\
        # slave=0000:81:00.1,slave=0000:82:00.1,xmit_policy=l34"
        dpdk_devargs = "eth_bond{},".format(bond.id)
        dpdk_devargs = dpdk_devargs + "mode={}".format(bond.mode)
        for pci in bond.slaves:
            dpdk_devargs = dpdk_devargs + \
                ",slave={}".format(pci)
        # There are 3 supported transmission policies for bonded device
        # running in Balance XOR mode.
        if bond.mode == 2 and bond.policy is not None:
            dpdk_devargs = dpdk_devargs + \
                ",xmit_policy={}".format(bond.policy)
        dpdk_devargs = "dpdk-devargs={}".format(dpdk_devargs)

        self.addPort(bridgeName, bond.name, "dpdk", dpdk_devargs)

    def addOvsBondToBr(self, bondName, bridgeName):
        bond = OvsDpdkCtl.getBondFromFile(bondName)
        slaves = self._convertIfToBDF(bond.slaves)

        if len(slaves) < 2:
            raise OvsError(
                "Number of slaves in dpdk bond:{} should >=2".format(bond.name))

        self._prepareSlaves(slaves)

        if bridgeName not in self.listBrs():
            raise OvsError("Can not find bridge:{} in ovs.".format(bridgeName))

        if bond.name in self.listPorts(bridgeName):
            return

        # ovs-vsctl add-bond [brname] [bondname] [pf0] [pf1] bond_mode=[bondmode] [lacp=]\
        # -- set Interface [pf0] type=dpdk options:dpdk-devargs=0000:17:00.0 \
        # -- set Interface [pf1] type=dpdk options:dpdk-devargs=0000:17:00.1
        cmd = CtlBin + \
            '--no-wait add-bond {} {} '.format(bridgeName, bond.name)

        pfName = ''
        ifceSet = ''
        count = 0
        for pci in slaves:
            pfName = pfName + '{}_pf{} '.format(bond.name, count)
            ifceSet = ifceSet + \
                '-- set Interface {}_pf{} type=dpdk options:dpdk-devargs={} '.format(
                    bond.name, count, pci)
            count = count + 1

        cmd = cmd + pfName
        cmd = cmd + 'bond_mode={} '.format(bond.mode)
        if bond.mode == 'balance-tcp':
            cmd = cmd + 'lacp={} '.format(bond.lacp)
        cmd = cmd + ifceSet

        shell.call(cmd)

    @linux.retry(times=3, sleep_time=1)
    def configDpdkForOvs(self):
        """
        config ovs dpdk, open hardware offload, init dpdk  and so on.
        """
        if not self.dpdkSup:
            raise OvsError("This openvswitch do not support dpdk.")

        shell.run(CtlBin +
                  "--no-wait set Open_vSwitch . other_config:hw-offload=true")
        shell.run(CtlBin +
                  "--no-wait set Open_vSwitch . other_config:dpdk-init=true")

        # TODO: allocate hugepages to the numa nodes whitch attached dpdk device.
        # TODO: allocate hugepages depends on MTU size.
        memSize = self.venv.nr_hugepages * self.venv.hugepage_size / 1024  # MB
        dpdkSocketMem = ','.join([str(memSize)
                                 for _ in range(0, self.venv.numaNodes)])
        cmd = "--no-wait set Open_vSwitch . other_config:dpdk-socket-mem={}".format(
            dpdkSocketMem)
        shell.run(CtlBin + cmd)

        if not self.ovs.checkOvsConfiguration("hw-offload", "true") or \
           not self.ovs.checkOvsConfiguration("dpdk-init", "true") or \
           not self.ovs.checkOvsConfiguration("dpdk-socket-mem", dpdkSocketMem):
            raise OvsError("Config dpdk for ovs failed.")

    @linux.retry(times=3, sleep_time=1)
    def convertOvsConfigByVersion(self, version):
        """
        reconfig Open_vSwitch if ovs version changed
        """

        dpdkExtra = self._getOvsDpdkExtra()

        if dpdkExtra == '':
            return

        if version_geq(version, "20.11"):
            dpdkExtra = dpdkExtra.replace("-w", "-a")
            dpdkExtra = dpdkExtra.replace("dv_xmeta_en=1", "")
        else:
            dpdkExtra = dpdkExtra.replace("-a", "-w")

        ret = shell.run(CtlBin +
                        '--no-wait set Open_vSwitch . other_config:dpdk-extra="{}"'.format(dpdkExtra))
        if ret != 0:
            raise OvsError(
                "Convert ovs configuration by version failed. version:{}".format(version))

        if not self.ovs.checkOvsConfiguration("dpdk-extra", dpdkExtra):
            raise OvsError("Set ovs dpdk-extra configuration failed.")

    def createNic(self, nic):
        bridgeName = nic.bridgeName
        nicInternalName = nic.nicInternalName
        self.addPort(bridgeName, nicInternalName)

    def createVdpa(self, nic, sockPath):
        bridgeName = nic.bridgeName
        nicInternalName = nic.nicInternalName
        vfpci = nic.pciDeviceAddress
        queueNum = str(nic.vHostAddOn.queueNum) if nic.vHostAddOn.queueNum is not None else '1'

        pfSysinfo = "/sys/bus/pci/devices/{}/physfn".format(vfpci)
        pfpci = os.path.realpath(pfSysinfo).split("/")[-1]

        try:
            representor = None
            tmp_list = os.listdir(pfSysinfo)
            for vf in tmp_list:
                if vf.startswith("virtfn") and vfpci == os.path.realpath(pfSysinfo + "/" + vf).split("/")[-1]:
                    representor = vf[6:]

            if representor is None:
                OvsError(
                    "vf:{} is not the virtual function of pf:{}".format(vfpci, pfpci))

            # check if vf has been used
            s = shell.call(
                CtlBin + "--columns=name find interface options:vdpa-accelerator-devargs='{}'".format(vfpci.replace(":", "\:")))
            if 'name' in s:
                raise OvsError("vf:{} was already used by vnic:{}".format(
                    vfpci, s.strip().strip('"')))

            self.addPort(bridgeName, nicInternalName, "dpdkvdpa",
                         "vdpa-socket-path={}".format(sockPath),
                         "vdpa-accelerator-devargs={}".format(vfpci),
                         "dpdk-devargs={},representor=[{}]".format(
                             pfpci, representor),
                         "vdpa-max-queues=8",
                         "n_rxq={}".format(queueNum),
                         "vdpa-sw=true")
        except shell.ShellError as err:
            raise OvsError(str(err))

    def createDpdkVhostUserClient(self, nic, sockPath):
        bridgeName = nic.bridgeName
        nicInternalName = nic.nicInternalName
        self.addPort(bridgeName, nicInternalName, "dpdkvhostuserclient",
                     "vhost-server-path={}".format(sockPath))

    def _cleanSocket(self, sockPath):
        try:
            os.remove(sockPath)
        except OSError:
            if not os.path.exists(sockPath):
                return
            raise

    def _doCreateBackend(self, vmUuid, nic, sockPath):
        vlanId = nic.vlanId
        vNicName = nic.nicInternalName
        type = nic.type

        self._cleanSocket(sockPath)

        if type == "vNic":
            self.createNic(nic)
        elif self.isDpdkReady:
            if type == "vDPA":
                self.createVdpa(nic, sockPath)
            elif type == "dpdkvhostuserclient":
                self.createDpdkVhostUserClient(nic, sockPath)
            else:
                raise OvsError("Do not support vnic type:{}".format(type))
        else:
            raise OvsError("Do not support vnic type:{}".format(type))

        if vlanId is not None:
            self.setPort(vNicName, vlanId)

        self.setIfaces(vNicName, "external_ids:vm-id={}".format(vmUuid))

    def createNicBackend(self, vmUuid, nic):
        bridgeName = nic.bridgeName
        pNicName = nic.physicalInterface
        type = nic.type
        vNicName = nic.nicInternalName
        sockDirPath = os.path.join(SockPath, type.lower(), vmUuid)
        sockPath = os.path.join(sockDirPath, vNicName)

        try:
            if bridgeName not in self.listBrs():
                raise OvsError(
                    "Can not find bridge:{} in ovs.".format(bridgeName))

            curPorts = self.listPorts(bridgeName)
            if pNicName not in curPorts:
                raise OvsError(
                    "Port:{} does not exists. Please create it firstly".format(pNicName))
            if not os.path.exists(sockDirPath):
                os.makedirs(sockDirPath, 0o755)

            if "vDPA" in type:
                options = "vdpa-socket-path"
            elif "dpdkvhostuserclient" in type:
                options = "vhost-server-path"
            else:
                raise OvsError("Unsupport vnic type:{}".format(type))

            if vNicName in curPorts:
                s = shell.call(
                    CtlBin + "get Interface {} options:{}".format(vNicName, options)).strip()[1:-1]

                if s != '' and sockPath != s:
                    raise OvsError("same vnic in different vm.")
            else:
                self._doCreateBackend(vmUuid, nic, sockPath)

            return sockPath
        except shell.ShellError as err:
            raise OvsError(
                "nic interface {} maybe not a {} type. {}".format(vNicName, type, err))
        except OSError as err:
            raise OvsError(str(err))

    def _listIfacesByVmUuid(self, vmUuid):
        try:
            interfaces = shell.call(CtlBin +
                                    "--columns=name find interface external_ids:vm-id={} | grep name |cut -d ':' -f2 | tr -d ' '".format(vmUuid))
            return interfaces.strip().splitlines()
        except shell.ShellError as err:
            raise OvsError(
                "Find interface by vm uuid:{} failed. {}".format(vmUuid, err))

    def _getInterfacesSockByName(self, nicName):
        try:
            sockPath = ''
            # get nic type
            type = shell.call(
                CtlBin + "get interface {} type".format(nicName)).strip()

            if "dpdkvdpa" in type:
                options = "vdpa-socket-path"
            elif "dpdkvhostuserclient" in type:
                options = "vhost-server-path"
            else:
                return sockPath

            sockPath = shell.call(CtlBin +
                                  "get interface {} options:{}".format(nicName, options)).strip().strip('"')
            return sockPath
        except shell.ShellError as err:
            raise OvsError(
                "Get interface sock path by name:{} failed. {}".format(nicName, err))

    def destoryNicBackend(self, vmUuid, specificNic=None):
        sockPath = ''
        interfaceList = []

        if specificNic != None:
            sockPath = self._getInterfacesSockByName(specificNic)
            interfaceList.append(specificNic)
        else:
            # free all vNics belongs to vm
            interfaceList = self._listIfacesByVmUuid(vmUuid)

        for br in self.listBrs():
            tmpList = []
            for intface in interfaceList:
                if intface in self.listIfaces(br):
                    self.delPort(br, intface)
                    tmpList.append(intface)
            interfaceList = list(set(interfaceList).difference(set(tmpList)))

        return sockPath


class OvsKernelCtl(OvsBaseCtl):

    def __init__(self):
        super(OvsKernelCtl, self).__init__()

    def addNormalIfToBr(self, interface, bridgeName):
        bdf = getBDFOfInterface(interface)
        self._changeDevlinkMode(bdf)
        if bridgeName not in self.listBrs():
            raise OvsError("Can not find bridge:{} in ovs.".format(bridgeName))

        if interface not in self.listPorts(bridgeName):
            self.addAnonymousPort(bridgeName, interface)

    def addKernalBondToBr(self, bondName, bridgeName):
        slavesPath = "/sys/class/net/{}/bonding/slaves".format(bondName)

        if not os.path.exists(slavesPath):
            raise OvsError(
                "Can not find file:{}, please check the bond settings.".format(slavesPath))

        interfaces = self._getBondSlaves(bondName)
        interfaceBDFs = [getBDFOfInterface(i) for i in interfaces]
        interfaceBDs = set()
        interfacePciIds = set()

        for bdf in interfaceBDFs:
            interfaceBDs.add(bdf.split(".")[0])
            interfacePciIds.add(getPciID(bdf))

        if bridgeName not in self.listBrs():
            raise OvsError("Can not find bridge:{} in ovs.".format(bridgeName))

        if bondName not in self.listPorts(bridgeName):
            self.addAnonymousPort(bridgeName, bondName)

    def addOvsBondToBr(self, bondName, bridgeName):
        bond = OvsDpdkCtl.getBondFromFile(bondName)
        slaves = self._getBondSlaves(bondName)

        if len(slaves) < 2:
            raise OvsError(
                "Number of slaves in dpdk bond:{} should >=2".format(bond.name))

        if bridgeName not in self.listBrs():
            raise OvsError("Can not find bridge:{} in ovs.".format(bridgeName))

        if bond.name in self.listPorts(bridgeName):
            return

        # ovs-vsctl add-bond [brname] [bondname] [slave0] [slave1] bond_mode=[bondmode] [lacp=]
        cmd = CtlBin + \
            '--no-wait add-bond {} {} '.format(bridgeName, bond.name)

        pfName = ' '.join(slave for slave in slaves)

        cmd = cmd + pfName
        cmd = cmd + 'bond_mode={} '.format(bond.mode)
        if bond.mode == 'balance-tcp':
            cmd = cmd + 'lacp={} '.format(bond.lacp)

        shell.call(cmd)

    def createNicBackend(self, vmUuid, nic):
        raise OvsError("Not implemented")

    def destoryNicBackend(self, vmUuid, specificNic=None):
        raise OvsError("Not implemented")


def getOvsCtl(with_dpdk=None):
    try:
        if with_dpdk:
            return OvsDpdkCtl()
        else:
            return OvsKernelCtl()
    except OvsError as err:
        logger.error("Get Ovs controller failed. {}".format(err))
        raise

def isVmUseOpenvSwitch(vmUuid):
    try:
        vmInterfaceList = shell.call("virsh domiflist {}".format(vmUuid)).strip()
        if "vhostuser" in vmInterfaceList:
            return True
        return False
    except shell.ShellError as err:
        raise OvsError("Failed to check if vm {} attached with OpenvSwitch.".format(vmUuid))
