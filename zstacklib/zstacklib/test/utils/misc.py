import functools
import os
import uuid as uid

import simplejson

import env
from zstacklib.utils import jsonobject, log
from zstacklib.utils.http import REQUEST_BODY

logger = log.get_logger(__name__)


def uuid():
    return str(uid.uuid4()).replace('-', '')


def make_a_request(body):
    # type: (dict) -> dict
    return {
        REQUEST_BODY: jsonobject.dumps(body, include_protected_attr=True)
    }


def return_jsonobject():
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            r = f(*args, **kwargs)

            if isinstance(r, tuple):
                # for tuple, always assume the first return value is the string to convert
                lst = list(r)
                lst[0] = jsonobject.loads(lst[0])
                return tuple(lst)
            elif isinstance(r, str):
                return jsonobject.loads(r)
            else:
                return r

        return inner

    return wrap


def _write_test_for_info(handlers, case_info):
    cc = case_info.split('::')
    case_name = cc[0]
    func_name = '::'.join(cc[1:])

    if handlers is not None and not isinstance(handlers, list) and not isinstance(handlers, str):
        raise ValueError('handlers of %s must be a non-empty list or a non-empty string' % func_name)

    if not handlers:
        # empty means just skip test for dry-run
        logger.warn('%s has empty handler' % case_info)
        return

    output_dir = os.path.abspath(env.TEST_FOR_OUTPUT_DIR)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)

    file_path = os.path.join(output_dir, '%s.json' % os.path.basename(case_name).split('.')[0])

    if os.path.isfile(file_path):
        with open(file_path, 'r') as fd:
            data = jsonobject.loads(fd.read())
    else:
        data = jsonobject.from_dict({})

    data.case_path = case_name
    if data.test_for is None:
        data.test_for = []

    data.test_for.append({
        'func': func_name,
        'handlers': handlers if isinstance(handlers, list) else [handlers]
    })

    with open(file_path, 'w+') as fd:
        fd.write(jsonobject.dumps(data))
        logger.debug('write test_for into to: %s' % file_path)


def test_for(handlers):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            if env.DRY_RUN:
                _write_test_for_info(handlers, os.environ.get('PYTEST_CURRENT_TEST'))
            else:
                return f(*args, **kwargs)

        return inner

    return wrap


