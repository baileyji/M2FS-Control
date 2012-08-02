import socket
SHOE_R=('localhost',42000)
SLITCONTROLLER=('localhost',48000)
GALIL_R=('localhost',40000)
DIRECTOR=('141.211.198.113',51280)#socket.gethostname(),50000)

def cg():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(GALIL_R)
    return s
    
def cs():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(SHOE_R)
    s.settimeout(1)
    return s

def csc():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(SLITCONTROLLER)
    s.settimeout(1)
    return s

def cd():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(DIRECTOR)
    s.settimeout(1)
    return s

def sendrec(socket,msg):
    socket.send(msg+'\n')
    return socket.recv(1024)