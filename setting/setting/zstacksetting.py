'''

@author: Frank
'''

from zstacklib.utils import log

log.configure_log("/var/log/zstack/zstack-setting.log", log_to_console=False)
logger = log.get_logger(__name__)

from zstacklib.utils import plugin
from zstacklib.utils import linux
from zstacklib.utils import xmlobject
from zstacklib.utils import shell
import os.path
import os
import argparse
import sys
import re
import datetime
import textwrap

class SettingPlugin(plugin.Plugin):
    def start(self):
        pass
    
    def stop(self):
        pass
    
    def check_system(self):
        pass
        
    def add_subcommand(self, subcommand_parser):
        pass
    
    def finalize(self):
        pass

class SettingError(Exception):
    pass

class Property(object):
    def __init__(self):
        self.name = None
        self.dest = None
        self.xmlobj = None
        self.option_name = None
        
class Setting(object):
    HOME_DIR = os.path.expanduser('~/.zstack-setting')
    BACKUP_DIR = os.path.join(HOME_DIR, 'backup')
    SYSTEM_CHNAGE_HISTROY_DIR = os.path.join(HOME_DIR, 'system-changes-history')
    PROPERTIES_BACKUP_DIR = os.path.join(BACKUP_DIR, 'properties')
    
    system_change_info = []
    
    def _create_backup_folder(self):
        if not os.path.exists(self.HOME_DIR):
            os.makedirs(self.HOME_DIR, 0755)
        if not os.path.exists(self.BACKUP_DIR):
            os.makedirs(self.BACKUP_DIR, 0755)
        if not os.path.exists(self.SYSTEM_CHNAGE_HISTROY_DIR):
            os.makedirs(self.SYSTEM_CHNAGE_HISTROY_DIR, 0755)
        if not os.path.exists(self.PROPERTIES_BACKUP_DIR):
            os.makedirs(self.PROPERTIES_BACKUP_DIR, 0755)
            
    def __init__(self):
        self.plugin_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plugins')
        self.plugin_rgty = plugin.PluginRegistry(self.plugin_path)
        self.properties = []
        self.properties_map = {}
        self.template_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'property-templates')
        self.parser = argparse.ArgumentParser(prog='zstack-setting', description="zstack setting tool",
                                              formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        self.subparsers = self.parser.add_subparsers(title='commands', metavar='')
        self.settting_command = self.subparsers.add_parser('setting', help="configure zstack management", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        self.settting_command.set_defaults(func=self._setting)
        self.settings = []
        
        self._create_backup_folder()
    
    def _setting(self, options):
        def validate(restr, option_name, val, err_msg):
            p = re.compile(restr)
            if not p.search(val):
                err = "value[%s] of %s doesn't match regular expression[%s]" % (val, option_name, restr)
                if err_msg:
                    err = '%s\n%s' % (err, err_msg)
                raise SettingError(err)
        
        def check_exists(option_name, val):
            if not os.path.exists(val):
                err = '%s of %s is not existing in filesystem' % (val, option_name)
                raise SettingError(err)
        
        def write_properties_file():
            content = []
            property_file = os.path.join(self.HOME_DIR, 'zstack.properties')
            for name, value in self.settings:
                po = self.properties_map[name]
                if xmlobject.has_element(po.xmlobj, 'help'):
                    wrapper = textwrap.TextWrapper()
                    help = wrapper.wrap(po.xmlobj.help.text_)
                    help = ['# %s' % h for h in help]
                    help = [re.sub(r' +', ' ', h) for h in help]
                    content.extend(help)
                content.append('%s=%s\n' % (name, value))
            
            if os.path.exists(property_file):
                backup_file(property_file, self.PROPERTIES_BACKUP_DIR)
            
            with open(property_file, 'w') as fd:
                fd.write('\n'.join(content))
            
            print 'wrote all settings to %s' % property_file
        
        dopetions = vars(options)
        for name, p in self.properties:
            s = dopetions[p.dest]
            xo = p.xmlobj
            if xmlobject.has_element(xo, 'validator'):
                restr = xo.validator.text_
                err_msg = None
                if xmlobject.has_element(xo, 'errorMessage'):
                    err_msg = xo.errorMessage.text_
                validate(restr, p.option_name, s, err_msg)
            
            if xmlobject.has_element(xo, 'checkExists'):
                check_exists(p.option_name, s)
                
            self.settings.append((name, s))
        
        write_properties_file()
                
    def _build_setting_command_from_templates(self):
        def build_property_option(xo):
            for p in xo.get_child_node_as_list('property'):
                name = p.name.text_
                pairs = name.split('.')
                dest = '%s_%s' % (pairs[0], pairs[1])
                option_name = '--%s-%s' % (pairs[0], pairs[1])
                help = None
                if xmlobject.has_element(p, 'help'):
                    help = p.help.text_
                default = None
                if xmlobject.has_element(p, 'default'):
                    default = p.default.text_
                
                self.settting_command.add_argument(option_name, dest=dest, default=default, help=help)
                
                po = Property()
                po.name = name
                po.dest = dest
                po.xmlobj = p
                po.option_name = option_name
                self.properties.append((name, po))
                self.properties_map[name] = po
        
        templates = os.listdir(self.template_path)
        for t in templates:
            tpath = os.path.join(self.template_path, t)
            logger.debug('load xml %s' % tpath)
            if not tpath.endswith('.xml'):
                logger.warn('ignore none xml template %s' % tpath)
                continue
            
            xo = xmlobject.loads_from_xml_file(tpath)
            build_property_option(xo)
        
    def _print_system_change_info(self):
        if not self.system_change_info:
            return
        
        changes = []
        changes.append('zstack-setting has made below changes in your system:')
        changes.append('-----------------------------------------------------')
        for c in self.system_change_info:
            changes.append('[CHANGE]: %s' % c)
        changes.append('-----------------------------------------------------')
        
        info = '\n'.join(changes)
        history = datetime.datetime.now().strftime('%b-%d-%y-%H-%M-%S')
        history_file = os.path.join(self.SYSTEM_CHNAGE_HISTROY_DIR, history)
        with open(history_file, 'w') as fd:
            fd.write(info)
        
        print info
        print '\nthis change info has been saved to %s' % history_file
        
        
    def main(self):
        try:
            for p in self.plugin_rgty.get_plugins():
                p.check_system()
                p.add_subcommand(self.subparsers)
                
            self._build_setting_command_from_templates()
            options = self.parser.parse_args()
            options.func(options)
            self._print_system_change_info()
        except SettingError as se:
            print str(se)
            sys.exit(1)
        except Exception:
            print 'internal error happened, check /var/log/zstack/zstack-setting.log for details'
            err = linux.get_exception_stacktrace()
            logger.warn(err)
            sys.exit(1)

def get_resource_file(filename, subfolder=None):
    resource = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resource')
    if subfolder:
        ret = os.path.join(resource, subfolder, filename)
    else:
        ret = os.path.join(resource, filename)
        
    if not os.path.exists(ret):
        raise Exception('cannot find %s' % ret)
    return ret
    
def report_system_change(info):
    Setting.system_change_info.append(info)
    
def backup_file(filepath, subfolder=None):
    if not os.path.isfile(filepath):
        raise Exception('cannot find %s to backup' % filepath)
    
    tdir = datetime.datetime.now().strftime('%b-%d-%y-%H-%M-%S')
    if subfolder:
        dst_dir = os.path.join(Setting.BACKUP_DIR, subfolder, tdir)
    else:
        dst_dir = os.path.join(Setting.BACKUP_DIR, tdir)
    
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir, 0755)
    
    shell.call('yes | cp -f %s %s' % (filepath, dst_dir))
    bk = os.path.join(dst_dir, os.path.basename(filepath))
    report_system_change('back up file %s to %s' % (filepath, bk))
    return bk

def backup_dir(dirpath, subfolder=None):
    if not os.path.isdir(dirpath):
        raise Exception('cannot find %s to backup' % dirpath)
    
    tdir = datetime.datetime.now().strftime('%b-%d-%y-%H-%M-%S')
    if subfolder:
        dst_dir = os.path.join(Setting.BACKUP_DIR, subfolder, tdir)
    else:
        dst_dir = os.path.join(Setting.BACKUP_DIR, tdir)
    
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir, 0755)
    
    shell.call('yes | cp -rf %s %s' % (dirpath, dst_dir))
    bk = os.path.join(dst_dir, os.path.basename(dirpath))
    report_system_change('back up directory %s to %s' % (dirpath, bk))
    return bk
    
def main():
    Setting().main()
        