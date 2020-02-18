import socket
from m2fscontrol.m2fsConfig import M2FSConfig

def conn(thing, timeout=None):
    if isinstance(thing, str):
        thing = ('localhost' if thing.lower() != 'director' else socket.gethostname(),
                 M2FSConfig.getPort(thing))

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(thing)
    if timeout is not None:
        s.settimeout(timeout)
    return s


def sr(socket, msg):
    socket.send(msg + '\n')
    return socket.recv(1024)