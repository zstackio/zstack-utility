'''

@author: frank
'''
import sys
import os.path
import ConfigParser
import os
import shutil
import traceback
from zstacklib.utils import shell
import tools

class BuildError(Exception):
    '''build error'''
    def __init__(self, msg):
        content = traceback.format_exc()
        msg = '%s\n%s' % (content, msg)
        super(BuildError, self).__init__(msg)
    
def usage():
    helptxt = '''\build config path must be specified, or there is a default config 'zstack-build.cfg' locates in current folder
Usage: zstackbuild build_config_file_path\
'''
    
class ZstackJava(object):
    def __init__(self):
        self.repo = None
        self.source = None
        self.dist_war = None

class ZstackCommon(object):
    def __init__(self):
        self.repo = None
        self.source = None
    
    def assemble(self, war_path):
        thedict = {
                   "source" : self.source,
                   "componentsHome" : Build.get_component_home(war_path),
                   }
        
        install = [
                   ('$source/zstackagentbase', '$componentsHome/puppet/commonModules/zstackagentbase'),
                   ]        
        
        tools.substitute_copy(install, thedict)
        print "Completed assembling zstackcommon"
    
class ZstackLib(object):
    def __init__(self):
        self.source = None
        self.home = None
        self.dist_egg = None
        
    def assemble(self, war_path):
        thedict = {
                   "source" : self.source,
                   "componentsHome" : Build.get_component_home(war_path),
                   "egg" : self.dist_egg,
                   }
        
        install = [
                   ('$source/puppet/zstacklib', '$componentsHome/puppet/commonModules/zstacklib'),
                   ('$egg', '$componentsHome/puppet/commonModules/zstacklib/files/zstacklib.egg'),
                   ]        
        
        tools.substitute_copy(install, thedict)
        print "Completed assembling zstacklib"
        
        
class ZstackKvmAgent(object):
    def __init__(self):
        self.source = None
        self.home = None
        self.dist_egg = None
        self.dist_service_file = None
        
    def assemble(self, war_path):
        thedict = {
                   "source" : self.source,
                   "componentsHome" : Build.get_component_home(war_path),
                   "egg" : self.dist_egg,
                   "servicefile" : self.dist_service_file,
                   }
        
        install = [
                   ('$source/puppet/kvmagent', '$componentsHome/kvmagent/puppet/kvmagent'),
                   ('$egg', '$componentsHome/kvmagent/puppet/kvmagent/files/zstack-kvmagent.egg'),
                   ('$servicefile', '$componentsHome/kvmagent/puppet/kvmagent/files/'),
                   ]
        
        tools.substitute_copy(install, thedict)
        
        print "Completed assembling kvmagent"

class ZstackSftpBackupStorage(object):
    def __init__(self):
        self.source = None
        self.home = None
        self.dist_egg = None
        self.dist_service_file = None   
    
    def assemble(self, war_path):
        thedict = {
                   "source" : self.source,
                   "componentsHome" : Build.get_component_home(war_path),
                   "egg" : self.dist_egg,
                   "servicefile" : self.dist_service_file,
                   }
        
        install = [
                   ('$source/puppet/sftpbackupstorage', '$componentsHome/sftpbackupstorage/puppet/sftpbackupstorage'),
                   ('$egg', '$componentsHome/sftpbackupstorage/puppet/sftpbackupstorage/files/zstack-sftpbackupstorage.egg'),
                   ('$servicefile', '$componentsHome/sftpbackupstorage/puppet/sftpbackupstorage/files/'),
                   ]
        
        tools.substitute_copy(install, thedict)
        
        print "Completed assembling sftpbackupstorage"       

class ZstackVirtualRouter(object):
    def __init__(self):
        self.source = None
        self.home = None
        self.dist_egg = None
        self.dist_service_file = None
    
    def assemble(self, war_path):
        thedict = {
                   "source" : self.source,
                   "componentsHome" : Build.get_component_home(war_path),
                   "egg" : self.dist_egg,
                   "servicefile" : self.dist_service_file,
                   }
        
        install = [
                   ('$source/puppet/virtualrouter', '$componentsHome/virtualrouter/puppet/virtualrouter'),
                   ('$egg', '$componentsHome/virtualrouter/puppet/virtualrouter/files/zstack-virtualrouter.egg'),
                   ('$servicefile', '$componentsHome/virtualrouter/puppet/virtualrouter/files/'),
                   ]
        
        tools.substitute_copy(install, thedict)
        
        print "Completed assembling virtualrouter"       
        
class Build(object):
    ZSTACK_JAVA_SECTION = 'zstack-java'
    ZSTACK_JAVA_SECTION_SOURCE = 'source'
    ZSTACK_JAVA_SECTION_REPO = 'repo'
    ZSTACK_KVM_AGENT_SECTION = 'zstack-kvmagent'
    ZSTACK_KVM_AGENT_SOURCE = 'source'
    ZSTACK_KVM_AGENT_HOME = 'home'
    ZSTACK_LIB_SECTION = 'zstacklib'
    ZSTACK_LIB_HOME = 'home'
    ZSTACK_LIB_SOURCE = 'source'
    ZSTACK_SFTP_AGENT_SECTION = "zstack-sftpbackupstorage"
    ZSTACK_SFTP_AGENT_SOURCE = 'source'
    ZSTACK_SFTP_AGENT_HOME = 'home'
    ZSTACK_VIRTUAL_ROUTER_SECTION = "zstack-virtualrouter"
    ZSTACK_VIRTUAL_ROUTER_SOURCE = 'source'
    ZSTACK_VIRTUAL_ROUTER_HOME = 'home'
    ZSTACK_COMMON_SECTION = "zstack-common"
    ZSTACK_COMMON_HOME = 'home'
    ZSTACK_COMMON_SOURCE = 'source'
    
    BUILD_DIR = "build"
    ZSTACK_ASSEMBLE = "zstack-assemble"
    CLASSPATH_ROOT = "WEB-INF/classes/"
    COMPONENTS_HOME = "componentsHome"
    PUPPET_COMMON_MODULES = "puppet/commonModules"
    
    def _info(self, msg):
        print '[zstack build]: %s' % msg
        
    @staticmethod
    def get_component_home(war_path):
        return os.path.join(war_path, Build.CLASSPATH_ROOT, Build.COMPONENTS_HOME)
    
    def __init__(self, path):
        self.config_file_path = path
        self.confg_parser = None
        self.zstack_java = ZstackJava()
        self.zstack_kvmagent = ZstackKvmAgent()
        self.zstack_lib = ZstackLib()
        self.zstack_sftp = ZstackSftpBackupStorage()
        self.zstack_virtualrouter = ZstackVirtualRouter()
        self.zstack_common = ZstackCommon()
        self.build_path = None
        
    def _assemble(self):
        war_path = os.path.join(self.build_path, self.ZSTACK_ASSEMBLE)
        shell.ShellCmd('unzip -d %s %s' % (war_path, self.zstack_java.dist_war))()
        self.zstack_lib.assemble(war_path)
        self.zstack_kvmagent.assemble(war_path)
        self.zstack_sftp.assemble(war_path)
        self.zstack_virtualrouter.assemble(war_path)
        self.zstack_common.assemble(war_path)
        
        shell.ShellCmd('jar -cvf zstack.war *', workdir=war_path)()
        shell.ShellCmd('mv %s/zstack.war %s/zstack.war' % (war_path, self.build_path))
        print "Completed assembling finally war file at %s/zstack.war" %  self.build_path
    
    def main(self):
        self.confg_parser = tools.Parser()
        self.confg_parser.read(self.config_file_path)
        self._validate_config_file()
        self._make_build_dir()
        self._build_zstack_java()
        self._build_zstack_lib()
        self._build_zstack_kvmagent()
        self._build_zstack_sftpbackupstorage()
        self._build_zstack_virtualrouter()
        
        self._assemble()
    
    def _build_zstack_lib(self):
        def build_from_source():
            try:
                (egg_name, egg_path) = tools.build_egg(self.zstack_lib.source)
                self.zstack_lib.dist_egg = egg_path
            except Exception as e:
                raise BuildError(str(e))
            
        build_from_source()
            
    def _build_zstack_kvmagent(self):
        def build_from_source():
            try:
                (egg_name, egg_path) = tools.build_egg(self.zstack_kvmagent.source)
                self.zstack_kvmagent.dist_egg = egg_path
                self.zstack_kvmagent.dist_service_file = os.path.join(self.zstack_kvmagent.source, 'zstack-kvmagent')
            except Exception as e:
                raise BuildError(str(e))
            
        build_from_source()
        
    def _build_zstack_sftpbackupstorage(self):
        def build_from_source():
            try:
                (egg_name, egg_path) = tools.build_egg(self.zstack_sftp.source)
                self.zstack_sftp.dist_egg = egg_path
                self.zstack_sftp.dist_service_file = os.path.join(self.zstack_sftp.source, "zstack-sftpbackupstorage")
            except Exception as e:
                raise BuildError(str(e))
        
        build_from_source()
    
    def _build_zstack_virtualrouter(self):
        def build_from_source():
            try:
                (egg_name, egg_path) = tools.build_egg(self.zstack_virtualrouter.source)
                self.zstack_virtualrouter.dist_egg = egg_path
                self.zstack_virtualrouter.dist_service_file = os.path.join(self.zstack_virtualrouter.source, "zstack-virtualrouter")
            except Exception as e:
                raise BuildError(str(e))
        
        build_from_source()
            
    def _build_zstack_java(self):
        def build_from_source():
            try:
                cmdstr ="mvn -DskipTests clean install"
                shell.ShellCmd(cmdstr, workdir=self.zstack_java.source, pipe=False)()
                warstr = "mvn war:war"
                shell.ShellCmd(warstr, workdir=os.path.join(self.zstack_java.source, 'build'), pipe=False)()
                war = os.path.join(self.zstack_java.source, "build/target/zstack.war")
                tools.copy([(war, self.zstack_java.dist_war)])
                self._info("zstack.war is created at %s" % self.zstack_java.dist_war)
            except Exception as e:
                raise BuildError(str(e))
            
        def build_from_repo():
            try:
                self.zstack_java.source = tools.git_clone(self.zstack_java.repo, self.build_path)
                build_from_source()
            except Exception as e:
                raise BuildError(str(e))
                
        self.zstack_java.dist_war = os.path.join(self.build_path, 'zstack.war')
        if self.zstack_java.source:
            build_from_source()
        else:
            build_from_repo()
        
    def _make_build_dir(self):
        build_path = os.path.abspath(self.BUILD_DIR)
        if os.path.exists(build_path):
            shutil.rmtree(build_path)
        os.makedirs(build_path)
        self._info('created build directory %s' % build_path)
        self.build_path = build_path
        
    def _validate_config_file(self):
        def error_if_not_dir(path, section):
            if not os.path.isdir(path):
                raise BuildError('Cannot find %s in section[%s], its not existing or not a dir' % (path, section))
            
        def validate_zstack_java():
            is_source = True
            is_repo = True
            java = self.zstack_java
            java.source = self.confg_parser.get(self.ZSTACK_JAVA_SECTION, self.ZSTACK_JAVA_SECTION_SOURCE)
            if java.source:
                java.source = tools.full_path(java.source)
            else:
                is_source = False
                
            java.repo = self.confg_parser.get(self.ZSTACK_JAVA_SECTION, self.ZSTACK_JAVA_SECTION_REPO)
            if java.repo:
                java.repo = tools.full_path(java.repo)
            else:
                is_repo =False
                
            if not any([is_source, is_repo]):
                raise BuildError("either %s or %s must be set in section[%s]" % (self.ZSTACK_JAVA_SECTION_REPO, self.ZSTACK_JAVA_SECTION_SOURCE, self.ZSTACK_JAVA_SECTION))
            
            if is_source:
                error_if_not_dir(java.source, self.ZSTACK_JAVA_SECTION)
            
        def validate_zstack_kvmagent():
            kvmagent = self.zstack_kvmagent
            kvmagent.source = self.confg_parser.get(self.ZSTACK_KVM_AGENT_SECTION, self.ZSTACK_KVM_AGENT_SOURCE)
            if not kvmagent.source: raise BuildError('section[%s] must contain entry[%s]' % (self.ZSTACK_KVM_AGENT_SECTION, self.ZSTACK_KVM_AGENT_SOURCE))
            kvmagent.source = tools.full_path(kvmagent.source)
            error_if_not_dir(kvmagent.source, self.ZSTACK_KVM_AGENT_SECTION)
            
            kvmagent.home = self.confg_parser.get(self.ZSTACK_KVM_AGENT_SECTION, self.ZSTACK_KVM_AGENT_HOME, default="%s/kvmagent"%self.COMPONENTS_HOME)
            
        
        def validate_zstack_lib():
            zstacklib = self.zstack_lib
            zstacklib.source = self.confg_parser.get(self.ZSTACK_LIB_SECTION, self.ZSTACK_LIB_SOURCE)
            if not zstacklib.source: raise BuildError('section[%s] must contain entry[%s]' % (self.ZSTACK_LIB_SECTION, self.ZSTACK_LIB_SOURCE))
            zstacklib.source = tools.full_path(zstacklib.source)
            error_if_not_dir(zstacklib.source, self.ZSTACK_LIB_SECTION)
            
            zstacklib.home = self.confg_parser.get(self.ZSTACK_LIB_SECTION, self.ZSTACK_LIB_HOME, default="%s/%s"%(self.COMPONENTS_HOME, self.PUPPET_COMMON_MODULES))
        
        def validate_zstack_sftpbackupstorage():
            zstack_sftp = self.zstack_sftp
            zstack_sftp.source = self.confg_parser.get(self.ZSTACK_SFTP_AGENT_SECTION, self.ZSTACK_SFTP_AGENT_SOURCE)
            if not zstack_sftp.source: raise BuildError('section[%s] must contain entry[%s]' % (self.ZSTACK_SFTP_AGENT_SECTION, self.ZSTACK_SFTP_AGENT_SOURCE))
            zstack_sftp.source = tools.full_path(zstack_sftp.source)
            error_if_not_dir(zstack_sftp.source, self.ZSTACK_SFTP_AGENT_SOURCE)
            
            zstack_sftp.home = self.confg_parser.get(self.ZSTACK_SFTP_AGENT_SECTION, self.ZSTACK_SFTP_AGENT_HOME, default="%s/sftpbackupstorage"%(self.COMPONENTS_HOME))
        
        def validate_zstack_virtualrouter():
            zstack_vr = self.zstack_virtualrouter
            zstack_vr.source = self.confg_parser.get(self.ZSTACK_VIRTUAL_ROUTER_SECTION, self.ZSTACK_VIRTUAL_ROUTER_SOURCE)
            if not zstack_vr.source: raise BuildError('section[%s] must contain entry[%s]' % (self.ZSTACK_VIRTUAL_ROUTER_SECTION, self.ZSTACK_VIRTUAL_ROUTER_SOURCE))
            zstack_vr.source = tools.full_path(zstack_vr.source)
            error_if_not_dir(zstack_vr.source, self.ZSTACK_VIRTUAL_ROUTER_SOURCE)
            
            zstack_vr.home = self.confg_parser.get(self.ZSTACK_VIRTUAL_ROUTER_SECTION, self.ZSTACK_VIRTUAL_ROUTER_HOME, default="%s/virtualrouter"%(self.COMPONENTS_HOME))
        
        def validate_zstack_common():
            zstack_common = self.zstack_common
            zstack_common.source = self.confg_parser.get(self.ZSTACK_COMMON_SECTION, self.ZSTACK_COMMON_SOURCE)
            if not zstack_common.source: raise BuildError('section[%s] must contain entry[%s]' % (self.ZSTACK_COMMON_SECTION, self.ZSTACK_COMMON_SOURCE))
            zstack_common.source = tools.full_path(zstack_common.source)
            error_if_not_dir(zstack_common.source, self.ZSTACK_COMMON_SOURCE)
            
        def error_if_missing_section(sections):
            for s in sections:
                if not self.confg_parser.has_section(s): raise BuildError('No secion[%s] in config[%s]' % (s, self.config_file_path))
                
        error_if_missing_section([self.ZSTACK_JAVA_SECTION, self.ZSTACK_KVM_AGENT_SECTION])
        validate_zstack_java()
        validate_zstack_lib()
        validate_zstack_kvmagent()
        validate_zstack_sftpbackupstorage()
        validate_zstack_virtualrouter()
        validate_zstack_common()
        
if __name__ == '__main__':
    if len(sys.argv) >= 2:
        config_path = sys.argv[1]
    else:
        config_path = 'zstack-build.cfg'
        
    config_path = os.path.abspath(config_path)
    if not os.path.exists(config_path):
        usage()
        sys.exit(1)
        
    Build(sys.argv[1]).main()
    sys.exit(0)