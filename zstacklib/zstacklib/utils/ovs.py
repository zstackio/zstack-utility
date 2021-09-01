import os
import shutil
import time
import yaml
import glob
import uuid

from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import iproute
from zstacklib.utils import lock
from zstacklib.utils import linux

logger = log.get_logger(__name__)


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


def confirmWriteSysfs(path, value, times=3, sleepTime=3):
    for _ in range(0, times):
        writeSysfs(path, value, True)
        time.sleep(sleepTime)
        if readSysfs(path, True) == value:
            return

    raise OvsError("write sysfs timeout")


class OvsVenv(object):
    """ prepare ovs workspace and env
        including:
        1. mlnx ofed driver
        2. hugepages
        3. offloadStatus of smart-nics
    """
    __cache__ = []  # list[int, OvsVenv]

    DEFAULT_HUGEPAGE_SIZE = 2048
    DEFAULT_NR_HUGEPAGES = 1024 * 2

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
        self.ready = True
        self.checkMlnxOfed()

        self.hugepage_size = hugepage_size
        self.nr_hugepages = nr_hugepages

        self.offloadStatus = {}
        self.checkOffloadStatus()

    def checkMlnxOfed(self):
        """ check mlnx ofed driver,
            get ovs and dpdk version,
            the EAL options between different dpdk version maybe changed
            and old configurations may cause error
        """
        if not os.path.exists("/usr/share/openvswitch/scripts/ovs-ctl"):
            logger.debug("can not find ovs-ctl")
            self.ready = False
            return

        # get ofed_info version
        if not os.path.exists("/usr/bin/ofed_info"):
            logger.debug("can not find ofed_info")
            self.ready = False
            return

        self.ofedVer = shell.call("ofed_info -n").strip()

        # get ovs-vswitch and dpdk version
        if not os.path.exists("/usr/sbin/ovs-vswitchd"):
            logger.debug("can not find ovs-vswitchd")
            self.ready = False
            return

        verList = shell.call(
            "ovs-vswitchd --version | grep -E 'DPDK|vSwitch'").splitlines()
        if len(verList) > 0 and verList[0] != '':
            self.vSwitchVer = verList[0].split()[-1]
        if len(verList) > 1 and verList[1] != '':
            self.dpdkVer = verList[1].split()[-1]

        # get ovsdb-server version
        if not os.path.exists("/usr/sbin/ovsdb-server"):
            logger.debug("can not find ovsdb-server")
            self.ready = False
            return

        self.ovsDBVer = shell.call(
            "ovsdb-server --version | awk 'NR==1{print $NF}'").strip()

    def checkHugepage(self):
        """
        prepare Hugepages for DPDK
        """
        hugepagesPath = {2048: "/sys/kernel/mm/hugepages/hugepages-2048kB/",
                         1048576: "/sys/kernel/mm/hugepages/hugepages-1048576kB/"}

        # get numa nodes
        numaNodes = glob.glob("/sys/devices/system/node/node*/")
        numaNodeSz = len(numaNodes)

        meminfo = {}
        # get current memory status
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
            for l in lines:
                lsplit = l.split(":")
                meminfo[lsplit[0].strip()] = lsplit[1].strip()

        curFreeMemsz = int(meminfo['MemFree'].split()[0])

        # get default free hugepage size
        freeHugepages = int(readSysfs(
            hugepagesPath[self.hugepage_size] + "free_hugepages"))

        if freeHugepages < self.nr_hugepages:
            if curFreeMemsz > (self.nr_hugepages - freeHugepages) * self.hugepage_size:
                writeSysfs(hugepagesPath[self.hugepage_size] +
                           "nr_hugepages", str
                           (self.nr_hugepages * numaNodeSz - freeHugepages))
            else:
                self.ready = False
                logger.debug("can not malloc enough hugepage for ovs.")

    def checkOffloadStatus(self):
        nicInfoPath = os.path.join(
            "/usr/local/etc/zstack-ovs/", "smart-nics.yaml")

        if not os.path.exists(nicInfoPath):
            logger.debug("no such file:{}".format(nicInfoPath))
            self.ready = False
            return

        with open(nicInfoPath, 'r') as f:
            data = yaml.safe_load(f)

        for i in data:
            self.offloadStatus[i['nic']['vendor_device']] = "|".join(
                str(x) for x in i['nic']['offloadstatus'])


class Ovs(object):
    """ control the lifecycle of ovsdb and vswitch
    """

    ovsPath = "/var/run/openvswitch/"
    logPath = "/var/log/zstack/openvswitch/"
    vdpaPath = "/var/run/zstack/vdpa/"
    confPath = "/usr/local/etc/zstack-ovs/"

    CONF_DB = "/usr/local/etc/zstack-ovs/conf.db"
    DB_SOCK = "/var/run/openvswitch/db.sock"
    DBPidPath = "/var/run/openvswitch/ovsdb-server.pid"
    SwitchPidPath = "/var/run/openvswitch/ovs-vswitchd.pid"
    DBLogPath = "/var/log/zstack/openvswitch/ovsdb-server.log"
    SwitchLogPath = "/var/log/zstack/openvswitch/ovs-vswitchd.log"
    DBCtlFilePath = "/var/run/openvswitch/ovsdb-server.zs.ctl"
    SwitchCtlFilePath = "/var/run/openvswitch/ovs-vswitchd.zs.ctl"
    ctlBin = "ovs-vsctl --db=unix:{} ".format(DB_SOCK)

    def __init__(self, venv):
        self.venv = venv

        if not os.path.isdir(self.ovsPath):
            os.mkdir(self.ovsPath, 0755)

        if not os.path.isdir(self.logPath):
            os.mkdir(self.logPath, 0755)

        if not os.path.exists(self.vdpaPath):
            os.mkdir(self.vdpaPath, 0755)

        if not os.path.exists(self.confPath):
            os.mkdir(self.confPath, 0755)

    def checkOvs(func):
        def wrapper(self, *args, **kw):
            if self.venv.ready:
                return func(self, *args, **kw)
            return None
        return wrapper

    def start(self, restart=False):
        self.startDB(restart)
        self.startSwitch(restart)

    def stop(self):
        self.stopDB()
        self.stopSwitch()

    def status(self):
        self.statusDB()
        self.statusSwitch()

    @checkOvs
    @lock.lock('startDB')
    def startDB(self, restart=False):
        """ start ovsdb """

        if not restart and self.statusDB() > 0:
            return 0

        self.stopDB()
        self.upgradeDB()

        cmd = "ovsdb-server {}".format(self.CONF_DB)
        cmd = cmd + " -vconsole:emer -vsyslog:err -vfile:info"
        cmd = cmd + " --remote=punix:{}".format(self.DB_SOCK)
        cmd = cmd + " --private-key=db:Open_vSwitch,SSL,private_key"
        cmd = cmd + " --certificate=db:Open_vSwitch,SSL,certificate"
        cmd = cmd + " --bootstrap-ca-cert=db:Open_vSwitch,SSL,ca_cert"
        cmd = cmd + \
            " --no-chdir --log-file={} --pidfile={} --unixctl={}".format(
                self.DBLogPath, self.DBPidPath, self.DBCtlFilePath)
        cmd = cmd + " --detach --monitor"
        ret = shell.run(cmd)
        if ret != 0:
            raise OvsError("start ovsdb-server failed.")

        # Initialize database settings.
        ret = shell.run(self.ctlBin +
                        "--no-wait -- init -- set Open_vSwitch . db-version={}".format(self.venv.ovsDBVer))
        if ret != 0:
            logger.debug("init openvswitch database settings failed.")

        time.sleep(1)
        # get os release info
        osRelease = {}
        with open('/etc/os-release', 'r') as f:
            lines = f.readlines()
            for l in lines:
                l = l.strip()
                if l == '':
                    continue
                lsplit = l.split("=")
                osRelease[lsplit[0].strip()] = lsplit[1].strip('"')

        systemType = osRelease['ID']
        systemVersion = osRelease['VERSION_ID']

        cmd = self.ctlBin + "--no-wait set Open_vSwitch . ovs-version={}".format(
            self.venv.vSwitchVer)
        cmd = cmd + " external-ids:system-id={}".format(uuid.uuid4())
        cmd = cmd + " external-ids:rundir={}".format(self.ovsPath)
        cmd = cmd + " system-type={}".format(systemType)
        cmd = cmd + " system-version={}".format(systemVersion)

        ret = shell.run(cmd)

        if ret != 0:
            raise OvsError("set system infos for ovsdb failed.")

        logger.debug("ovsdb: [{}] start success".format(self.pids[0]))
        return 0

    def stopDB(self):
        return self.stopProcess("ovsdb-server")

    def statusDB(self):
        return self.pids[0]

    @checkOvs
    def upgradeDB(self):
        """
        create ovsDB if not exist
        upgrade ovsDB if needs conversion
        """
        def createDB():
            ret = shell.run(
                'ovsdb-tool -v create {} {}'.format(self.CONF_DB, self.ovs_schema))
            if ret != 0:
                logger.debug("create ovsdb file failed.")
            return ret

        if not os.path.isfile(self.CONF_DB):
            return createDB()

        s = shell.ShellCmd(
            "ovsdb-tool needs-conversion {} {}".format(self.CONF_DB, self.ovs_schema), None, False)
        s(False)
        if s.return_code != 0:
            logger.debug("upgrade ovsdb failed.")
            return s.return_code
        elif s.stdout != "yes":
            logger.debug("current ovsdb do not need conversion.")
            return 0
        else:
            # backup conf.db
            s1 = shell.ShellCmd(
                "ovsdb-tool db-version {}".format(self.CONF_DB))
            s1(False)
            if s1.return_code == 0:
                version = s1.stdout
            else:
                version = 'old'

            s2 = shell.ShellCmd(
                "ovsdb-tool db-cksum {} | awk '{print $1}'".format(self.CONF_DB))
            s2(False)
            if s2.return_code == 0:
                cksum = s2.stdout
            else:
                cksum = 'unknow'

            backup = self.CONF_DB + ".backup" + version + "-" + cksum
            shutil.copy2(self.CONF_DB, backup)

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
            ret = shell.run("ovsdb-tool compact {}".format(self.CONF_DB))
            ret = shell.run(
                "ovsdb-tool convert {} {}".format(self.CONF_DB, self.ovs_schema)) + ret

            if ret != 0:
                logger.warn(
                    "Schema conversion failed, using empty database instead")
                os.remove(self.CONF_DB)
                return createDB()

    @checkOvs
    @lock.lock('startSwitch')
    def startSwitch(self, restart=False):
        """ start vswitchd """

        if not restart and self.statusSwitch() > 0:
            return 0

        self.stopSwitch()

        if self.venv.dpdkVer != "unknow":
            self.venv.checkHugepage()

        cmd = "ovs-vswitchd unix:{}".format(self.DB_SOCK)
        cmd = cmd + " -vconsole:emer -vsyslog:err -vfile:info"
        cmd = cmd + " --mlockall --no-chdir"
        cmd = cmd + \
            " --log-file={} --pidfile={} --unixctl={}".format(
                self.SwitchLogPath, self.SwitchPidPath, self.SwitchCtlFilePath)
        cmd = cmd + " --detach --monitor"
        ret = shell.run(cmd)
        if ret != 0:
            raise OvsError("start ovs-vswitch failed.")

        logger.debug("ovs-vswitch: [{}] start success".format(self.pids[1]))
        return 0

    def stopSwitch(self):
        return self.stopProcess("ovs-vswitchd")

    def statusSwitch(self):
        return self.pids[1]

    @property
    def ovs_schema(self):
        ovsdir = "/usr/share/openvswitch/"
        path = os.path.join(ovsdir, 'vswitchd', 'vswitch.ovsschema')
        if os.path.isfile(path):
            return path
        return os.path.join(ovsdir, 'vswitch.ovsschema')

    @property
    def pids(self):
        """ return [ovsdb_pid, ovs-vswitch_pid] """

        ovsdb_pidf = os.path.join(self.ovsPath, "ovsdb-server.pid")
        vswitch_pidf = os.path.join(self.ovsPath, "ovs-vswitchd.pid")
        result = [-1, -1]
        if os.path.exists(ovsdb_pidf):
            with open(ovsdb_pidf, 'r') as f:
                result[0] = int(f.read().strip())
        if os.path.exists(vswitch_pidf):
            with open(vswitch_pidf, 'r') as f:
                result[1] = int(f.read().strip())
        return result

    def process_exists(self, pid):
        if os.path.isdir(os.path.join("/proc", str(pid))):
            return True
        return False

    def stopProcess(self, name):
        """
        stop ovsdb or vswitch by ovs-appctl,
        if not work, kill it.
        """
        dict = {"ovsdb-server": {"pid": self.pids[0], "ver": self.venv.ovsDBVer, "ctl": self.DBCtlFilePath},
                "ovs-vswitchd": {"pid": self.pids[1], "ver": self.venv.vSwitchVer, "ctl": self.SwitchCtlFilePath}}

        pid = dict[name]["pid"]
        ver = dict[name]["ver"]
        ctl = dict[name]["ctl"]

        if pid < 0:
            return True

        pidPath = os.path.join(self.ovsPath, "{}.pid".format(name))

        if not self.process_exists(pid):
            try:
                os.remove(pidPath)
                os.remove(ctl)
            except OSError:
                pass
            return True

        graceful = "EXIT 0.1 0.25 0.65 1"
        actions = "TERM 0.1 0.25 0.65 1 1 1 1 KILL 1 1 1 2 10 15 30 FAIL"
        # Use `ovs-appctl exit` only if the running daemon version
        # is >= 2.5.90.  This script might be used during upgrade to
        # stop older versions of daemons which do not behave correctly
        # with `ovs-appctl exit` (e.g. ovs-vswitchd <= 2.5.0 deletes
        # internal ports).
        if self.version_geq(ver, "2.5.90") and self.venv.ready:
            actions = graceful + ' ' + actions

        forceStop = False
        for action in actions.split():

            if not self.process_exists(pid):
                if forceStop:
                    return True
                else:
                    # check one more time
                    if not os.path.exists(pidPath) and not self.process_exists(pid):
                        return True

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
                logger.error("Killing {} {} failed".format(name, pid))
                return False
            else:
                time.sleep(float(action))

        return False

    def version_geq(self, v1, v2):
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


class OvsCtl(Ovs):
    def __init__(self, venv=None):
        if venv is None:
            venv = OvsVenv()
        super(OvsCtl, self).__init__(venv)
        self.startDB(False)
        self.vdpaSup = not self.venv.dpdkVer == "unknow"

    def checkOvs(func):
        def wrapper(self, *args, **kw):
            if self.venv.ready:
                return func(self, *args, **kw)
            return None
        return wrapper

    @linux.retry(times=5, sleep_time=2)
    def initVdpaSupport(self):
        """
        config ovs dpdk, open hardware offload, init dpdk  and so on.
        """
        if not self.vdpaSup:
            return False

        shell.run(self.ctlBin +
                  "--no-wait set Open_vSwitch . other_config:hw-offload=true")
        shell.run(self.ctlBin +
                  "--no-wait set Open_vSwitch . other_config:dpdk-init=true")
        # TODO: caculater the memory
        shell.run(self.ctlBin +
                  "--no-wait set Open_vSwitch . other_config:dpdk-socket-mem={}".format(self.venv.nr_hugepages))

        # check Open_vSwitch table
        ret = shell.call(self.ctlBin + "get Open_vSwitch . other_config")

        if "hw-offload" not in ret or \
           "dpdk-init" not in ret or \
           "dpdk-socket-mem" not in ret:
            raise OvsError("init vdpa support failed.")

        return True

    # ---------------------------- ovsctl ----------------------------------------

    def listBrs(self, *args):
        s = shell.ShellCmd(self.ctlBin + "list-br", None, False)
        s(False)

        if s.return_code != 0:
            logger.debug("list ovs bridges failed.")
            return []
        else:
            return s.stdout.strip().splitlines()

    def createBr(self, brName, *args):

        brs = self.listBrs()
        if brName in brs:
            logger.debug("bridge {} already created".format(brName))
            return 0

        # create bridge
        ret = shell.run(self.ctlBin + 'add-br {} -- set Bridge {} datapath_type=netdev'.format(
            brName, brName, "netdev"))

        return ret

    def deleteBr(self, *args):
        brs = self.listBrs()
        for arg in args:
            if arg in brs:
                s = shell.ShellCmd(self.ctlBin +
                                   "--timeout=5 del-br {}".format(arg), None, False)
                s(False)
                if s.return_code != 0:
                    logger.debug("delete bridge {} failed.".format(arg))
                    return s.return_code
        return 0

    def deleteBrs(self):
        brs = self.listBrs()
        for br in brs:
            s = shell.run(self.ctlBin +
                          "--timeout=5 del-br {}".format(br))
            s(False)
            if s.return_code != 0:
                logger.debug("delete bridge {} failed.".format(br))

    def listIfaces(self, brName, *args):
        s = shell.ShellCmd(self.ctlBin +
                           "--timeout=5 list-ifaces {}".format(brName), None, False)
        s(False)
        if s.return_code != 0:
            return []
        else:
            return s.stdout.strip().splitlines()

    def listPorts(self, brName, *args):
        s = shell.ShellCmd(self.ctlBin +
                           "--timeout=5 list-ports {}".format(brName), None, False)
        s(False)
        if s.return_code != 0:
            return []
        else:
            return s.stdout.strip().splitlines()

    def addPort(self, brName, phyIfName, type, *args):
        # add port
        cmd = self.ctlBin + \
            'add-port {} {} -- set Interface {} type={} '.format(
                brName, phyIfName, phyIfName, type)

        for arg in args:
            cmd = cmd + "options:{} ".format(arg)

        return shell.run(cmd)

    def delPort(self, brName, phyIfName, *args):
        return shell.run(self.ctlBin +
                         'del-port {} {}'.format(brName, phyIfName))

    def setPort(self, portName, tag):
        return shell.run(self.ctlBin +
                         'set Port {} tag={} '.format(portName, tag))

    def setIfaces(self, ifName, *args):
        # set options
        cmd = self.ctlBin + 'set Interface {} '.format(ifName)

        for arg in args:
            cmd = cmd + "{} ".format(arg)

        return shell.run(cmd)

    # ---------------------------- external ---------------------------------------

    @checkOvs
    def prepareBridge(self, bridgeName, interface):
        # check whether interface is a bond
        infacPath = '/sys/class/net/{}'.format(interface)

        # kernel bond
        if self.isKernelBond(interface):
            #self._init_kernel_bond(bridgeName, interface)
            logger.debug("do not support kernel bond since v4.2.1.")
            return False

        # normal interface
        if os.path.exists(infacPath):
            self._init_interface(bridgeName, interface)
            return True

        # dpdk bond, dpdk bond configurations are store in file 'dpdk-bond.xml'
        dpdkBond = self.getDPDKBond(interface)
        if dpdkBond is None:
            return False

        return self._init_dpdk_bond(bridgeName, dpdkBond)

    @lock.lock('getVdpa')
    def getVdpaS(self, vmUuid, nics):
        ret = {}
        for nic in nics:
            vdpaPath = self._getVdpa(vmUuid, nic)
            if vdpaPath is not None:
                ret[nic.nicInternalName] = vdpaPath
            else:
                # if vDPA resource is not enough then 
                # realse all vDPAs.
                for k in ret:
                    self.freeVdpa(vmUuid, k)
                return None

        return ret


    @lock.lock('getVdpa')
    def getVdpa(self, vmUuid, nic):
        return self._getVdpa(vmUuid, nic)

    @checkOvs
    def _getVdpa(self, vmUuid, nic):
        bridgeName = nic.bridgeName
        bondName = nic.physicalInterface
        vlanId = nic.vlanId
        nicInternalName = nic.nicInternalName

        # check vdpa support
        if not self.vdpaSup:
            raise OvsError(
                "ovs does not support vdpa feature. Please check dpdk settings")

        # check br
        if bridgeName not in self.listBrs():
            raise OvsError("bridge:{} does not exists.".format(bridgeName))

        curPorts = self.listPorts(bridgeName)
        # check bond
        if bondName not in curPorts:
            raise OvsError(
                "bond:{} does not exists. Please create it firstly".format(bondName))

        # check if already attached
        if nicInternalName in curPorts:
            s = shell.ShellCmd(
                self.ctlBin + "get Interface {} options:vdpa-socket-path".format(nicInternalName))
            s(False)
            if s.return_code != 0:
                logger.debug(
                    "nic interface {} maybe not a vdpa type".format(nicInternalName))
                return None
            return s.stdout.strip()[1:-1]

        vdpaBrPath = os.path.join(self.vdpaPath, bridgeName)
        if not os.path.exists(vdpaBrPath):
            os.mkdir(vdpaBrPath, 0755)

        vdpaSockPath = os.path.join(vdpaBrPath, nicInternalName+".sock")

        vf, pci, ifaceName = self._get_free_vf(bridgeName, bondName)
        if pci == None:
            return None

        self.addPort(bridgeName, nicInternalName, "dpdkvdpa",
                     "vdpa-socket-path={}".format(vdpaSockPath),
                     "vdpa-accelerator-devargs={}".format(pci),
                     "dpdk-devargs={},representor=[{}]".format(
                         self._get_if_pcinum(ifaceName), vf[6:]),
                     "vdpa-max-queues=8",
                     "vdpa-sw=true")

        if vlanId is not None:
            self.setPort(nicInternalName, vlanId)

        self.setIfaces(nicInternalName, "external_ids:vm-id={}".format(vmUuid))

        return vdpaSockPath

    @checkOvs
    def listVdpas(self, vmUuid):
        if not self.vdpaSup:
            return

        s = shell.ShellCmd(self.ctlBin +
                           "--columns=name find interface external_ids:vm-id={} | grep name |cut -d ':' -f2 | tr -d ' '".format(vmUuid), None, False)
        s(False)
        if s.return_code != 0:
            return []
        else:
            return s.stdout.strip().splitlines()

    @checkOvs
    @lock.lock('freeVdpa')
    def freeVdpa(self, vmUuid, specificNic=None):
        vDPA_list = []

        if not self.vdpaSup:
            return

        vDPA_path = ''
        if specificNic != None:
            vDPA_list.append(specificNic)
            s = shell.ShellCmd(self.ctlBin +
                               "get interface {} options:vdpa-socket-path".format(specificNic), None, False)
            s(False)
            if s.return_code != 0:
                logger.debug(
                    "nic interface {} maybe not a vdpa type".format(specificNic))
                vDPA_path = None
            else:
                vDPA_path = s.stdout.strip().strip('"')

        else:
            # free all vdpa nic belongs to vm
            # get all vdpa nic belongs to vm
            vDPA_list = self.listVdpas(vmUuid)

        for br in self.listBrs():
            tmpList = []
            for vDPA in vDPA_list:
                if vDPA in self.listIfaces(br):
                    self.delPort(br, vDPA)
                    tmpList.append(vDPA)
            vDPA_list = list(set(vDPA_list).difference(set(tmpList)))

        return vDPA_path

    @checkOvs
    def ifOffloadStatus(self, ifName):

        vd = self._get_if_vd(ifName)

        if vd in self.venv.offloadStatus.keys():
            return self.venv.offloadStatus[vd]

        return None

    @checkOvs
    def getDPDKBond(self, bondName):
        bondFile = os.path.join(self.confPath, "dpdk-bond.yaml")
        if not os.path.exists(bondFile):
            return None

        dpdkBond = Bond()
        with open(bondFile, "r") as f:
            data = yaml.safe_load(f)

        for d in data:
            if d['bond']['name'] == bondName:
                dpdkBond.name = d['bond']['name']
                dpdkBond.mode = d['bond']['mode']
                if d['bond'].has_key('policy'):
                    dpdkBond.policy = d['bond']['policy']
                dpdkBond.id = d['bond']['id']
                for i in d['bond']['slaves']:
                    dpdkBond.slaves.append(str(i))

                return dpdkBond

        return None

    def isKernelBond(self, interface):
        # check whether interface is a bond
        bondList = readSysfs('/sys/class/net/bonding_masters').strip().split()
        return interface in bondList

    @checkOvs
    def reconfigOvs(self):
        ret = shell.run("modprobe bonding")
        if ret != 0:
            raise OvsError("can not find bonding module.")

        if not self.initVdpaSupport():
            raise OvsError("ovs can not support dpdk.")

        self._updateOvsConfig()

        # reconfig smart nics
        brs = self.listBrs()

        # do not start ovs-vswitchd while
        # there is no bridges.
        if len(brs) == 0:
            return

        for b in brs:
            if b == '':
                continue
            # prepare bridge floader
            vdpaBrPath = os.path.join(self.vdpaPath, b)
            if not os.path.exists(vdpaBrPath):
                os.mkdir(vdpaBrPath, 0755)
            self.prepareBridge(b, b[3:])
        # do not force restart openvswitch.
        self.start()

    # ---------------------------- utils ------------------------------------------

    def _init_kernel_bond(self, bridgeName, bondName):
        """
        attach kernel bond to ovs.
        """

        slaves_p = "/sys/class/net/{}/bonding/slaves"

        if not os.path.exists(slaves_p.format(bondName)):
            return False

        interfaces = self._get_bond_slaves(bondName)
        if_pci_bdf = set()
        if_vendor = set()

        for i in interfaces:
            if_pci_bdf.add(self._get_if_pcinum(i).split(".")[0])
            if_vendor.add(self._get_if_vd(i))

        # the pfs under vflag should come from the same nic.
        if len(if_vendor) != 1 or len(if_pci_bdf) != 1:
            return False

        # check vendor_device number
        if self.ifOffloadStatus(interfaces[0]) == None:
            return False

        for i in interfaces:
            # set devlink mode to switchdev and unbind vfs
            self._set_if_devlink_mode(i)
            self._set_dpdk_white_list(i)

        if bridgeName not in self.listBrs():
            # create bridge
            self.createBr(bridgeName)

        if bondName not in self.listPorts(bridgeName):
            # To work with VF-LAG with OVS-DPDK, add the bond master (PF) to the bridge. Note that the first
            # PF on which you run "ip link set <PF> master bond0" becomes the bond master.
            if self.addPort(bridgeName, bondName, "dpdk",
                            "dpdk-devargs={}".format(
                                self._get_if_pcinum(interfaces[0])),
                            "dpdklsc-interrupt=true") != 0:
                return False

        return True

    def _init_dpdk_bond(self, bridgeName, bond):
        """
        attach dpdk-bond to bridge
        """

        if len(bond.slaves) < 2:
            logger.debug(
                "Number of slaves in dpdk bond:{} < 2".format(bond.name))
            return False

        for i in bond.slaves:
            # check vendor_device number
            if self.ifOffloadStatus(i) == None:
                return False
            # set devlink mode to switchdev and unbind vfs
            self._set_if_devlink_mode(i)
            self._set_dpdk_white_list(i)

        if bridgeName not in self.listBrs():
            # create bridge
            if self.createBr(bridgeName) != 0:
                logger.debug("create bridge {} failed.".format(bridgeName))
                return False

        if bond.name not in self.listPorts(bridgeName):
            # ovs-vsctl add-port br_test bondtest -- \
            # set Interface bondtest type=dpdk dpdk-devargs="eth_bond0,mode=2,\
            # slave=0000:81:00.1,slave=0000:82:00.1,xmit_policy=l34"
            dpdk_devargs = "eth_bond{},".format(bond.id)
            dpdk_devargs = dpdk_devargs + "mode={}".format(bond.mode)
            for s in bond.slaves:
                dpdk_devargs = dpdk_devargs + \
                    ",slave={}".format(self._get_if_pcinum(s))
            # There are 3 supported transmission policies for bonded device
            # running in Balance XOR mode.
            if bond.mode == 2 and bond.policy is not None:
                dpdk_devargs = dpdk_devargs + ",xmit_policy={}".format(bond.policy)
            dpdk_devargs = "dpdk-devargs={}".format(dpdk_devargs)

            if self.addPort(bridgeName, bond.name, "dpdk",
                            dpdk_devargs) != 0:
                return False

            # every time you create a new dpdkbond,
            # you have to restart ovs-vswitchd to 
            # make the dpdkbond work.
            self.startSwitch(True)

        return True

    def _init_interface(self, bridgeName, interface):
        """
        attach normal interface to ovs.
        """
        self._set_if_devlink_mode(interface)
        self._set_dpdk_white_list(interface)
        if bridgeName not in self.listBrs():
            # create bridge
            if self.createBr(bridgeName) != 0:
                logger.debug("create bridge {} failed.".format(bridgeName))
                return False
        if interface not in self.listPorts(bridgeName):
            self.addPort(bridgeName, interface, "dpdk",
                         "dpdk-devargs={}".format(
                             self._get_if_pcinum(interface)))

    def _set_dpdk_white_list(self, ifName):
        ret = 0
        dpdk_extra = ""

        s = shell.ShellCmd(self.ctlBin +
                           "get Open_vSwitch . other_config:dpdk-extra", None, False)
        s(False)
        if s.return_code == 0:
            dpdk_extra = s.stdout.strip().strip('\n').strip('"')
        else:
            logger.debug("get dpdk-extra config failed.")

        pci = self._get_if_pcinum(ifName)

        if pci in dpdk_extra:
            return ret

        if self.version_geq(self.venv.dpdkVer, "20.11"):
            dpdk_extra = dpdk_extra + "-a {},representor=[0-127],dv_flow_en=1,dv_esw_en=1 ".format(
                pci)
        else:
            dpdk_extra = dpdk_extra + "-w {},representor=[0-127],dv_flow_en=1,dv_esw_en=1 ".format(
                pci)

        ret = shell.run(self.ctlBin +
                        '--no-wait set Open_vSwitch . other_config:dpdk-extra="{}"'.format(dpdk_extra))

        if ret != 0:
            logger.info(
                "set dpdk wihite list for {} failed".format(ifName))
            return ret

        self.startSwitch(True)

        return ret

    def _updateOvsConfig(self):
        """
        reconfig Open_vSwitch if ovs version changed
        """

        dpdk_extra = ""

        s = shell.ShellCmd(self.ctlBin +
                           "get Open_vSwitch . other_config:dpdk-extra", None, False)
        s(False)
        if s.return_code == 0:
            dpdk_extra = s.stdout.strip().strip('\n').strip('"')

        if self.version_geq(self.venv.dpdkVer, "20.11"):
            dpdk_extra = dpdk_extra.replace("-w", "-a")
            dpdk_extra = dpdk_extra.replace("dv_xmeta_en=1", "")
        else:
            dpdk_extra = dpdk_extra.replace("-a", "-w")

        ret = shell.run(self.ctlBin +
                        '--no-wait set Open_vSwitch . other_config:dpdk-extra="{}"'.format(dpdk_extra))

        if ret != 0:
            logger.debug("update ovs configuration failed.")

    def _get_if_pcinum(self, ifName):
        pci = None
        try:
            pci_path = '/sys/class/net/{}/device'
            pci = os.path.realpath(pci_path.format(ifName)).split("/")[-1]
        except Exception as e:
            logger.warn(str(e))
        finally:
            return pci

    def _get_if_vd(self, ifName):
        vendor_path = '/sys/class/net/{}/device/vendor'.format(ifName)
        device_path = '/sys/class/net/{}/device/device'.format(ifName)

        vendorId = readSysfs(vendor_path)[2:6]
        deviceId = readSysfs(device_path)[2:6]

        return vendorId + deviceId

    def _get_bond_slaves(self, bond):
        slaves_p = "/sys/class/net/{}/bonding/slaves".format(bond)
        ifList = []
        # kernel bond
        if os.path.exists(slaves_p):
            ifList = readSysfs(slaves_p).split()
            return ifList

        # dpdk bond
        dpdkBond = self.getDPDKBond(bond)
        if dpdkBond is not None:
            ifList = dpdkBond.slaves

        return ifList

    def _get_vfs_dict(self, ifName):
        """
        vfs_dict{'virtfnx', '0000:65:00.1'}
        """

        device_p = "/sys/class/net/{}/device/"
        vfs_dict = {}
        tmp_list = os.listdir(device_p.format(ifName))
        for vf in tmp_list:
            if vf.startswith("virtfn"):
                pci = os.path.realpath(device_p.format(
                    ifName) + vf).split("/")[-1]
                vfs_dict[vf] = pci

        return vfs_dict

    def _set_if_devlink_mode(self, ifName, mode="switchdev"):
        devlink_mode = '/sys/class/net/{}/compat/devlink/mode'.format(
            ifName)
        totalvfs = '/sys/class/net/{}/device/sriov_totalvfs'.format(ifName)
        numvfs = '/sys/class/net/{}/device/sriov_numvfs'.format(ifName)
        totalvfs = readSysfs(totalvfs)

        if readSysfs(devlink_mode, True) == mode and totalvfs == readSysfs(numvfs):
            return

        iproute.set_link_down_no_error(ifName)
        # split vfs
        writeSysfs(numvfs, "0")
        # wait until
        for _ in range(0, 5):
            if int(readSysfs(numvfs)) != 0:
                time.sleep(0.2)
        writeSysfs(numvfs, totalvfs)
        # wait split vfs complete
        for _ in range(0, 5):
            if int(readSysfs(numvfs)) != totalvfs:
                time.sleep(0.2)

        self._unbind_vfs(ifName)

        # change devlink mode
        confirmWriteSysfs(devlink_mode, mode, 10, 5)
        logger.debug("set {} for {} success.".format(mode, ifName))

        self._bind_vfs(ifName)
        iproute.set_link_up_no_error(ifName)

    def _unbind_vfs(self, ifName):
        # unbind vfs
        dev_path = '/sys/class/net/{}/device/'.format(ifName)
        unbind_path = '/sys/class/net/{}/device/driver/unbind'.format(ifName)

        pci_list = self._get_vfs_dict(ifName)
        for i in pci_list:
            writeSysfs(unbind_path, pci_list[i])
            # wait unbind finished, It may take some time to unbind VFS
            for _ in range(0, 5):
                if os.path.exists(os.path.join(dev_path, i, "driver")):
                    time.sleep(0.5)

    def _bind_vfs(self, ifName):
        # bind vfs
        dev_path = '/sys/class/net/{}/device/'.format(ifName)
        bind_path = '/sys/class/net/{}/device/driver/bind'.format(ifName)

        pci_list = self._get_vfs_dict(ifName)
        for i in pci_list:
            if not os.path.exists(os.path.join(dev_path, i, "driver")):
                writeSysfs(bind_path, pci_list[i], True)
            # wait bind finished, It will take some time
            for _ in range(0, 5):
                if not os.path.exists(os.path.join(dev_path, i, "driver")):
                    time.sleep(0.5)

    def _get_free_vf(self, bridgeName, bondName):

        # get all vfs under bond
        slaves = self._get_bond_slaves(bondName)

        # maybe it is not a bond
        if len(slaves) == 0 and os.path.exists("/sys/class/net/{}".format(bondName)) and \
                not os.path.exists("/sys/class/net/{}/bonding_slave".format(bondName)):
            slaves.append(bondName)

        if len(slaves) == 0:
            return None, None, None

        # get used vfs under bond
        usedPciList = self._get_used_pci(bridgeName)

        for s in slaves:
            vfsDict = self._get_vfs_dict(s)
            for v in vfsDict:
                if vfsDict[v] not in usedPciList:
                    return v, vfsDict[v], s

        return None, None, None

    def _get_used_pci(self, bridgeName):
        usedPciList = []

        ifList = self.listIfaces(bridgeName)
        if ifList == None:
            return usedPciList

        for i in ifList:
            s = shell.ShellCmd(self.ctlBin +
                               "get Interface {} options:vdpa-accelerator-devargs".format(i), None, False)
            s(False)
            if s.return_code != 0:
                continue

            usedPciList.append(s.stdout.strip()[1:-1])

        return usedPciList


class Bond:
    def __init__(self):
        self.name = "default"
        self.policy = None
        self.mode = 1
        self.slaves = []
        self.id = 0
