'''

@author: frank
'''

from zstacklib.utils import http
from zstacklib.utils import shell
from zstacklib.utils import uuidhelper
import sys
import os
import optparse
import re
import readline
import traceback
import string


class Completer(object):

    COMMANDS = ['file', 'cmd']
    RE_SPACE = re.compile('.*\s+$', re.M)

    def _listdir(self, root):
        "List directory 'root' appending the path separator to subdirs."
        res = []
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if os.path.isdir(path):
                name += os.sep
            res.append(name)
        return res

    def _complete_path(self, path=None):
        "Perform completion of filesystem path."
        if not path:
            return self._listdir('.')
        dirname, rest = os.path.split(path)
        tmp = dirname if dirname else '.'
        res = [os.path.join(dirname, p)
                for p in self._listdir(tmp) if p.startswith(rest)]
        # more than one match, or single match which does not exist (typo)
        if len(res) > 1 or not os.path.exists(path):
            return res
        # resolved to a single directory, so return list of files below it
        if os.path.isdir(path):
            return [os.path.join(path, p) for p in self._listdir(path)]
        # exact file match terminates this completion
        return [path + ' ']

    def complete_file(self, args):
        "Completions for the 'extra' command."
        if not args:
            return self._complete_path('.')
        # treat the last arg as a path and complete it
        return self._complete_path(args[-1])

    def complete(self, text, state):
        "Generic readline completion entry point."
        buffer = readline.get_line_buffer()
        line = readline.get_line_buffer().split()
        # show all commands
        if not line:
            return [c + ' ' for c in self.COMMANDS][state]
        # account for last argument ending in a space
        if self.RE_SPACE.match(buffer):
            line.append('')
        # resolve command to the implementation function
        cmd = line[0].strip()
        if cmd in self.COMMANDS:
            impl = getattr(self, 'complete_%s' % cmd)
            args = line[1:]
            if args:
                return (impl(args) + [None])[state]
            return [cmd + ' '][state]
        results = [c + ' ' for c in self.COMMANDS if c.startswith(cmd)] + [None]
        return results[state]

class CliError(Exception):
    '''Cli Error'''

class Cli(object):
    def __init__(self, options):
        self.options = options
        self.agent_ip = options.ip
        self.agent_port = options.port
        self.cip = options.cip
        
        self.http_server = http.HttpServer(port=10086)
        self.http_server.register_sync_uri('/result', self.callback)
        self.http_server.start_in_thread()
        print ""
        
        comp = Completer()
        readline.set_completer_delims(' \t\n;')
        readline.set_completer(comp.complete)
        readline.parse_and_bind("tab: complete")

    def callback(self, req):
        print req[http.REQUEST_BODY]

    def print_error(self, err):
        print '\033[91m' + err + '\033[0m'

    def do_command(self, line):
        def from_file(tokens):
            file_path = tokens[1]
            file_path = os.path.abspath(file_path)
            if not os.path.exists(file_path):
                self.print_error('cannot find file %s' % file_path)
                return
            
            with open(file_path, 'r') as fd:
                text = fd.read()
                
                path, json_str = text.split('>>', 1)
                path = path.strip(' \t\n\r')
                json_str = json_str.strip(' \t\n\r')

            args = {}
            if len(tokens) > 2:
                for token in tokens[2:]:
                    k, v = token.split('=', 1)
                    args[k] = v
            
            tmp = string.Template(json_str)
            json_str = tmp.substitute(args)
            url = 'http://%s:%s/%s/' % (self.agent_ip, self.agent_port, path)
            callback_url = 'http://%s:%s/%s/' % (self.cip, 10086, 'result')
            rsp = http.json_post(url, json_str, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:callback_url})
            print rsp
            
        
        def from_text(tokens):
            pass

        tokens = line.split()
        cmd = tokens[0]
        if cmd == 'file':
            from_file(tokens)
        elif cmd == 'call':
            from_text(tokens)
        else:
            self.print_error('unkonwn command: %s. only "file" or "call" allowed' % cmd)

    def run(self):
        while True:
            try:
                line = raw_input('>>>')
                if line:
                    self.do_command(line)
            except CliError as clierr:
                self.print_error(str(clierr))
            except (EOFError, KeyboardInterrupt):
                print ''
                self.http_server.stop()
                sys.exit(1)
            except:
                content = traceback.format_exc()
                self.print_error(content)

def main():
    parser = optparse.OptionParser()
    parser.add_option("-p", "--port", dest="port", help="port for agent server")
    parser.add_option("-i", "--ip", dest="ip", default='127.0.0.1', help="ip for agent server")
    parser.add_option("-c", "--callback-ip", dest="cip", default='127.0.0.1', help="ip for callback http server")
    (options, args) = parser.parse_args()
    if not options.port:
        parser.print_help()
        parser.error('--port must be specified')

    Cli(options).run()

if __name__ == "__main__":
    main()