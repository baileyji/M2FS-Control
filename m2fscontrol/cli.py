import socket
from m2fscontrol.m2fsConfig import M2FSConfig

def conn(thing, timeout=2):
    if isinstance(thing, str):
        thing = ('localhost' if thing.lower() != 'director' else socket.gethostname(),
                 M2FSConfig.getPort(thing))

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(thing)
    if timeout is not None:
        s.settimeout(timeout)
    return s


def sr(socket, msg, show=True):
    socket.send(msg + '\n')
    s = socket.recv(1024)
    if show:
        print(s.decode('string_escape'))
    return s
