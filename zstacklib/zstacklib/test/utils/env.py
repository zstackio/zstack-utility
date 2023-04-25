import os
import yaml

from zstacklib.utils import log, jsonobject

logger = log.get_logger(__name__)

envFile = "/root/.zguest/envconfig.yaml"


def init_env():
    with open(envFile, "r") as f:
        env = yaml.load(f.read(), Loader=yaml.FullLoader)
    return env


class EnvVariable(object):
    def __init__(self, name, variable_type, default=None, required=False):
        self.name = name
        self.type = variable_type
        self.default = default
        self.required = required
        self.env = init_env()

    def set(self, value):
        self.env[self.name] = value
        with open(envFile, "w") as f:
            f.write(yaml.dump(self.env))

    def value(self):
        v = self.env.get(self.name, None)
        try:
            if v is not None:
                return self.type(v)
            elif v is None and self.required:
                raise ValueError('the required environment variable[%s] is not defined' % self.name)
            else:
                return self.type(self.default)
        except TypeError as ex:
            raise Exception('environment[%s] is defined as type[%s] but get %s. %s' %
                            (self.name, self.type, type(v), str(ex)))


def env_var(name, the_type, default=None, required=True):
    # type: (str, typing.Type, typing.Any, bool) -> EnvVariable

    return EnvVariable(name=name, variable_type=the_type, default=default, required=required)


VM_IMAGE_PATH = env_var('caseImagePath', str).value()
DEFAULT_ETH_INTERFACE_NAME = env_var('defaultEthName', str).value()
TEST_ROOT = env_var('testRoot', str).value()
VOLUME_DIR = env_var('volumePath', str).value()
SNAPSHOT_DIR = env_var('snapShotPath', str).value()
CASE_PATH = env_var('casePath', str).value()
ZSTACK_UTILITY_SOURCE_DIR = env_var('projectSourceDir', str).value()
DRY_RUN = env_var('dryRun', bool, default=False, required=False).value()
TEST_FOR_OUTPUT_DIR = env_var('outPutDir', str, default='/root/ztest-test-for', required=False).value()
SSH_PRIVATE_KEY = env_var('privateKey', str).value()
COVERAGE = env_var('coverage', bool, default=False, required=False).value()


def log_env_variables():
    logger.debug('environment variables: %s' % jsonobject.dumps(os.environ))


log_env_variables()


def get_test_environment_metadata():
    with open(envFile, "r") as f:
        env = yaml.load(f.read(), Loader=yaml.FullLoader)
        return dict2obj(env["self"])


def get_vm_metadata(vm_name):
    with open(envFile, "r") as f:
        env = yaml.load(f.read(), Loader=yaml.FullLoader)
        return dict2obj(env[vm_name])


class Dict(dict):
    __setattr__ = dict.__setitem__
    __getattr__ = dict.__getitem__


def dict2obj(dictObj):
    if not isinstance(dictObj, dict):
        return dictObj
    d = Dict()
    for k, v in dictObj.items():
        d[k] = dict2obj(v)
    return d
