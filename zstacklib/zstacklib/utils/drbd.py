import os

from zstacklib.utils import linux
from zstacklib.utils import bash
from zstacklib.utils import lvm
from zstacklib.utils import log
from jinja2 import Template


logger = log.get_logger(__name__)


class RetryException(Exception):
    pass


class DrbdRole(object):
    Primary = "Primary"
    Secondary = "Secondary"


class DrbdNetState(object):
    WFConnection = "WFConnection"
    Unconfigured = "Unconfigured"
    StandAlone = "StandAlone"
    Disconnecting = "Disconnecting"
    Unconnected = "Unconnected"
    Timeout = "Timeout"
    BrokenPipe = "BrokenPipe"
    NetworkFailure = "NetworkFailure"
    ProtocolError = "ProtocolError"
    Connecting = "Connecting"
    TearDown = "TearDown"
    Connected = "Connected"
    Unknown = "Unknown"
    Unconfigured = "Unconfigured"


class DrbdResource(object):
    def __init__(self, name, up=True):
        super(DrbdResource, self).__init__()
        self.config = DrbdConfigStruct(name)
        self.name = self.config.name = name
        self.path = self.config.path = "/etc/drbd.d/%s.res" % name

        self.cstate = None
        self.local_role = None
        self.remote_role = None
        self.local_disk_state = None
        self.remote_disk_state = None

        if self.name is None:
            return

        try:
            self._init_from_name()
        except Exception:
            logger.debug("can not find config of resource %s" % self.name)
            return

        if up and not self.minor_allocated():
            self.up()

    def _init_from_disk(self, disk_path):
        """

        :type disk_path: str
        """
        config_path = self.get_config_path_from_disk(disk_path)
        self._init_from_config_path(config_path)

    def _init_from_name(self):
        if self.name is None:
            return
        self._init_from_config_path(self.get_config_path_from_name(self.name))

    def _init_from_config_path(self, config_path):
        self.path = self.config.path = config_path
        self.config.read_config()

    @staticmethod
    @bash.in_bash
    def get_config_path_from_disk(disk_path, raise_exception=True):
        return bash.bash_o("grep -E 'disk.*%s' /etc/drbd.d/ -r | head -n1 | awk '{print $1}' | cut -d ':' -f1" % disk_path, raise_exception).strip()

    @staticmethod
    @bash.in_bash
    def get_config_path_from_name(name):
        if bash.bash_r("drbdadm dump %s" % name) == 0:
            return bash.bash_o("drbdadm dump %s | grep 'defined at' | awk '{print $4}'" % name).split(":")[0]
        if bash.bash_r("ls /etc/drbd.d/%s.res" % name) == 0:
            return "/etc/drbd.d/%s.res" % name
        raise Exception("can not find drbd resource %s" % name)

    @staticmethod
    @bash.in_bash
    def get_name_from_config_path(config_path):
        """

        :type config_path: str
        """
        if bash.bash_r("head -n 1 %s" % config_path) == 0:
            return bash.bash_o("head -n 1 %s | awk '{print $2}'" % config_path).strip()
        else:
            return config_path.split("/")[-1].split(".")[0]

    @bash.in_bash
    def up(self):
        if not self.minor_allocated() or self.get_cstate() == DrbdNetState.Unconfigured:
            bash.bash_errorout("drbdadm up %s" % self.name)

    @bash.in_bash
    def down(self):
        bash.bash_errorout("drbdadm down %s" % self.name)

    @bash.in_bash
    @linux.retry(times=15, sleep_time=2)
    def promote(self, force=False):
        f = " --force" if force else ""
        r, o, e = bash.bash_roe("drbdadm primary %s %s" % (self.name, f))
        if self.get_role() != DrbdRole.Primary:
            raise RetryException("promote failed, return: %s, %s, %s. resource %s still not in role %s" % (r, o, e, self.name, DrbdRole.Primary))

    @bash.in_bash
    def demote(self):
        r, o, e = bash.bash_roe("drbdadm secondary %s" % self.name)

    @bash.in_bash
    def get_cstate(self):
        return bash.bash_o("drbdadm cstate %s" % self.name).strip()

    @bash.in_bash
    def get_dstate(self):
        return bash.bash_o("drbdadm dstate %s | cut -d '/' -f1" % self.name).strip()

    @bash.in_bash
    def get_remote_dstate(self):
        return bash.bash_o("drbdadm dstate %s | cut -d '/' -f2" % self.name).strip()

    def is_connected(self):
        return self.get_cstate() == DrbdNetState.Connected

    @bash.in_bash
    def get_role(self):
        return bash.bash_o("drbdadm role %s | awk -F '/' '{print $1}'" % self.name).strip()

    @bash.in_bash
    def get_remote_role(self):
        return bash.bash_o("drbdadm role %s | awk -F '/' '{print $2}'" % self.name).strip()

    def get_dev_path(self):
        assert self.config.local_host.minor is not None
        return "/dev/drbd%s" % self.config.local_host.minor

    @bash.in_bash
    @linux.retry(times=15, sleep_time=2)
    def clear_bits(self):
        bash.bash_errorout("drbdadm new-current-uuid --clear-bitmap %s" % self.name)

    @bash.in_bash
    def minor_allocated(self):
        r, o, e = bash.bash_roe("drbdadm role %s" % self.name)
        if e is not None and "Device minor not allocated" in e:
            logger.debug("Device %s minor not allocated!" % self.name)
            return False
        return True

    @bash.in_bash
    def initialize(self, primary, cmd, backing=None):
        bash.bash_errorout("echo yes | drbdadm create-md %s" % self.name)
        self.up()
        if not primary:
            self.clear_bits()
        if primary:
            self.promote(False)
            if backing:
                linux.qcow2_create_with_backing_file_and_cmd(backing, self.get_dev_path(), cmd)
            else:
                linux.qcow2_create_with_cmd(self.get_dev_path(), cmd.size, cmd)
            self.demote()

    @bash.in_bash
    def is_defined(self):
        assert self.name is not None
        assert self.name.strip() != ""
        r, o, e = bash.bash_roe("drbdadm role %s" % self.name)
        if r != 0 and "not defined in your config" in o+e:
            return False

        return True

    @bash.in_bash
    def destroy(self):
        if not self.is_defined():
            return
        self.down()
        bash.bash_r("echo yes | drbdadm wipe-md %s" % self.name)
        bash.bash_r("rm /etc/drbd.d/%s.res" % self.name)

    @bash.in_bash
    def resize(self):
        bash.bash_errorout("drbdadm -- --assume-clean resize %s" % self.name)


class DrbdStruct(object):
    pass


class DrbdConfigStruct(DrbdStruct):
    def __init__(self, name):
        super(DrbdConfigStruct, self).__init__()
        self.path = None
        self.name = name
        self.local_host = DrbdHostStruct(name)
        self.remote_host = DrbdHostStruct(name)
        self.net = DrbdNetStruct()

        # handlers
        self.split_brain = '"/usr/lib/drbd/notify-split-brain.sh root"'
        # TODO(weiw): fix it
        self.fence_peer = '"echo `date +%s.%N` >> /tmp/hehe.txt"'

        # disk
        self.fencing = 'resource-only'

    def read_config(self):
        assert self.path
        with open(self.path, "r") as f:
            content = f.readlines()  # type: list[str]

        on_local = on_remote = False
        for line in content:
            line = line.strip()
            if line.startswith("resource ") and line.endswith(" {"):
                assert self.name == line.split(" ")[1], "self.name: %s, line: %s" % (self.name, line)
            elif line.strip().endswith(";"):
                line = line.strip(";")
                key = line.split(" ", 1)[0].replace("-", "_")
                try:
                    value = line.split(" ", 1)[1].strip()
                except IndexError:
                    continue

                if key in self.__dict__.keys():
                    self.__dict__[key] = value
                elif key in self.net.__dict__.keys():
                    self.net.__dict__[key] = value
                elif on_local and key in self.local_host.__dict__.keys():
                    if key == "device":
                        self.local_host.device = value.split(" ")[0]
                        self.local_host.minor = value.split(" ")[2]
                        continue
                    self.local_host.__dict__[key] = value
                elif on_remote and key in self.remote_host.__dict__.keys():
                    if key == "device":
                        self.remote_host.device = value.split(" ")[0]
                        self.remote_host.minor = value.split(" ")[2]
                        continue
                    self.remote_host.__dict__[key] = value
            elif line.startswith("on ") and line.endswith("# local"):
                on_local = True
                self.local_host.hostname = line.split(" ")[1]
            elif line.startswith("on ") and line.endswith("# remote"):
                on_remote = True
                self.remote_host.hostname = line.split(" ")[1]
            elif (on_local is True or on_remote is True) and "}" in line:
                on_local = on_remote = False

    def write_config(self):
        assert self.name is not None
        config = Template("""
resource {{ name }} {
  handlers {
    split-brain {{ split_brain }};
    fence-peer {{ fence_peer }};
  }

  net {
    csums-alg {{ net_csums_alg }};
    after-sb-0pri {{ net_after_sb_0pri }};
    after-sb-1pri {{ net_after_sb_1pri }};
    after-sb-2pri {{ net_after_sb_2pri }};
    protocol C;

    sndbuf-size {{ net_sndbuf_size }};
    allow-two-primaries yes;
    verify-alg {{ net_verify_alg }};
  }

  disk {
    fencing {{ fencing }};
  }

  on {{ local_host_hostname }} {  # local
    device    {{ local_host_device }} minor {{ local_host_minor }};
    disk      {{ local_host_disk }};
    address   {{ local_host_address }};
    meta-disk internal;
  }
  on {{ remote_host_hostname }} {  # remote
    device    {{ remote_host_device }} minor {{ remote_host_minor }};
    disk      {{ remote_host_disk }};
    address   {{ remote_host_address }};
    meta-disk internal;
  }
}
            """)
        logger.debug("write drbd config: \n%s" % config.render(self.make_ctx()).strip())
        dirname = os.path.dirname(self.path)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(self.path, "w") as f:
            f.write(config.render(self.make_ctx()).strip())

    def make_ctx(self):
        ctx = {}
        for k, v in self.__dict__.items():
            if isinstance(v, str):
                ctx[k] = v
            elif isinstance(v, DrbdStruct):
                for m, n in v.__dict__.items():
                    ctx["%s_%s" % (k, m)] = n
        ctx["local_host_hostname"] = bash.bash_o("hostname").strip()
        return ctx


class DrbdHostStruct(DrbdStruct):
    def __init__(self, name):
        super(DrbdHostStruct, self).__init__()
        self.hostname = None
        self.address = None
        self.disk = None
        self.device = "/dev/drbd_%s" % name
        self.minor = None
        self.meta_disk = "internal"


class DrbdNetStruct(DrbdStruct):
    def __init__(self):
        super(DrbdNetStruct, self).__init__()
        self.csums_alg = 'sha1'
        self.after_sb_0pri = 'discard-zero-changes'
        self.after_sb_1pri = 'call-pri-lost-after-sb'
        self.after_sb_2pri = 'call-pri-lost-after-sb'
        self.sndbuf_size = 0
        self.allow_two_primaries = 'yes'
        self.verify_alg = 'md5'


@bash.in_bash
# TODO(weiw): drbd-overview maybe not exists
def list_local_up_drbd(vgUuid):
    if bash.bash_r("drbd-overview | grep -v %s" % DrbdNetState.Unconfigured) == 1:
        return []
    names = bash.bash_o("drbd-overview | grep -v %s | awk -F ':' '{print $2}' | awk '{print $1}'" % DrbdNetState.Unconfigured).strip().splitlines()
    return [DrbdResource(name) for name in names]


@bash.in_bash
def install_drbd():
    mod_installed = bash.bash_r("lsmod | grep drbd") == 0
    mod_exists = bash.bash_r("modinfo drbd") == 0
    utils_installed = bash.bash_r("rpm -ql drbd-utils || rpm -ql drbd84-utils") == 0
    utils_exists, o = bash.bash_ro("ls /opt/zstack-dvd/Packages/drbd-utils*")

    if mod_installed and utils_exists:
        return

    if not mod_installed:
        if mod_exists:
            bash.bash_errorout("modprobe drbd")
        else:
            raise Exception("drbd mod not installed and not exists!")

    if not utils_installed:
        if utils_exists == 0:
            bash.bash_errorout("rpm -ivh %s" % o)
        else:
            raise Exception("drbd utils not installed and not exists!")


class OperateDrbd(object):
    @bash.in_bash
    def __init__(self, resource, shared=False, delete_when_exception=False):
        self.resource = resource
        self.shared = shared
        self.current_role = self.resource.get_role()
        self.delete_when_exception = delete_when_exception

    @bash.in_bash
    def __enter__(self):
        if self.current_role == DrbdRole.Secondary:
            self.resource.promote()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None and self.delete_when_exception is True:
            lvm.delete_lv(self.resource.config.local_host.disk, False)
            return

        if self.current_role == DrbdRole.Secondary and not self.shared:
            self.resource.demote()


@bash.in_bash
def up_all_resouces():
    all_names = bash.bash_o("ls /etc/drbd.d/ | grep -v global_common.conf").strip().splitlines()
    for name in all_names:
        try:
            DrbdResource(name.split(".")[0])
        except Exception as e:
            logger.warn("up resource %s failed: %s" % (name, e.message))
