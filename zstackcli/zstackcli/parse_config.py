'''
@author: Frank
'''

import os
import sys
import traceback
import string

import zstacklib.utils.xmlobject as xmlobject


class TemplateError(Exception):
    '''zstack template parser exception'''


class DeployConfig(object):
    def __init__(self, deploy_config_path, deploy_tmpt_path=None):
        self.deploy_config_path = os.path.abspath(deploy_config_path)
        if deploy_tmpt_path:
            self.deploy_tmpt_path = os.path.abspath(deploy_tmpt_path)
        else:
            self.deploy_tmpt_path = None

        if not os.path.exists(deploy_config_path):
            raise TemplateError('ZStack deployment Config file:%s is not found' % self.deploy_config_path)

        if self.deploy_tmpt_path and not os.path.exists(self.deploy_tmpt_path):
            raise TemplateError('ZStack deployment Config template file:%s is not found' % self.deploy_tmpt_path)

    def _full_path(self, path):
        if path.startswith('~'):
            return os.path.expanduser(path)
        elif path.startswith('/'):
            return path
        else:
            return os.path.join(self.config_base_path, path)

    def get_xml_config(self):
        cfg_path = os.path.abspath(self.deploy_config_path)
        with open(cfg_path, 'r') as fd:
            xmlstr = fd.read()
            fd.close()
            config = xmlobject.loads(xmlstr)
            return config

    def get_deploy_config(self):
        config = self.get_xml_config()

        if self.deploy_tmpt_path:
            deploy_config = build_deploy_xmlobject_from_configure(self.deploy_config_path, self.deploy_tmpt_path)
        else:
            deploy_config = build_deploy_xmlobject_from_configure(self.deploy_config_path)
        return deploy_config

    def expose_config_variable(self):
        if self.deploy_config_template_path:
            set_env_var_from_config_template(self.deploy_config_template_path)


def _template_to_dict(template_file_path):
    def _parse(path, ret, done):
        if path in done:
            done.append(path)
            err = "recursive import detected," \
                  " {0} is cyclically referenced, resolving path is: {1}".format(path, " --> ".join(done))
            raise Exception(err)

        done.append(path)
        with open(os.path.abspath(path), 'r') as fd:
            content = fd.read()
            for l in content.split('\n'):
                l = l.strip().strip('\t\n ')
                if l == "":
                    continue

                if l.startswith('#'):
                    continue

                if l.startswith('import'):
                    _, sub_tempt = l.split(None, 1)
                    sub_tempt = sub_tempt.strip('''\t\n"' ''')
                    if sub_tempt.startswith('.'):
                        sub_tempt = os.path.join(os.path.dirname(os.path.abspath(path)), sub_tempt)

                    # allow referring to environment variable in import
                    if "$" in sub_tempt:
                        t = string.Template(sub_tempt)
                        sub_tempt = t.substitute(os.environ)

                    _parse(sub_tempt, ret, done)
                    continue

                try:
                    (key, val) = l.split('=', 1)
                except:
                    traceback.print_exc(file=sys.stdout)
                    err = "parse error for %s" % l
                    raise Exception(err)

                key = key.strip()
                val = val.strip()
                ret[key] = val

        done.remove(path)
        return ret

    ret = _parse(template_file_path, {}, [])
    flag = True

    tmp = dict(os.environ)
    tmp.update(ret)
    while flag:
        d = ret
        flag = False
        for key, val in d.iteritems():
            if "$" not in val:
                continue

            t = string.Template(val)
            try:
                val = t.substitute(tmp)
                # the val may contain still place holder that has not been resolved
                tmp[key] = val
                if "$" in val:
                    flag = True
                    continue

                ret[key] = val
            except KeyError as e:
                err = "undefined variable: {0}\ncan not parse variable: {1}," \
                      " it's most likely a wrong variable was defined in its value body." \
                      " Note, a variable is defined as 'ABC = xxx' and referenced as 'CBD = $ABC'.".format(str(e), key)
                raise Exception(err)

    return ret


def build_deploy_xmlobject_from_configure(xml_cfg_path, template_file_path=None):
    with open(xml_cfg_path, 'r') as fd:
        xmlstr = fd.read()

    if template_file_path:
        d = _template_to_dict(template_file_path)
        tmpt = string.Template(xmlstr)
        try:
            xmlstr = tmpt.substitute(d)
        except KeyError as key:
            test_fail("Did not find value definition in [template:] '%s' for [KEY:] '%s' from [config:] '%s' " % (
                template_file_path, key, xml_cfg_path))

    return xmlobject.loads(xmlstr)


def set_env_var_from_config_template(template_file_path):
    if os.path.exists(template_file_path):
        d = _template_to_dict(template_file_path)
        for key in d:
            os.environ[key] = d[key]
