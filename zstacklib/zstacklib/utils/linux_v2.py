import socket


def check_remote_port_whether_open(remote_addr, remote_port):
    """ Check the remote port whether open

    :param remote_addr: Remote host's ip address
    :param remote_port: Remote host's tcp port
    :type remote_addr: string
    :type remote_port: int
    :return: A boolean value to decide the port whether open
    :rtype: boolean
    """

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ret = s.connect_ex((remote_addr, remote_port))

    return ret == 0
