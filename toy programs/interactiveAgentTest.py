import socket
HOST = 'localhost'    # The remote host
PORT=50000
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))
