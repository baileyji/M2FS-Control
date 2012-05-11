import socket
GALIL_R=('localhost',40000)
DIRECTOR=('141.211.198.209',51280)#socket.gethostname(),50000)

def cg():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(GALIL_R)
    return s
    
def cd():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(DIRECTOR)
    return s