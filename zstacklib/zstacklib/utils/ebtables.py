from zstacklib.utils import shell

_ebtablesUseLock = None

def get_ebtables_cmd():

    def checkEbtablesLock():
        global _ebtablesUseLock
        if shell.run("ebtables --concurrent -L > /dev/null") == 0:
            _ebtablesUseLock = True
        else:
            _ebtablesUseLock = False

    if _ebtablesUseLock is None:
        checkEbtablesLock()

    if _ebtablesUseLock:
        return "ebtables --concurrent"
    return "ebtables"
