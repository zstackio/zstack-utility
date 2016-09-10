'''

@author: Frank
'''
import os
try:
    if os.environ['TERM'].startswith('xterm'):
        os.environ['TERM'] = 'vt100'
except:
    os.environ['TERM'] = 'vt100'

import readline
import sys
reload(sys)
sys.setdefaultencoding('utf8')
import shlex
import hashlib
import optparse
import termcolor
import pydoc
import time
import urllib3

import zstacklib.utils.log as log
#comment out next line to print detail zstack cli http command to screen.
log.configure_log('/var/log/zstack/zstack-cli', log_to_console=False)

import apibinding.inventory as inventory
import apibinding.api as api
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.filedb as filedb
import zstackcli.parse_config as parse_config
import zstackcli.deploy_config as deploy_config
import zstackcli.read_config as read_config


cld = termcolor.colored
cprint = termcolor.cprint

text_doc = pydoc.TextDoc()

CLI_LIB_FOLDER = os.path.expanduser('~/.zstack/cli')
CLI_HISTORY = '%s/command_history' % CLI_LIB_FOLDER
CLI_RESULT_HISTORY_FOLDER = '%s/result_history' % CLI_LIB_FOLDER
CLI_RESULT_HISTORY_KEY = '%s/result_key' % CLI_RESULT_HISTORY_FOLDER
CLI_RESSULT_FILE = '%s/result' % CLI_RESULT_HISTORY_FOLDER
SESSION_FILE = '%s/session' % CLI_LIB_FOLDER
CLI_MAX_CMD_HISTORY = 1000
CLI_MAX_RESULT_HISTORY = 1000
prompt = '>>>'

query_param_keys = \
        ['conditions', 'count', 'limit', 'start', 'timeout', \
        'replyWithCount', 'sortBy', 'sortDirection', 'fields']

NOT_QUERY_MYSQL_APIS = ['APIQueryResourcePriceMsg', \
        'QueryResourcePrice', \
        'APIQueryLogMsg', \
        'QueryLog' \
        ]

def clean_password_in_cli_history():
    cmd_historys = open(CLI_HISTORY, 'r').readlines()
    new_cmd_historys = []
    for cmd in cmd_historys:
        if 'password=' in cmd:
            cmd_params = cmd.split()
            cmd_list = []
            for param in cmd_params:
                if not 'password=' in param:
                    cmd_list.append(param)
                else:
                    cmd_list.append(param.split('=')[0] + '=')
            new_cmd_historys.append(' '.join(cmd_list))
        else:
            new_cmd_historys.append(cmd)
    open(CLI_HISTORY, 'w').write('\n'.join(new_cmd_historys))

class CliError(Exception):
    '''Cli Error'''

class Cli(object):
    '''
    classdocs
    '''

    msg_creator = {}

    LOGIN_MESSAGE_NAME = 'APILogInByAccountMsg'
    LOGIN_BY_LDAP_MESSAGE_NAME = 'APILogInByLdapMsg'
    LOGOUT_MESSAGE_NAME = 'APILogOutMsg'
    LOGIN_BY_USER_NAME = 'APILogInByUserMsg'
    CREATE_ACCOUNT_NAME = 'APICreateAccountMsg'
    CREATE_USER_NAME = 'APICreateUserMsg'
    ACCOUNT_RESET_PASSWORD_NAME = 'APIUpdateAccountMsg'
    USER_RESET_PASSWORD_NAME = 'APIUpdateUserMsg'

    @staticmethod
    def register_message_creator(apiname, func):
        Cli.msg_creator[apiname] = func

    def usage(self):
        print '''
  ZStack command line tool
  Type "help" for more information
  Type Tab key for auto-completion
  Type "quit" or "exit" or Ctrl-d to exit

'''

    def print_error(self, err):
        print '\033[91m' + err + '\033[0m'

    def complete(self, pattern, index):
        '''
        pattern is current input. index is current matched number of list.
        complete will be kept calling, until it return None.
        '''
        def prepare_primitive_fields_words(apiname, separator='=', prefix=''):
            if not prefix:
                api_map_name = inventory.queryMessageInventoryMap[apiname].__name__
            else:
                api_map_name = apiname

            query_pri_fields = eval('inventory.%s().PRIMITIVE_FIELDS' % api_map_name)
            query_pri_fields = ['%s' % field for field in query_pri_fields]
            temp_fields = list(query_pri_fields)
            query_pri_fields = []
            for field in temp_fields:
                if prefix:
                    query_pri_fields.append('%s%s%s' % (prefix, field, separator))
                else:
                    query_pri_fields.append('%s%s' % (field, separator))

            self.words.extend(query_pri_fields)

        def prepare_expanded_fields_words(apiname, separator='.', prefix=''):
            if not prefix:
                api_map_name = inventory.queryMessageInventoryMap[apiname].__name__
            else:
                api_map_name = apiname
            query_ext_fields = eval('inventory.%s().EXPANDED_FIELDS' % api_map_name)
            query_ext_fields = ['%s' % field for field in query_ext_fields]
            temp_fields = list(query_ext_fields)
            query_ext_fields = []
            for field in temp_fields:
                if prefix:
                    query_ext_fields.append('%s%s%s' % (prefix, field, separator))
                else:
                    query_ext_fields.append('%s%s' % (field, separator))

            self.words.extend(query_ext_fields)
            if 'conditions=' in self.words:
                self.words.remove('conditions=')

        def prepare_query_words(apiname, prefix=''):
            prepare_primitive_fields_words(apiname, '=', prefix)
            prepare_expanded_fields_words(apiname, '.', prefix)

        def prepare_fields_words(apiname, current_fields=[]):
            prepare_primitive_fields_words(apiname, ',')
            for field in current_fields:
                new_field = '%s,' % field
                if new_field in self.words:
                    self.words.remove(new_field)

        def prepare_words():
            currtext = readline.get_line_buffer()
            apiname = currtext.split()[0]
            if apiname in self.words_db:
                self.is_cmd = False
                self.words = ['%s=' % field for field in self.api_class_params['API%sMsg' % apiname]]
                if apiname.startswith('Query') and not apiname in NOT_QUERY_MYSQL_APIS:
                    real_api_name = 'API%sMsg' % apiname
                    prepare_query_words(real_api_name)
                    if not ('UserTag' in apiname or 'SystemTag' in apiname):
                        self.words.append('__systemTag__=')
                        self.words.append('__userTag__=')
            else:
                self.is_cmd = True
                self.words = self.words_db

        if not self.words:
            return None

        prepare_words()

        if not self.curr_pattern or pattern.lower() != self.curr_pattern.lower():
            #self.matching_words = [w for w in self.words if w.lower().startswith(pattern.lower())]
            if self.is_cmd:
                self.matching_words = ['%s ' % w for w in self.words if pattern.lower() in w.lower()]
            else:
                #need to auto complete expanded fields.
                if '.' in pattern:
                    currtext = readline.get_line_buffer()
                    fields_objects = pattern.split('.')
                    head_field = fields_objects[0]
                    fields_num = len(fields_objects)
                    apiname = currtext.split()[0]
                    new_api_name = 'API%sMsg' % apiname
                    if inventory.queryMessageInventoryMap.has_key(new_api_name):
                        api_obj_name = inventory.queryMessageInventoryMap[new_api_name].__name__
                        query_ext_fields = eval('inventory.%s().EXPANDED_FIELDS' % api_obj_name)
                        if head_field in query_ext_fields:
                            current_obj_name = eval('inventory.%s().QUERY_OBJECT_MAP["%s"]' % (api_obj_name, head_field))

                            for i in range(0, fields_num):
                                if i == fields_num - 2:
                                    break
                                next_field = fields_objects[i + 1]
                                query_ext_fields = eval('inventory.%s().EXPANDED_FIELDS' % current_obj_name)
                                if next_field in query_ext_fields:
                                    current_obj_name = eval('inventory.%s().QUERY_OBJECT_MAP["%s"]' % (current_obj_name, next_field))
                                else:
                                    current_obj_name = None
                        else:
                            current_obj_name = None
                    else:
                        current_obj_name = None

                    if current_obj_name:
                        self.words = []
                        pattern_prefix = '.'.join(fields_objects[:-1])
                        prepare_query_words(current_obj_name, '%s.' % pattern_prefix)

                currtext = readline.get_line_buffer()
                last_field = currtext.split()[-1]
                if not currtext.endswith(' ') and last_field.startswith('fields='):
                    apiname = currtext.split()[0]
                    new_api_name = 'API%sMsg' % apiname
                    api_map_name = inventory.queryMessageInventoryMap[new_api_name].__name__
                    self.words = []
                    fields = last_field.split('=')[1]
                    prepare_fields_words(new_api_name, fields.split(','))

                self.matching_words = [w for w in self.words if pattern.lower() in w.lower()]

            self.curr_pattern = pattern

        try:
            return self.matching_words[index]
        except IndexError:
            return None

    def do_command(self, line):
        def check_session(apiname):
            if not self.session_uuid and apiname not in [self.LOGIN_MESSAGE_NAME, self.LOGIN_BY_USER_NAME, self.LOGIN_BY_LDAP_MESSAGE_NAME]:
                self.print_error('''Please login before running any API message
example: %sLogInByAccount accountName=admin password=your_super_secure_admin_password''' % prompt)
                return False
            return True

        def is_api_param_a_list(apiname, param):
            optional_list = eval('isinstance(inventory.%s().%s, \
                    inventory.OptionalList)' % (apiname, param))
            not_none_list = eval('isinstance(inventory.%s().%s, \
                    inventory.NotNoneList)' % (apiname, param))
            if optional_list or not_none_list:
                return True

        def build_params():
            def eval_string(key, value_string):
                try:
                    return eval(value_string)
                except Exception as e:
                    err_msg = """
Parse command parameters error:
  eval '%s' error for: '%s'
  the right format is like: "[{'KEY':'VALUE'}, {'KEY':['VALUE1', 'VALUE2']}]"
                          """ % (value_string, key)
                    self.print_error(err_msg)
                    raise e

            pairs = shlex.split(line)
            if pairs[0] in self.cli_cmd:
                cmd = pairs[0]
                if len(pairs) > 1:
                    return cmd, pairs[1:]
                else:
                    return cmd, None

            apiname = 'API%sMsg' % pairs[0]
            if apiname not in inventory.api_names:
                raise CliError('"%s" is not an API message' % apiname)

            #'=' will be used for more meanings than 'equal' in Query API
            if apiname.startswith('APIQuery') and not apiname in NOT_QUERY_MYSQL_APIS:
                return apiname, pairs[1:]

            all_params = {}
            for param_str in pairs[1:]:
                params = param_str.split('=', 1)
                if len(params) != 2:
                    raise CliError('Invalid parameter[%s], the parameter must be split by "="' % param_str)

                if apiname == 'APIAddSecurityGroupRuleMsg' and params[0] == 'rules':
                    all_params[params[0]] = eval(params[1])
                elif apiname in ['APIGetHostMonitoringDataMsg', 'APIGetVmMonitoringDataMsg', 'APIMonitoringPassThroughMsg'] and params[0] == 'query':
                    all_params[params[0]] = eval(params[1])
                elif apiname == 'APIAttachNetworkServiceToL3NetworkMsg' and params[0] == 'networkServices':
                    all_params[params[0]] = eval_string(params[0], params[1])
                elif apiname == 'APIDetachNetworkServiceFromL3NetworkMsg' and params[0] == 'networkServices':
                    all_params[params[0]] = eval_string(params[0], params[1])
                elif apiname == 'APICreatePolicyMsg' and params[0] == 'statements':
                    all_params[params[0]] = eval_string(params[0], params[1])
                elif is_api_param_a_list(apiname, params[0]):
                    all_params[params[0]] = params[1].split(',')
                else:
                    all_params[params[0]] = params[1]

            return (apiname, all_params)

        def generate_query_params(apiname, params):
            '''
            Query params will include conditions expression, which includes ops:
            =, !=, >, <, >=, <=, ?=, !?=, ~=, !~=
            ?= means 'in'
            !?= means 'not in'
            ~= means 'like'
            !~= means 'not like'
            =null means 'is null'
            !=null means 'is not null'
            '''

            null = 'null'
            eq = '='
            gt = '>'
            lt = '<'
            nt = '!'
            lk = '~'
            qs = '?'
            ps = '+'
            ms = '-'
            perc = '%'
            underscore = '_'

            conditions = []
            new_params = {}

            for param in params:
                if eq in param:
                    key,value = param.split(eq, 1)
                    if not key in query_param_keys:
                        if key.endswith(nt):
                            if value != null:
                                conditions.append({'name':key[:-1], \
                                        'op':'!=', 'value': value})
                            else:
                                conditions.append({'name':key[:-1], \
                                        'op':'is not null', 'value': ''})

                        elif key.endswith(gt):
                            conditions.append({'name':key[:-1], \
                                    'op':'>=', 'value': value})

                        elif key.endswith(lt):
                            conditions.append({'name':key[:-1], \
                                    'op':'<=', 'value': value})

                        elif key.endswith('%s%s' % (nt, qs)):
                            conditions.append({'name':key[:-2], \
                                    'op':'not in', 'value': value})

                        elif key.endswith(qs):
                            conditions.append({'name':key[:-1], \
                                    'op':'in', 'value': value})

                        elif key.endswith('%s%s' % (nt, lk)):
                            #will help to add pattern %, if user not input
                            if not perc in value and not underscore in value:
                                value = '%s%s%s' % (perc, value, perc)
                            conditions.append({'name':key[:-2], \
                                    'op':'not like', 'value': value})

                        elif key.endswith(lk):
                            #will help to add pattern %, if user not input
                            if not perc in value and not underscore in value:
                                value = '%s%s%s' % (perc, value, perc)
                            conditions.append({'name':key[:-1], \
                                    'op':'like', 'value': value})

                        else:
                            if value != null:
                                conditions.append({'name':key, \
                                        'op':eq, 'value': value})
                            else:
                                conditions.append({'name':key, \
                                        'op':'is null', 'value': ''})

                    elif key == 'conditions':
                        conditions.extend(eval(value))

                    elif key == 'fields':
                        #remove the last ','
                        if value.endswith(','):
                            value = value[:-1]
                        new_params[key] = value.split(',')

                    else:
                        if is_api_param_a_list(apiname, key):
                            new_params[key] = value.split(',')
                        else:
                            new_params[key] = value

                elif gt in param:
                    key,value = param.split(gt, 1)
                    conditions.append({'name':key, \
                            'op':gt, 'value': value})

                elif lt in param:
                    key,value = param.split(lt, 1)
                    conditions.append({'name':key, \
                            'op':lt, 'value': value})

            new_params['conditions'] = conditions
            return new_params

        def create_msg(apiname, params):
            creator = self.msg_creator.get(apiname)
            if creator:
                return creator(apiname, params)

            if apiname.startswith('APIQuery')  and not apiname in NOT_QUERY_MYSQL_APIS:
                params = generate_query_params(apiname, params)

            msg = eval('inventory.%s()' % apiname)
            for key in params.keys():
                value = params[key]
                setattr(msg, key, value)
            return msg

        def set_session_to_api(msg):
            session = inventory.Session()
            session.uuid = self.session_uuid
            msg.session = session


        (apiname, all_params) = build_params()
        if apiname in self.cli_cmd:
            #self.write_more(apiname, None)
            self.cli_cmd_func[apiname](all_params)
            return

        if not check_session(apiname):
            raise CliError("No session uuid defined")

        msg = create_msg(apiname, all_params)
        set_session_to_api(msg)
        try:
            if apiname in [self.LOGIN_MESSAGE_NAME, self.LOGIN_BY_USER_NAME, self.CREATE_ACCOUNT_NAME, self.CREATE_USER_NAME]:
                if not msg.password:
                    raise CliError('"password" must be specified')
                msg.password = hashlib.sha512(msg.password).hexdigest()

            if apiname in [self.USER_RESET_PASSWORD_NAME, self.ACCOUNT_RESET_PASSWORD_NAME]:
                if msg.password:
                    msg.password = hashlib.sha512(msg.password).hexdigest()

            if apiname == self.LOGOUT_MESSAGE_NAME:
                if not msg.sessionUuid:
                    setattr(msg, 'sessionUuid', self.session_uuid)

            start_time = time.time()
            (name, event) = self.api.async_call_wait_for_complete(msg, fail_soon=True)
            end_time = time.time()

            if apiname in [self.LOGIN_MESSAGE_NAME, self.LOGIN_BY_USER_NAME, self.LOGIN_BY_LDAP_MESSAGE_NAME]:
                self.session_uuid = event.inventory.uuid
                open(SESSION_FILE, 'w').write(self.session_uuid)

            result = jsonobject.dumps(event, True)
            print '%s\n' % result
            #print 'Time costing: %fs' % (end_time - start_time)
            self.write_more(line, result)
        except urllib3.exceptions.MaxRetryError as urlerr:
            self.print_error('Is %s reachable? Please make sure the management node is running.' % self.api.api_url)
            self.print_error(str(urlerr))
            raise ("Server: %s is not reachable" % self.hostname)
        except Exception as e:
            self.print_error(str(e))
            self.write_more(line, str(e), False)
            raise e

    def main(self, cmd = None):
        if not cmd:
            self.usage()

        exit_code = 0

        import atexit
        if not os.path.exists(os.path.dirname(CLI_HISTORY)):
            os.system('mkdir -p %s' % os.path.dirname(CLI_HISTORY))
        atexit.register(clean_password_in_cli_history)
        atexit.register(readline.write_history_file, CLI_HISTORY)

        while True:
            try:
                if cmd:
                    self.do_command(cmd)
                else:
                    line = raw_input(prompt)
                    if line:
                        self.do_command(line)
            except CliError as clierr:
                self.print_error(str(clierr))
                exit_code = 1
            except (EOFError):
                print ''
                sys.exit(1)
            except (KeyboardInterrupt):
                print ''
            except Exception as e:
                exit_code = 3
                self.print_error(str(e))

            if cmd:
                sys.exit(exit_code)

    def build_api_parameters(self):
        def rule_out_unneeded_params(keys):
            excludes = ['session']
            for k in excludes:
                if k in keys:
                    keys.remove(k)
            return keys

        for apiname in inventory.api_names:
            obj = eval("inventory.%s()" % apiname)
            params = []
            params.extend(obj.__dict__.keys())
            self.api_class_params[apiname] = rule_out_unneeded_params(params)

    def _parse_api_name(self, api_names):
        '''
        Remove API pattern 'API' and appendix 'MSG'
        '''
        short_api_name = []
        for api in api_names:
            if api.endswith('Msg'):
                short_api_name.append(api[3:-3])

        short_api_name.sort()
        return short_api_name

    def completer_print(self, substitution, matches, longest_match_length) :
        def print_match(columes, new_matches, max_match_length):
            cur_col = 1

            for match in new_matches:
                if cur_col == columes:
                    end_sign = '\n'
                    cur_col = 1
                else:
                    end_sign = ' ' * (max_match_length - len(match))
                    cur_col += 1

                try:
                    index = match.lower().index(self.curr_pattern.lower())
                except Exception as e:
                    print "can't find pattern: %s in match: %s" % (self.curr_pattern, match)
                    print e
                    raise e

                cprint(match[0:index], end='')
                cprint(match[index:(len(self.curr_pattern) + index)], attrs=['bold', 'reverse'], end='')
                cprint(match[(len(self.curr_pattern) + index):], end=end_sign)

        def print_bold():
            max_match_length = 0
            matches_dot = []
            matches_eq_cond = []
            matches_eq_param = []
            matches_ot = []
            currtext = readline.get_line_buffer()
            apiname = currtext.split()[0]
            if apiname.startswith('Query') and not apiname in NOT_QUERY_MYSQL_APIS:
                query_cmd = True
            else:
                query_cmd = False

            for match in matches:
                if len(match) > max_match_length:
                    max_match_length = len(match)
                if match.endswith('.'):
                    matches_dot.append(match)
                elif match.endswith('='):
                    for key in query_param_keys:
                        if query_cmd and match.startswith(key):
                            matches_eq_param.append(match)
                            break
                    else:
                        matches_eq_cond.append(match)
                else:
                    matches_ot.append(match)

            max_match_length += 2

            try:
                term_width = int(os.popen('stty size', 'r').read().split()[1])
            except:
                term_width = 80

            columes = term_width/max_match_length
            if columes == 0:
                columes = 1

            if matches_dot:
                if query_cmd:
                    cprint('[Query Conditions:]', attrs=['bold'], end='\n')
                print_match(columes, matches_dot, max_match_length)
                print '\n'
            if matches_eq_cond:
                #cprint('[Primitive Query Conditions:]', attrs=['bold'], end='\n')
                print_match(columes, matches_eq_cond, max_match_length)
                print '\n'
            if matches_eq_param:
                if query_cmd:
                    cprint('[Parameters:]', attrs=['bold'], end='\n')
                print_match(columes, matches_eq_param, max_match_length)
                print '\n'
            if matches_ot:
                print_match(columes, matches_ot, max_match_length)
                print '\n'

        print ''
        print_bold()
        print ''
        cprint('%s%s' % (prompt, readline.get_line_buffer()), end='')
        #readline.redisplay()

    def write_more(self, cmd, result, success=True):
        if self.hd.get(self.start_key):
            start_value = int(self.hd.get(self.start_key))
        else:
            start_value = 0

        if self.hd.get(self.last_key):
            last_value = int(self.hd.get(self.last_key))
        else:
            last_value = 0

        if last_value <= start_value:
            if start_value < CLI_MAX_RESULT_HISTORY:
                start_value += 1
            else:
                start_value = 1
                last_value = 2
        else:
            if last_value < CLI_MAX_RESULT_HISTORY:
                start_value += 1
                last_value += 1
            else:
                start_value += 1
                last_value = 1

        self.hd.set(self.start_key, start_value)
        self.hd.set(self.last_key, last_value)
        #filedb might leave more than 1 same key item.
        while self.hd.get(str(start_value)):
            self.hd.rem(str(start_value))

        result_file = '%s%d' % (CLI_RESSULT_FILE, start_value)
        open(result_file, 'w').write(result)
        if not self.no_secure and 'password=' in cmd:
            cmds = cmd.split()
            cmds2 = []
            for cmd2 in cmds:
                if not 'password=' in cmd2:
                    cmds2.append(cmd2)
                else:
                    cmds2.append(cmd2.split('=')[0] + '=' + '******')
            cmd = ' '.join(cmds2)

        self.hd.set(str(start_value), [cmd, success])

    def read_more(self, num=None, need_print=True, full_info=True):
        '''
        need_print will indicate whether print the command result to screen.

        full_info will indicate whether return command and params information
            when return command results.
        '''
        start_value = self.hd.get(self.start_key)
        last_value = self.hd.get(self.last_key)
        more_usage_list = [text_doc.bold('Usage:'), text_doc.bold('\t%smore NUM\t #show the No. NUM Command result' % prompt), text_doc.bold('\t%smore\t\t #show all available NUM and Command. The failure command will be marked with "!" before it.' % prompt)]

        more_usage = '\n'.join(more_usage_list)

        if not start_value:
            print 'No command history to display.'
            return

        if num:
            if num.isdigit():
                if int(num) > CLI_MAX_CMD_HISTORY:
                    print 'Not find result for number: %s' % num
                    print 'Max number is: %s ' % str(CLI_MAX_RESULT_HISTORY)
                    cprint(more_usage, attrs=['bold'], end='\n')
                    return

                key = start_value - int(num) + 1
                if key <= 0:
                    key += CLI_MAX_RESULT_HISTORY

                #print key
                result_list = self.hd.get(str(key))

                result_file = '%s%d' % (CLI_RESSULT_FILE, key)
                result = open(result_file, 'r').read()

                if result_list:
                    output = 'Command: \n\t%s\nResult:\n%s' % \
                            (result_list[0], result)
                    if need_print:
                        pydoc.pager(output)

                    if full_info:
                        return [result_list[0], output]
                    else:
                        return [result_list[0], result]
        else:
            more_list = []
            explamation = text_doc.bold('!')
            if start_value < last_value:
                for i in range(CLI_MAX_RESULT_HISTORY):
                    if start_value - i > 0:
                        key = start_value - i
                    else:
                        key = start_value - i + CLI_MAX_RESULT_HISTORY

                    cmd_result = self.hd.get(str(key))
                    cmd_result_list = cmd_result[0].split()
                    cmd = text_doc.bold(cmd_result_list[0])
                    if len(cmd_result_list) > 1:
                        cmd = cmd + ' ' + ' '.join(cmd_result_list[1:])
                    if len(cmd_result) <= 2 or cmd_result[2]:
                        more_list.append('[%s]\t %s' % (str(i + 1), cmd))
                    else:
                        more_list.append('[%s]  %s\t %s' % (str(i + 1), \
                                explamation, cmd))
            else:
                for i in range(start_value):
                    cmd_result = self.hd.get(str(start_value - i))
                    cmd_result_list = cmd_result[0].split()
                    cmd = text_doc.bold(cmd_result_list[0])
                    if len(cmd_result_list) > 1:
                        cmd = cmd + ' ' + ' '.join(cmd_result_list[1:])
                    if len(cmd_result) <= 2 or cmd_result[2]:
                        more_list.append('[%s]\t %s' % (str(i + 1), \
                                cmd))
                    else:
                        more_list.append('[%s]  %s\t %s' % (str(i + 1), \
                                explamation, cmd))

            more_result = '\n'.join(more_list)
            header = text_doc.bold('[NUM]\tCOMMAND')
            more_result = '%s\n%s\n%s' % (header, '-' * 48, more_result)
            more_result = '%s\n%s' % (more_result, more_usage)
            pydoc.pager(more_result)
            return

        print 'Not find result for number: %s' % num
        cprint(more_usage, attrs=['bold'], end='\n')

    def save_json_to_file(self, all_params):

        def write_to_file(output, file_name, num):
            file_name = os.path.abspath(file_name)
            open(file_name, 'w').write(output)
            print "Saved command: %s result to file: %s" % (str(num), file_name)

        if not all_params:
            self.show_help()
            return

        nums = all_params[0].split(',')
        if len(all_params) > 1:
            file_folder = all_params[1]
            if len(nums) > 1 and not os.path.isdir(file_folder):
                print "%s must be a folder, to save more than 1 command" % file_folder
                return
        else:
            file_folder = None

        if len(all_params) > 2:
            json_only = all_params[2]
        else:
            json_only = False

        for num in nums:
            return_result = self.read_more(num, False, not json_only)
            if not return_result:
                print "cannot find related command result to save"
                return

            cmd, output = return_result

            if not file_folder:
                new_file_folder = '%s-%s.json' % (cmd.split()[0], num)
            else:
                new_file_folder = file_folder

            dirname = os.path.dirname(new_file_folder)
            if not dirname:
                file_name = new_file_folder
                write_to_file(output, file_name, num)
            else:
                if os.path.isdir(new_file_folder):
                    file_name = '%s/%s-%s.json' % (new_file_folder, cmd.split()[0], num)
                elif os.path.isdir(dirname):
                    write_to_file(output, file_name, num)
                else:
                    print "Can't find folder: %s" % dirname

    def show_more(self, all_params):
        if not all_params:
            num = None
        else:
            num = all_params[0]

        self.read_more(num)

    def show_help(self, all_params):
        help_string = text_doc.bold('Usage:')
        help_string += '''
-------------------------------------------------------------------------------
  help          show help

  more [No.]    show a single or multiple command history. If a command NUM is provided, only
                history of that command will show.

                >>> more

                >>> more 1


  save [No.] [TARGET_FILE_NAME|TARGET_FOLDER]
                save a single or multiple command history to a file or a directory.

                >>> save 1
                save history command 1 result to ./COMMAND-NAME-1.json

                >>> save 1,2,3,4
                save command history 1,2,3,4 to ./COMMAND-1.json, ./COMMAND-2.json,
                ./COMMAND-3.json, and ./COMMAND-4.json

                >>> save 1 /tmp
                save command history 1 to /tmp/COMMAND-1.json

                >>> save 1 /tmp/1.json
                save command history 1 to /tmp/1.json

  ZSTACK_API [API_PARAMS]
                execute a API command like LogInByAccount, QueryHost.

                >>> LogInByAccount accountName=admin password=password

                >>> QueryHost

                If API PARAMS is a list type, use ',' to split contents.

                >>> AddVmNicToSecurityGroup \\
                        securityGroupUuid=561f792761124a9a8fa9198684eaf5f2 \\
                        vmNicUuids=f994b93fe9354fd89061ea549642c6a4,\\
                                aee96364351e470abe1cfd919ce630b8,\\
                                e0c8016595a548628523d97b70e984e8

                the parameter 'rules' of AddSecurityGroupRule is a list containing items of
                map, you need to use a JSON object in this case.

                >>> AddSecurityGroupRule \\
                        securityGroupUuid=561f792761124a9a8fa9198684eaf5f2 \\
                        rules='[{"type":"Ingress","protocol":"TCP",\\
                                "startPort":100,"endPort":1000},\\
                                {"type":"Ingress","protocol":"UDP",\\
                                "startPort":100,"endPort":1000}]'

  Query* [conditions] [Query_API_PARAMS]
                query resources with query APIs; find details at http://zdoc.readthedocs.org/en/latest/userManual/query.html.

                conditions are arranged in format of:

                    CONDITION_NAME(no space)OPERATOR(no space)VALUE

                [CONDITION_NAME] is a field name of a resource, for example, uuid, name.

                [OPERATOR] is one of: '='. '!=', '>', '<', '>=', '<=',
                '?=', '!?=', '~=', '!~='

                most operators are straightforward except follows:

                '?=": check whether a value is within a set of values; values are split by ','; this
                      operator is equal to 'in' operator in SQL.

                      >>> QueryVmInstance name?=VM1,VM2

                '!?=': check whether a value is NOT within a set of values; values are split by ',';
                       this operator is equal to 'not in' operator in SQL.

                      >>> QueryVmInstance vmNics.ip!?=192.168.0.1,192.168.0.2

                '~=': simple pattern matching; use % to match any number of characters, even zero characters; use _
                      to match exactly one character; this operator is equal to 'like' operator in SQL.

                      >>> QueryHost name~=IntelCore%

                      >>> QueryHost name~=IntelCore_7

                '!~=': negation of simple pattern matching; use % to match any number of characters, even zero
                       characters; use _ to matches exactly one character; this operator is equal to 'not like' in SQL.

                      >>> QueryHost name!~=IntelCore%

                      >>> QueryHost name!~=IntelCore_7

                '=null': NULL value test

                      >>> QueryVolume vmInstanceUuid=null

                '!=null': NOT NULL value test

                      >>> QueryVolume vmInstanceUuid!=null

                [VALUE] is a string containing value as query a condition; ',' is used to split value into a string list.
                        strings are compared as case insensitive.
'''

        help_string += text_doc.bold('ZStack API')
        help_string += '''
-------------------------------------------------------------------------------
'''

        for api in self.raw_words_db:
            help_string += '  %s\n\n' % api

        pydoc.pager(help_string)

    def __init__(self, options):
        '''
        Constructor
        '''
        readline.parse_and_bind("tab: complete")
        readline.set_completer(self.complete)
        readline.set_completion_display_matches_hook(self.completer_print)
        try:
            readline.read_history_file(CLI_HISTORY)
        except IOError:
            pass
        readline.set_history_length(CLI_MAX_CMD_HISTORY)

        if not os.path.isdir(CLI_RESULT_HISTORY_FOLDER):
            os.system('rm -rf %s' % os.path.dirname(CLI_RESULT_HISTORY_FOLDER))
            os.system('mkdir -p %s' % os.path.dirname(CLI_RESULT_HISTORY_FOLDER))

        try:
            self.hd = filedb.FileDB(CLI_RESULT_HISTORY_KEY, is_abs_path=True)
        except:
            os.system('rm -rf %s' % CLI_RESULT_HISTORY_KEY)
            self.hd = filedb.FileDB(CLI_RESULT_HISTORY_KEY, is_abs_path=True)
            print "\nRead history file: %s error. Has recreate it.\n" % CLI_RESULT_HISTORY_KEY

        self.start_key = 'start_key'
        self.last_key = 'last_key'
        self.cli_cmd_func = {'help': self.show_help, \
                'history':  self.show_help, \
                'more':     self.show_more, \
                'quit':     sys.exit, \
                'exit':     sys.exit, \
                'save':     self.save_json_to_file}
        self.cli_cmd = self.cli_cmd_func.keys()

        self.raw_words_db = self._parse_api_name(inventory.api_names)
        self.words_db = list(self.raw_words_db)
        self.words_db.extend(self.cli_cmd)
        self.words = list(self.words_db)
        self.is_cmd = False
        self.curr_pattern = None
        self.matching_words = None
        self.api_class_params = {}
        self.build_api_parameters()
        self.api = None
        self.session_uuid = None
        if os.path.exists(SESSION_FILE):
            self.session_uuid = open(SESSION_FILE, 'r').readline()

        self.hostname = options.host
        self.port = options.port
        self.no_secure = options.no_secure
        self.api = api.Api(host=self.hostname, port=self.port)

def main():
    parser = optparse.OptionParser()

    parser.add_option(
            "-H",
            "--host",
            dest="host",
            default='localhost',
            action='store',
            help="[Optional] IP address or DNS name of a ZStack management node. Default value: localhost")

    parser.add_option(
            "-p",
            "--port",
            dest="port",
            default='8080',
            action='store',
            help="[Optional] Port that the ZStack management node is listening on. Default value: 8080")

    parser.add_option(
            "-d",
            "--deploy",
            dest="deploy_config_file",
            default=None,
            action='store',
            help="[Optional] deploy a cloud from a XML file.")

    parser.add_option(
            "-t",
            "--tempate",
            dest="deploy_config_template_file",
            default=None,
            action='store',
            help="[Optional] variable template file for XML file spcified in option '-d'")

    parser.add_option(
            "-D",
            "--dump",
            dest="zstack_config_dump_file",
            default=None,
            action='store',
            help="[Optional] dump a cloud to a XML file")

    parser.add_option(
            "-P",
            "--password",
            dest="admin_password",
            default='password',
            action='store',
            help="[Optional] admin account password for dumping and recovering cloud environment. It can only be used when set -D or -d option. Default is 'password'.")

    parser.add_option(
            "-s",
            "--no-secure",
            dest="no_secure",
            default=False,
            action='store_true',
            help="[Optional] if setting -s, will save password information in command history. ")

    (options, args) = parser.parse_args()
    cmd = ' '.join(args)

    os.environ['ZSTACK_BUILT_IN_HTTP_SERVER_IP'] = options.host
    os.environ['ZSTACK_BUILT_IN_HTTP_SERVER_PORT'] = options.port

    if options.zstack_config_dump_file:
        admin_passwd = hashlib.sha512(options.admin_password).hexdigest()
        read_config.dump_zstack(options.zstack_config_dump_file, \
                admin_passwd)
    elif options.deploy_config_file:
        #deploy ZStack pre-configed environment.
        xml_config = parse_config.DeployConfig(options.deploy_config_file, \
                options.deploy_config_template_file)
        deploy_xml_obj = xml_config.get_deploy_config()
        admin_passwd = hashlib.sha512(options.admin_password).hexdigest()
        try:
            deploy_xml_obj.deployerConfig
        except:
            deploy_config.deploy_initial_database(deploy_xml_obj, admin_passwd)
        else:
            deploy_config.deploy_initial_database(deploy_xml_obj.deployerConfig\
                    , admin_passwd)

        print('Successfully deployed a cloud from: %s' % options.deploy_config_file)

    else:
        cli = Cli(options)
        cli.main(cmd)

if __name__ == '__main__':
    main()

