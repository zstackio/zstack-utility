__author__ = 'frank'

import traceback, signal

def dump(sig, frame):
    message = "Signal received : dump Traceback:\n"
    message += ''.join(traceback.format_stack(frame))
    print message

def install_runtime_tracedumper():
    signal.signal(signal.SIGUSR1, dump)

def dump_stack():
    message = "Stack Traceback:\n"
    message += ''.join(traceback.format_stack())
    return message
