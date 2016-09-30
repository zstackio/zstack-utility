'''

@author: frank
'''

from zstacklib.utils import shell
import os.path
import os
import ConfigParser
import shutil
import string

def build_egg(source):
    cmdstr = 'python setup.py bdist_egg'
    shell.ShellCmd(cmdstr, workdir=source, pipe=False)()
    lsegg = shell.ShellCmd('ls %s/dist' % source)
    lsegg()
    egg_name = lsegg.stdout.strip()
    egg_path = os.path.join(source, 'dist', egg_name) 
    return (egg_name, egg_path)

def git_clone(repo, dst):
    before = os.listdir(dst)
    clonestr = 'git clone %s' % repo
    shell.ShellCmd(clonestr, workdir=dst, pipe=False)()
    after = os.listdir(dst)
    reponame = [x for x in after if x not in before]
    assert len(reponame) == 1, "why not only one repo names%s ??? " % reponame
    return os.path.join(dst, reponame[0])

def full_path(path):
    return os.path.expanduser(path) if path.startswith('~') else os.path.abspath(path)

def substitute_copy(pairs, thedict):
    lst = []
    for (src, dst) in pairs:
        t = string.Template(src)
        nsrc = t.substitute(thedict)
        t = string.Template(dst)
        ndst = t.substitute(thedict)
        lst.append((nsrc, ndst))
    copy(lst)
    
def copy(pairs):
    for (src, dst) in pairs:
        src = full_path(src)
        dst = full_path(dst)
        if os.path.isdir(src):
            if os.path.isdir(dst):
                os.removedirs(dst)
            elif os.path.exists(dst):
                os.remove(dst)
            print "copying dir %s to %s" % (src, dst)
            shutil.copytree(src, dst)
        else:
            print "copying %s to %s" % (src, dst)
            shutil.copy2(src, dst)
    
class Parser(ConfigParser.SafeConfigParser):
    def get(self, section, option, default=None):
        try:
            return ConfigParser.SafeConfigParser.get(self, section, option)
        except ConfigParser.NoOptionError:
            return default