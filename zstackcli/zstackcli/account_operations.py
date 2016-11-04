'''
'''

import apibinding.api_actions as api_actions
import apibinding.inventory as inventory
import traceback
import sys


def login_as_admin(password=inventory.INITIAL_SYSTEM_ADMIN_PASSWORD):
    login = api_actions.LogInByAccountAction()
    login.accountName = inventory.INITIAL_SYSTEM_ADMIN_NAME
    if not password:
        password = inventory.INITIAL_SYSTEM_ADMIN_PASSWORD

    login.password = password
    # login.timeout = 15000
    # since system might be hang for a while, when archive system log in 00:00:00
    # , it is better to increase timeout time to 60000 to avoid of no response
    login.timeout = 60000
    session_uuid = login.run().inventory.uuid
    return session_uuid


def logout(session_uuid):
    logout = api_actions.LogOutAction()
    logout.timeout = 15000
    logout.sessionUuid = session_uuid
    logout.run()


def execute_action_with_session(action, session_uuid):
    if session_uuid:
        action.sessionUuid = session_uuid
        evt = action.run()
    else:
        session_uuid = login_as_admin()
        try:
            action.sessionUuid = session_uuid
            evt = action.run()
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            raise e
        finally:
            logout(session_uuid)

    return evt


# To be added, depended on APIListSessionMsg
def get_account_by_session(session_uuid):
    pass
