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
from zstacklib.utils import thread
from zstacklib.utils import http

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

BridgeAndPfExist = 0
BridgeExistPfNotExist = 1
BridgeNotExist = 2 

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
        pciId = getPciID(interfaceName)
        offloadStatus = getMlnxSmartNicOffloadStatus()
        if pciId in offloadStatus.keys():
            return offloadStatus[pciId]
        return None
    except Exception as err:
        logger.debug("Get offload status failed. {}".format(err))


def getMlnxSmartNicOffloadStatus():
    nicInfoPath = os.path.join(ConfPath, "smart-nics.yaml")
    if not os.path.exists(nicInfoPath):
        raise OvsError("no such file:{}".format(nicInfoPath))

    with open(nicInfoPath, 'r') as f:
        data = yaml.safe_load(f)
    offloadStatus = {}
    for i in data:
        offloadStatus[str(i['nic']['vendor_device'])] = "|".join(
            str(x) for x in i['nic']['offloadstatus'])
    return offloadStatus

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
        logger.debug("make work dir for dpdkovs")
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


    def allocateHugepageMemForOvs(self, hugepage_nr, hugepage_unit, socket_mem):
        rollback_hugepagesPath = []
        rollback_osCurrentnrHugepages = []
        try:
            numaNodePaths = glob.glob("/sys/devices/system/node/node*/")
            if self.numaNodes < 1:
                logger.error("can not find numa node.")
                return -1

            cmd = "--no-wait set Open_vSwitch . other_config:dpdk-socket-mem=" 
            for numaNodePath in numaNodePaths:
                hugepagesPath = os.path.join(
                    numaNodePath, self.hugepagesPaths[int(hugepage_unit)])
                rollback_hugepagesPath.append(hugepagesPath)               
 
                osCurrentfreeHugepages = int(
                    readSysfs(os.path.join(hugepagesPath, "free_hugepages")))
                osCurrentnrHugepages = int(
                    readSysfs(os.path.join(hugepagesPath, "nr_hugepages")))
                rollback_osCurrentnrHugepages.append(osCurrentnrHugepages)    

                #OS free memory unit KB
                memFree = self._getFreeMemByNode(numaNodePath)
                            
                needAllocateHugepageNr = hugepage_nr + osCurrentnrHugepages
    
                if memFree < needAllocateHugepageNr * hugepage_unit:
                    logger.error("not enough hugepage for ovs dpdk, os free memory {} but dpdk need {}.".format(
                        memFree, needAllocateHugepageNr * hugepage_unit))
                    return -1
                #logger.debug("{}".format(needAllocateHugepageNr))
                writeSysfs(os.path.join(hugepagesPath, "nr_hugepages"), str(needAllocateHugepageNr), True)

                cmd = cmd + str(socket_mem)
                cmd = cmd + ","

            shell.run(CtlBin + cmd[0:-1])

            return 0
        except Exception as err:
            for i in range(len(rollback_hugepagesPath)):
                writeSysfs(os.path.join(rollback_hugepagesPath[i], "nr_hugepages"), str(rollback_osCurrentnrHugepages[i]), True)
            
            logger.error("Unpredictable error:{}".format(err))
            return -1

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
            raise OvsError("Set OS informations to ovsdb failed.")

    @lock.lock('startDB')
    def startDB(self):
        if self.isOvsProcRunning("ovsdb-server"):
            return

        #self.stopDB()
        self.upgradeDB()

        cmd = "ovsdb-server {}".format(CONF_DB) \
            + " -vconsole:emer -vsyslog:err -vfile:err" \
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

        #self.stopSwitch()

        #if self._getDpdkInitStates():
        #    self.venv.allocateHugepageMem()

        cmd = "ulimit -n 1000000 && ovs-vswitchd unix:{}".format(DB_SOCK) \
            + " -vconsole:emer -vsyslog:err -vfile:err" \
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
        try:
            shell.check_run(CtlBin + 'add-br {} -- set Bridge {} datapath_type=netdev'.format(
                brName, brName, "netdev"))
        except Exception as err:
            logger.error(
                "Create ovs bridges {} failed. {}".format(brName, err))
            raise OvsError(str(err))

    @lock.lock("ovs_global_config")
    def prepareDeleteBr(self, br):
        if self.deleteBr(br) != 0:
            return -1 
        if self.restoreNicBeforeDeleteBr(br) != 0:
            return -1
        return 0


    def initNicBeforeCreateBr(self, nicName, ispciAddress = 0):
        try:
            if ispciAddress == 0:
                bdf = getBDFOfInterface(nicName)
            else:
                bdf = nicName

            numvfs = '/sys/bus/pci/devices/{}/sriov_numvfs'.format(bdf)
            vfnum = readSysfs(numvfs)
            if int(vfnum) == 0:
                logger.error("nicName:{} vfnum:{}, sriov first".format(nicName, vfnum))
                return -1

            #reboot eswitch mode will be set to legacy
            #sriov_numvfs will be set by zstack mn node, before this fun call
            #clear random data 
            confirmWriteSysfs(numvfs, "0")
            shell.call("devlink dev eswitch set pci/{} mode {}".format(bdf, "legacy"))
            confirmWriteSysfs(numvfs, str(vfnum))

            self._unbindVfs(bdf)

            mode="switchdev"
            shell.call("devlink dev eswitch set pci/{} mode {}".format(bdf, mode))
            ret = shell.call("devlink dev eswitch show pci/{}".format(bdf))
            if mode not in ret:
                logger.error("devlink dev set eswitch mode {} for {} failed.".format(mode, bdf))
                return -1

            self._bindVfs(bdf)

            self._configDpdkExtraForOvs(bdf)

            if ispciAddress == 0:
                self.ovs.restart()

            return 0
        except OvsError as err:
            logger.error(
                "smartnic init for device :{} failed. {}".format(nicName, err))
            return -1

    def restoreNicBeforeDeleteBr(self, br, flag = 0):
        nicName = br[3:]
           
        try:
            bdf = getBDFOfInterface(nicName)

            dpdkExtra = self._getOvsDpdkExtra()
            if bdf not in dpdkExtra:
                logger.debug("device bdf:{} not in dpdk white list".format(bdf))
                return 0

            dpdkWhiteList = dpdkExtra.split("-a")
            dpdkWhiteNewList = []
            for item in dpdkWhiteList:
                if bdf not in item:
                    dpdkWhiteNewList.append(item)

            logger.debug("current dpdk white list:{}".format(dpdkWhiteNewList))
            dpdkExtraNew = ''
            for item in dpdkWhiteNewList:
                if item == '':
                    continue
                dpdkExtraNew = "-a" + item + dpdkExtraNew

            if dpdkExtraNew == '':
                shell.run(CtlBin + "--no-wait remove Open_vSwitch . other_config dpdk-extra")
            else:
                shell.run(CtlBin + '--no-wait set Open_vSwitch . other_config:dpdk-extra="{}"'.format(dpdkExtraNew))

            if flag == 0:
                self.ovs.restart()
            return 0

        except Exception as err:
            logger.error(
                "delete dpdk extra for device :{} failed. {}".format(nicName, err))
            return -1 

    def deleteBr(self, *args):
        try:
            brs = self.listBrs()
            for arg in args:
                if arg in brs:
                    shell.call(CtlBin + "--timeout=5 del-br {}".format(arg))

            bond_info = shell.call("ovs-appctl -t /var/run/openvswitch/ovs-vswitchd.zs.ctl bond/show")
            if bond_info == '':
                if os.path.exists(ConfPath + "bondused"):
                    os.rmdir(ConfPath + "bondused")

            return 0
        except Exception as err:
            logger.error("delete bridge {} failed. {}".format(arg, err))
            return -1

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

    def delPortNoWait(self, brName, phyIfName, *args):
        try:
            shell.call(CtlBin + '--no-wait del-port {} {}'.format(brName, phyIfName))
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
            rawString = shell.call(
                CtlBin + " --columns=name,external_ids find interface external_ids!={}")
            rawData = (rawString + "\n").splitlines()
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
                    self.destoryNicBackendNoWait(nicAndVmUuid[d])
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
            self._nicBackendGC()
            self.ovs.start()

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
            if self.initNicBeforeCreateBr(interface) != 0:
                raise OvsError("init nic :{} failed".format(interface))
            self.addNormalIfToBr(interface, bridgeName)
        elif ifType == BondType.KernelBond.value:
            self.addKernalBondToBr(interface, bridgeName)
        elif ifType == BondType.DpdkBond.value:
            self.addDpdkBondToBr(interface, bridgeName)
        elif ifType == BondType.OvsBond.value:
            bond = OvsDpdkCtl.getBondFromFile(interface)
            for slave in bond.slaves:
                if self.initNicBeforeCreateBr(slave) != 0: 
                    raise OvsError("init nic :{} failed".format(slave))

            self.addOvsBondToBr(interface, bridgeName)
            if not os.path.exists(ConfPath):
                os.mkdir(ConfPath, 0o755)
            if not os.path.exists(ConfPath + "bondused"):
                os.mkdir(ConfPath + "bondused", 0o755)
        elif ifType == BondType.VfLag.value:
            self.addVfLagToBr(interface, bridgeName)
        else:
            raise OvsError("Unexpected bond type.")

    def isInterfaceExist(self, interface, bridgeName):
        if bridgeName not in self.listBrs():
            return BridgeNotExist
        if interface not in self.listPorts(bridgeName):
            return BridgeExistPfNotExist 
        return BridgeAndPfExist 

    @lock.lock("ovs_global_config")
    def prepareBridge(self, interface, bridgeName):
        ret = self.isInterfaceExist(interface, bridgeName)
        if not ret:
            logger.debug("br:{} and interface:{} already exist".format(bridgeName, interface))
            return 0
        return self.addBridge(interface, bridgeName, ret)

    def addBridge(self, interface, bridgeName, flag):
        try:
            if flag == 2:
                self.createBr(bridgeName)
            self._addIntfaceToBridge(interface, bridgeName)
            return 0
        except OvsError:
            self.deleteBr(bridgeName)
            return -1

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

    @checkOvs
    def destoryNicBackendNoWait(self, vmUuid, specificNic=None):
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
            #self.convertOvsConfigByVersion(self.venv.dpdkVer)

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
            """
            # devlink dev eswitch show pci/0000:17:00.1
                pci/0000:17:00.1: mode legacy inline-mode none encap enable
            # devlink dev eswitch set pci/0000:65:00.1 mode switchdev
            """
            devlink_mode = "legacy"
            ret = shell.call("devlink dev eswitch show pci/{}".format(bdf))
            if "switchdev" in ret:
                devlink_mode = "switchdev"
            numvfs = '/sys/bus/pci/devices/{}/sriov_numvfs'.format(bdf)
            totalvfs = readSysfs(
                '/sys/bus/pci/devices/{}/sriov_totalvfs'.format(bdf))

            if devlink_mode == mode and readSysfs(numvfs, True) == totalvfs:
                return

            ifName = getInterfaceOfBDF(bdf)
            iproute.set_link_down_no_error(ifName)

            # create l2 bridge not split vfs
            #self._resplitVfs(bdf)
            # unbind vfs before change devlink mode
            self._unbindVfs(bdf)
            shell.call("devlink dev eswitch set pci/{} mode {}".format(bdf, mode))
            ret = shell.call("devlink dev eswitch show pci/{}".format(bdf))
            if mode not in ret:
                raise Exception("devlink dev set eswitch mode {} for {} failed.".format(mode, bdf))

            self._bindVfs(bdf)
            iproute.set_link_up_no_error(ifName)
            logger.debug("set {} for {} success.".format(mode, bdf))
        except OvsError as err:
            logger.error(
                "Change devlink mode for device bdf:{} failed. {}".format(bdf, err))
            raise

    @lock.lock("ovs-restart and init")
    def smartNicRestore(self, nicName):
        try:
            if "br_" + nicName in self.listBrs():
                logger.debug("pf:{} is in use, cannot recover".format(nicName)) 
                return -1          
 
            bdf = getBDFOfInterface(nicName)

            dpdkExtra = self._getOvsDpdkExtra()
            if bdf not in dpdkExtra:
                logger.debug("device bdf:{} not in dpdk white list".format(bdf))
                return 0

            dpdkWhiteList = dpdkExtra.split("-a")
            for item in dpdkWhiteList:
                if bdf in item:
                    dpdkWhiteList.remove(item)
                    break

            dpdkExtraNew = ''
            for item in dpdkWhiteList:
                if item == '':
                    continue
                dpdkExtraNew = "-a" + item

            if dpdkExtraNew == '':
                shell.run(CtlBin + "--no-wait remove Open_vSwitch . other_config dpdk-extra")
            else:
                shell.run(CtlBin + '--no-wait set Open_vSwitch . other_config:dpdk-extra="{}"'.format(dpdkExtraNew))

            self.ovs.restart()

            numvfs = '/sys/bus/pci/devices/{}/sriov_numvfs'.format(bdf)
            
            confirmWriteSysfs(numvfs, "0")
            shell.call("devlink dev eswitch set pci/{} mode {}".format(bdf, "legacy"))
            ret = shell.call("devlink dev eswitch show pci/{}".format(bdf))
            if "legacy" not in ret:
                logger.error("devlink dev set eswitch mode {} for {} failed for restore nic.".format(mode, bdf))
                return -1
             
            return 0

        except OvsError as err:
            logger.error(
                "smartnic restore for device :{} failed. {}".format(nicName, err))
            return -1


    
    @lock.lock("ovs-restart and init")
    def smartNicInit(self, nicName, hugepage_nr, hugepage_unit, socketmem, vfnum_to):
        try:
            bdf = getBDFOfInterface(nicName)
            
            numvfs = '/sys/bus/pci/devices/{}/sriov_numvfs'.format(bdf)
            vfnum = readSysfs(numvfs)
            if int(vfnum) != 0:
                logger.debug("vfnum:{}, already sriov".format(vfnum))
                return -1

            ret = shell.call("devlink dev eswitch show pci/{}".format(bdf))
            if "switchdev" in ret:
                logger.debug("pci:{} already init, if you want init again, must recover first".format(bdf))
                return -1

            #check hugepages
            if not self.ovs.isOvsProcRunning("ovs-vswitchd"):
                hugepagesPaths = {2048: "hugepages/hugepages-2048kB/",
                                  1048576: "hugepages/hugepages-1048576kB/"}
                numaNodePaths = glob.glob("/sys/devices/system/node/node*/")
                for numaNodePath in numaNodePaths:
                    hugepagesPath = os.path.join(
                        numaNodePath, hugepagesPaths[int(hugepage_unit)])
 
                    osCurrentfreeHugepages = int(
                        readSysfs(os.path.join(hugepagesPath, "free_hugepages")))
                    if hugepage_nr > osCurrentfreeHugepages:
                        logger.error("free hugepage num:{} not enough for dpdkovs use num:{}".format(osCurrentfreeHugepages, hugepage_nr))
                        return -1
                
            cmd = "--no-wait set Open_vSwitch . other_config:dpdk-socket-mem="
            numaNodePaths = glob.glob("/sys/devices/system/node/node*/")
            for i in numaNodePaths:
                cmd = cmd + str(socketmem)
                cmd = cmd + ","
            shell.run(CtlBin + cmd[0:-1])
            if not self.ovs.checkOvsConfiguration("dpdk-socket-mem", str(socketmem)):
                logger.error("Config dpdk socket mem for ovs failed.")
                return -1

            #reboot eswitch mode will be set to legacy
            #sriov_numvfs will be set by zstack mn node, before this fun call
            #clear random data 
            #confirmWriteSysfs(numvfs, "0")
            #shell.call("devlink dev eswitch set pci/{} mode {}".format(bdf, "legacy"))
            #confirmWriteSysfs(numvfs, str(vfnum))

            confirmWriteSysfs(numvfs, vfnum_to)
            self._unbindVfs(bdf)

            mode="switchdev"
            shell.call("devlink dev eswitch set pci/{} mode {}".format(bdf, mode))
            ret = shell.call("devlink dev eswitch show pci/{}".format(bdf))
            if mode not in ret:
                logger.error("devlink dev set eswitch mode {} for {} failed.".format(mode, bdf))
                return -1

            self._bindVfs(bdf)

            self._configDpdkExtraForOvs(bdf)
            self.ovs.restart()

            return []
        except OvsError as err:
            logger.error(
                "smartnic init for device :{} failed. {}".format(nicName, err))
            return -1

    @lock.lock("ovs_global_config")
    def resourceConfigure(self, hugepage_nr, hugepage_unit, socket_mem):
        #ovs-vswitchd already running, hugepages already allocated
        if self.ovs.isOvsProcRunning("ovs-vswitchd"):
            logger.warn("ovs-vswitchd already running, hugepages already allocated, no need allacate again")
            return 0

        ret = self.ovs.venv.allocateHugepageMemForOvs(int(hugepage_nr), int(hugepage_unit), socket_mem)     
        if ret != 0:
            return ret

        dpdkExtra = self._getOvsDpdkExtra()
        dpdkWhiteList = dpdkExtra.split("-a")
        for item in dpdkWhiteList:
            if item == "":
                continue
            pci_address = item.split(",")[0].strip()
            if self.initNicBeforeCreateBr(pci_address, 1) != 0:
                return -1
  
        try: 
            self.ovs.restart()
            return 0
        except Exception as err:
            logger.error("Unpredictable error:{}".format(err))
            return -1
        
    
    @lock.lock("ovs_global_config")
    def dpdkOvsSync(self, bridge_info):
        if not self.ovs.isOvsProcRunning("ovs-vswitchd"):
            logger.warn("ovs-vswitchd not running, can't sync bridge info")
            return -1

        if not self.ovs.isOvsProcRunning("ovsdb-server"):
            logger.warn("ovsdb-server not running, can't sync bridge info")
            return -1

        try:
            curr_brs = self.listBrs()
            controldata_brs = []
            for item in bridge_info:
                controldata_brs.append(item.name)
            #delete port not in controldata but in current br
            for item in list(set(curr_brs) - set(controldata_brs)):
                self.deleteBr(item)           
                self.restoreNicBeforeDeleteBr(item) 
                logger.debug("sync delete bridge:{}".format(item))
      
            for item in bridge_info:
                bridgeName = item.name
                
                curr_ports = []
                controldata_ports = []
                #add br in controldata not in current br
                if bridgeName not in curr_brs:
                    logger.debug("sync add bridge:{}".format(bridgeName))
                    self.createBr(bridgeName)

                    if item.phy_type == "bond":
                        bond = OvsDpdkCtl.getBondFromFile(item.physicalInterface)
                        for slave in bond.slaves:
                            if self.initNicBeforeCreateBr(slave) != 0: 
                                raise OvsError("init nic :{} failed".format(slave))
                        self.addOvsBondToBr(item.physicalInterface, bridgeName)
                    else:                    
                        bdf = getBDFOfInterface(item.physicalInterface)
                        if self.initNicBeforeCreateBr(item.physicalInterface) != 0:
                            raise OvsError("init nic :{} failed".format(item.physicalInterface))
                        self.addNormalIfToBr(item.physicalInterface, bridgeName)

                    logger.debug("sync add pf:{}, pf type:{}".format(item.physicalInterface, item.phy_type))

                    for port in item.ports:
                        sockDirPath = os.path.join(SockPath, port.type.lower(), port.vmUuid)
                        sockPath = os.path.join(sockDirPath, port.nicInternalName)
                        self._doCreateBackend(port.vmUuid, port, sockPath)
                        logger.debug("sync add vport:{}".format(port.nicInternalName))
                    
                else:
                    curr_ports = self.listPorts(bridgeName)
                    for port in item.ports:
                        controldata_ports.append(port.nicInternalName)
                    controldata_ports.append(item.physicalInterface)
                    #in per br,delete vport in current br, but not in controldata ports
                    for item_port in list(set(curr_ports) - set(controldata_ports)):
                        self.delPort(bridgeName, item_port)
                        logger.debug("sync delete vport:{}".format(item_port))

                    if item.physicalInterface not in curr_ports:
                        if item.phy_type == "bond":
                            bond = OvsDpdkCtl.getBondFromFile(item.physicalInterface)
                            for slave in bond.slaves:
                                if self.initNicBeforeCreateBr(slave) != 0: 
                                    raise OvsError("init nic :{} failed".format(slave))
                            self.addOvsBondToBr(item.physicalInterface, bridgeName) 
                        else:                    
                            if self.initNicBeforeCreateBr(item.physicalInterface) != 0:
                                raise OvsError("init nic :{} failed".format(item.physicalInterface))
                            self.addNormalIfToBr(item.physicalInterface, bridgeName)
                        logger.debug("sync add pf:{}, pf type:{}".format(item.physicalInterface, item.phy_type))
                         
                    #in per br, add vport in contraldata ports ,but not in current ports
                    for port in item.ports:
                        if port.nicInternalName not in curr_ports:
                            sockDirPath = os.path.join(SockPath, port.type.lower(), port.vmUuid)
                            sockPath = os.path.join(sockDirPath, port.nicInternalName)
                            self._doCreateBackend(port.vmUuid, port, sockPath)
                            logger.debug("sync add vport:{}".format(port.nicInternalName))
                 
            return 0      
        except Exception as err:
            logger.error("Unpredictable error:{}".format(err))
            return -1 
     
    def checkVswitchdHealthStatus(self):
        try:
            shell.call("ovs-appctl -t /var/run/openvswitch/ovs-vswitchd.zs.ctl dpif/dump-dps")
            shell.call("ovs-appctl -t /var/run/openvswitch/ovs-vswitchd.zs.ctl dpif/show")
            return 0
        except Exception as err:
            logger.error("ovs-vswitchd start failed, err:{}".format(err))
            return -1

    def checkOvsConfig(self):
        try:
            shell.call("ovs-vsctl --no-wait get Open_vSwitch . other_config:dpdk-socket-mem")  

            dpdkExtra = self._getOvsDpdkExtra()
            dpdkWhiteList = dpdkExtra.split("-a")
            for item in dpdkWhiteList:
                if item == "":
                    continue
                pci_address = item.split(",")[0].strip()

                numvfs = '/sys/bus/pci/devices/{}/sriov_numvfs'.format(pci_address)
                vfnum = readSysfs(numvfs)
                if int(vfnum) == 0:
                    logger.error("vfnum:{}, test config failed".format(vfnum))
                    return -1

                ret = shell.call("devlink dev eswitch show pci/{}".format(pci_address))
                if "legacy" in ret:
                    logger.error("pci:{} switch mode legacy, test config failed".format(pci_address))
                    return -1

            return 0
        except Exception as err:
            logger.error("test ovs config failed, err:{}".format(err))
            return -1

    @thread.AsyncThread       
    def checkOvsStatusWapper(self):
        os_run_time = int(float(readSysfs("/proc/uptime", True).split(" ")[0]))
        if os_run_time < 600:
            logger.debug("os just boot, os run time : {}".format(os_run_time))
            time.sleep(600 - os_run_time)             
        
        interval = 15 
        ovs_vswitchd_status_extra = 0         
        while True: 
            if http.AsyncUirHandler.STOP_WORLD == True:
                logger.debug("STOP_WORLD is True, check ovs status thread exit")
                break
            try:
                ovs_vswitchd_status_extra = self.checkOvsStatus(ovs_vswitchd_status_extra)
                time.sleep(interval)
            except Exception as err:
                logger.error("pull ovs failed, do it again. err info{}".format(err))
                time.sleep(interval)

    @lock.lock("ovs_global_config")
    def checkOvsStatus(self, ovs_vswitchd_status_extra):
        ovsdb_server_status = 0
        ovs_vswitchd_status = 0
        
        logger.debug("check ovs running status ...")
        if not self.ovs.isOvsProcRunning("ovsdb-server"):
            ovsdb_server_status = 1
        if not self.ovs.isOvsProcRunning("ovs-vswitchd") or ovs_vswitchd_status_extra == 1:
            ovs_vswitchd_status = 1
           
        if ovsdb_server_status == 0 and ovs_vswitchd_status == 0:
            return ovs_vswitchd_status_extra 
            
        if ovsdb_server_status:
            self.ovs.startDB()
            logger.debug("ovsdb-server not running, start sucess")
            ovsdb_server_status = 0
                
        if self.checkOvsConfig() != 0:
            logger.error("ovs config error, can't start it")
            return ovs_vswitchd_status_extra 

        if ovs_vswitchd_status:
            self.ovs.startSwitch()
            if self.checkVswitchdHealthStatus() == 0:
                logger.debug("ovs-vswitchd not running, start sucess")
                ovs_vswitchd_status = 0
                ovs_vswitchd_status_extra = 0
            else:
                ovs_vswitchd_status_extra = 1
                
        return ovs_vswitchd_status_extra


    @thread.AsyncThread       
    def checkBondStatusWapper(self):
        while True:
            if http.AsyncUirHandler.STOP_WORLD == True:
                logger.debug("STOP_WORLD is True, check bond status thread exit")
                break
    
            logger.debug("check ovs bond port status ...")
            self.checkBondStatus()
            time.sleep(15)   
 
    def checkBondStatus(self):
        if not os.path.exists(ConfPath + "bondused"): 
            return 0

        if not self.ovs.isOvsProcRunning("ovs-vswitchd"):
            logger.warn("ovs-vswitchd not running, no need to check bond status")
            return -1
        
        if not self.ovs.isOvsProcRunning("ovsdb-server"):
            logger.warn("ovsdb-server not running, no need to check bond status")
            return -1

        try:
            all_brs = self.listBrs()
            if len(all_brs) <= 0:
                return 0

            bond_info = shell.call("ovs-appctl -t /var/run/openvswitch/ovs-vswitchd.zs.ctl bond/show")
            if bond_info == '':
                return 0

            bond_list_org = bond_info.split("\n")
            bond_list_org = filter(None, bond_list_org)

            bond_list = self._getBondInfoList(bond_list_org, all_brs)
            if len(bond_list) <= 0:
                return 0

            self._syncVdpaForBond(bond_list)

            logger.debug("current brs:{} bondlist:{}, program pid:{}".format(all_brs, bond_list, os.getpid()))


        except Exception as err:
            logger.error("Unpredictable error:{} in checkBondStatus".format(err))
            return -1       

    def _syncVdpaForBond(self, bond_list):
        try:
            for bond in bond_list:
                ports = self.listPorts(bond["br_name"])
                for port in ports:
                    if port == bond["name"]:
                        continue

                    res = eval(shell.call("ovs-vsctl get Interface {} options:dpdk-devargs".format(port)))
                    if res == '':
                        continue

                    reslist = res.split(",")
                    if len(reslist) < 0:
                        continue
                    if bond["active_pf_pci_addr"] == reslist[0]:
                        continue
                    logger.debug(
                       "port:{},portconfig pf_pci_addr:{},bondconfig pf_pci_addr:{}".format(port, reslist[0], bond["active_pf_pci_addr"]))        
                    # sync vdpa for bond
                    self._syncVdpaItem(port, bond, reslist)
  
            return 0
        except Exception as err:
            logger.error("Unpredictable error:{} in syncVdpaForBond".format(err))
            return -1       

    def _syncVdpaItem(self, port, bond, reslist):
        bridgeName = bond["br_name"]
        nicInternalName = port
        representor = reslist[1].split("=")[1][1:-1]
        pfpci = bond["active_pf_pci_addr"]

        vfpcipath = "/sys/bus/pci/devices/{}/virtfn{}".format(pfpci, representor)
        vfpci = os.path.realpath(vfpcipath).split("/")[-1]

        sockPath = eval(shell.call("ovs-vsctl get Interface {} options:vdpa-socket-path".format(port))).strip()
        vmUuid = sockPath.split("/")[-2]
        vdpaqueues = eval(shell.call("ovs-vsctl get Interface {} options:vdpa-max-queues".format(port))).strip()
        vdpasw = eval(shell.call("ovs-vsctl get Interface {} options:vdpa-sw".format(port))).strip()
        queueNum = eval(shell.call("ovs-vsctl get Interface {} options:n_rxq".format(port))).strip()
        tag = shell.call("ovs-vsctl get Port {} tag".format(port)).strip()
 
        self.delPort(bridgeName, nicInternalName)
        self.addPort(bridgeName, nicInternalName, "dpdkvdpa",
                         "vdpa-socket-path={}".format(sockPath),
                         "vdpa-accelerator-devargs={}".format(vfpci),
                         "dpdk-devargs={},representor=[{}]".format(
                             pfpci, representor),
                         "vdpa-max-queues={}".format(vdpaqueues),
                         "n_rxq={}".format(queueNum),
                         "vdpa-sw={}".format(vdpasw))       
        if tag != '[]':
            self.setPort(nicInternalName, tag)

        self.setIfaces(nicInternalName, "external_ids:vm-id={}".format(vmUuid))
 
        vnic_info = {}
        vnic_info["bridgeName"] = bridgeName
        vnic_info["vnic"] = nicInternalName
        vnic_info["representor"] = representor
        vnic_info["pfpci"] = pfpci
        vnic_info["vfpci"] = vfpci
        vnic_info["sockPath"] = sockPath
        vnic_info["vmUuid"] = vmUuid
        vnic_info["vdpaqueues"] = vdpaqueues
        vnic_info["vdpasw"] = vdpasw
        vnic_info["queueNum"] = queueNum
        vnic_info["tag"] = tag
        logger.debug("sync vdpa port new info:{}".format(vnic_info))

    def _getBridgeFromPort(self, all_brs, port):
        for br in all_brs:
            cur_ports = self.listPorts(br)
            for nic in cur_ports:
                if nic == port:
                    return br


    def _getBondInfoList(self, bond_list_org, all_brs):
        """
        bond_list format:
        [{
	'name': 'dpdkbond',
	'active_pf': 'p1',
	'br_name': 'br-bond',
	'bond_mode': 'active-backup',
	'slaves': [
        {
		'status': 'enabled',
		'name': 'p0',
		'pci_addr': '0000:65:00.0'
	}, 
        {
		'status': 'enabled',
		'active': 1,
		'name': 'p1',
		'pci_addr': '0000:65:00.1'
	}],
	'active_pf_pci_addr': '0000:65:00.1'
        }]
        """
        try:
            bond_list = []
            for item in bond_list_org:
                if "----" in item:
                    itemDict = {}
                    bond_list.append(itemDict)
                    itemDict["name"] = item.split(" ")[1]

                    itemDict["br_name"] = self._getBridgeFromPort(all_brs, itemDict["name"])
                    continue
    
                if "bond_mode" in item:
                    itemDict[item.split(":")[0]] = item.split(":")[1][1:]
                    continue
    
                if "slave" == item[0:5]:
                    if not itemDict.has_key("slaves"):
                        slaveList = []
                    slaveDict = {}
                    slaveDict["status"] = item.split(":")[1][1:]
                    slaveDict["name"] = item.split(":")[0].split(" ")[1]
                    
                    pci_addr = eval(shell.call(" ovs-vsctl get Interface {} options:dpdk-devargs".format(slaveDict["name"]))).strip("\n")
                    slaveDict["pci_addr"] = pci_addr

                    slaveList.append(slaveDict)
                    itemDict["slaves"] = slaveList
                    continue
    
                if "  active" == item[0:8]:
                    itemDict["slaves"][-1]["active"] = 1
                    itemDict["active_pf"] = itemDict["slaves"][-1]["name"]
                    itemDict["active_pf_pci_addr"] = itemDict["slaves"][-1]["pci_addr"]
                    continue
            return bond_list

        except Exception as err:
            logger.error("Unpredictable error:{} in getBondList".format(err))
            return []


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

        #self._prepareSlaves(slaves)

        #if bridgeName not in self.listBrs():
        #    raise OvsError("Can not find bridge:{} in ovs.".format(bridgeName))

        #if bond.name in self.listPorts(bridgeName):
        #    return

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


        if not self.ovs.checkOvsConfiguration("hw-offload", "true") or \
           not self.ovs.checkOvsConfiguration("dpdk-init", "true"): 
            raise OvsError("Config dpdk for ovs failed.")


        shell.run(CtlBin +
                  "--no-wait set Open_vSwitch . other-config:lacp-fallback-ab=true")
        if not self.ovs.checkOvsConfiguration("lacp-fallback-ab", "true"):
            raise OvsError("Config lacp fallback ab for ovs failed.")

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

        queueNum = "1"    
        if nic.vHostAddOn is not None:
            if nic.vHostAddOn.queueNum is not None:
                queueNum = str(nic.vHostAddOn.queueNum)
        
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
   
    def _checkVdpaNum(self):
        vdpa_num = 0
        allbrs = []
        allifs = []

        allbrs = self.listBrs()
        if len(allbrs) == 0:
            logger.debug("dpdkovs already have vdpa num:{}".format(vdpa_num))
            return vdpa_num 

        for br_item in allbrs:
            allifs = self.listIfaces(br_item)
            for if_item in allifs:
                if "vnic" == if_item[0:4]:
                    vdpa_num = vdpa_num + 1

        logger.debug("dpdkovs already have vdpa num:{}".format(vdpa_num))
        return vdpa_num 

    def _getDpdkSocketMem(self):
        try:
            socket_mem = 0
            ret = shell.call(
                CtlBin + "get Open_vSwitch . other_config:dpdk-socket-mem").strip("\n").strip('"')
            #many numa node
            if "," in ret:
                socket_mem = int(ret.split(",")[0])
            else:
                socket_mem = int(ret)
            logger.debug("dpdkovs per socket mem:{}".format(socket_mem))

            return socket_mem
        except shell.ShellError:
            logger.debug("dpdkovs per socket mem:{}, maybe some unexpected error occur")
            return 0

    def _canCreateVdpaOrNotInCurrentConfig(self):
        vdpa = self._checkVdpaNum()
        socket_mem = self._getDpdkSocketMem()
         
        if socket_mem == 0 or socket_mem < 6500:
            return 1

        """
        The memory of dpdk-ovs is based on pre allocation
        During initialization, dpdk-ovs will build two memory pools: memory pool and malloc heap
        The memory pool is mainly used to store data packets read from the network card
        Malloc heap is mainly used to control surface usage, 
        and all final uses malloc_xxx of rte in dpdk-ovs comes from the malloc heap;
        For example, state control information, statistical information,
        virtual network card of vdpa, network bridge, and other interfaces

        Dpdk-ovs uses a two-layer memory mode, first configuring large page memory in the system:
        Echo N>/sys/devices/system/node/node0/hugepages/hugepages 2048kB/nr_ Hugepages
        At this point, the maximum amount of large page memory available for dpdk ovs in the system is N * 2=2N(unit M)
        However, the specific amount of large page memory used in dpdk ovs 
        depends on the value of dpdk socket mem (theoretically less than or equal to 2N);
        We set dpdk socket mem=2N * 0.85 to be rounded
        Why not set dpdk socket mem to 2N here, mainly because
        the large page system of the kernel set in this way may experience instability under special circumstances
        The coefficient of 0.85 is an empirical value

        One vdpa requires approximately 90M of memory:
        Memory pool=70M
        Malloc heap=15M (network card simulation)+5M (status information, statistical information, etc.)

        vdpa number             hugepage number                    socket_mem
        64                      echo 4096 > nr_hugepages           7000 
        128                     echo 8192 > nr_hugepages           14000
        256                     echo 16384 > nr_hugepages          28000
        512                     echo 32768 > nr_hugepages          56000
        """
        if vdpa > 63 and socket_mem < 7000:
            return 1
        if vdpa > 127 and socket_mem < 14000:
            return 1
        if vdpa > 255 and socket_mem < 28000:
            return 1
        if vdpa > 511 and socket_mem < 56000:
            return 1
            
        return 0

    def _doCreateBackend(self, vmUuid, nic, sockPath):
        vlanId = nic.vlanId
        vNicName = nic.nicInternalName
        type = nic.type

        self._cleanSocket(sockPath)

        if type == "vNic":
            self.createNic(nic)
        elif self.isDpdkReady:
            if type == "vDPA":
                if self._canCreateVdpaOrNotInCurrentConfig() != 0:
                    raise OvsError("Do not support continue create vdpa in current dpdkovs env")
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

        if not self.ovs.isOvsProcRunning("ovs-vswitchd"):
            logger.error("create vdpa failed, becauseof ovs-vswitchd not running.")
            return None

        if not self.ovs.isOvsProcRunning("ovsdb-server"):
            logger.error("create vdpa failed, becauseof ovsdb-server not running.")
            return None

        bridgeName = nic.bridgeName
        pNicName = nic.physicalInterface
        type = nic.type
        vNicName = nic.nicInternalName
        sockDirPath = os.path.join(SockPath, type.lower(), vmUuid)
        sockPath = os.path.join(sockDirPath, vNicName)

        try:
            if bridgeName not in self.listBrs():
                logger.debug(
                    "Can not find bridge:{} in ovs.".format(bridgeName))
                return None

            curPorts = self.listPorts(bridgeName)
            if pNicName not in curPorts:
                logger.error(
                    "Port:{} does not exists. Please create it firstly".format(pNicName))
                return None

            if not os.path.exists(sockDirPath):
                os.makedirs(sockDirPath, 0o755)

            if "vDPA" in type:
                options = "vdpa-socket-path"
            elif "dpdkvhostuserclient" in type:
                options = "vhost-server-path"
            else:
                logger.error("Unsupport vnic type:{}".format(type))
                return None

            if vNicName in curPorts:
                s = shell.call(
                    CtlBin + "get Interface {} options:{}".format(vNicName, options)).strip()[1:-1]

                if s != '' and sockPath != s:
                    logger.error("same vnic in different vm.")
                    return None
            else:
                self._doCreateBackend(vmUuid, nic, sockPath)

            return sockPath
        except shell.ShellError as err:
            logger.error(
                "nic interface {} maybe not a {} type. {}".format(vNicName, type, err))
            return None
        except OSError as err:
            logger.error(str(err))
            return None

    def _listIfacesByVmUuid(self, vmUuid):
        try:
            interfaces = shell.call(CtlBin +
                                    "--columns=name find interface external_ids:vm-id={} | grep name |cut -d ':' -f2 | tr -d ' '".format(vmUuid))
            return interfaces.strip().splitlines()
        except shell.ShellError as err:
            logger.warn("Find interface by vm uuid:{} failed. {}".format(vmUuid, err))
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
            logger.warn("Get interface sock path by name:{} failed. {}".format(nicName, err))
            raise OvsError(
                "Get interface sock path by name:{} failed. {}".format(nicName, err))

    def destoryNicBackend(self, vmUuid, specificNic=None):
        if not self.ovs.isOvsProcRunning("ovs-vswitchd"):
            logger.error("delete vdpa failed, becauseof ovs-vswitchd not running.")
            return None

        if not self.ovs.isOvsProcRunning("ovsdb-server"):
            logger.error("delete vdpa failed, becauseof ovsdb-server not running.")
            return None

        try:
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
        except:
            return None


    @lock.lock("ovs-destoryNicBackend")
    def destoryNicBackendNoWait(self, vmUuid, specificNic=None):
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
                    self.delPortNoWait(br, intface)
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

def getAllBondFromFile():
    try:
        bondFile = os.path.join(ConfPath, "dpdk-bond.yaml")

        dpdkbonds = []

        if not os.path.exists(bondFile):
            return dpdkbonds

        with open(bondFile, "r") as f:
            data = yaml.safe_load(f)

        for d in data:
            dpdkBond = Bond()
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
            dpdkbonds.append(dpdkBond)
        return dpdkbonds
    except Exception as e:
        return []







