#!/usr/bin/env python
from Tkinter import *
import numpy as np
import socket


MCALLED=('192.168.0.177', 8888)

s=None

def send(x):
    global s
    try:
        if s is None:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(MCALLED)
            s.settimeout(1)
        s.send(x+'\n')
        return s.recv(30)
    except Exception as e:
        print str(e)
        s=None
        return 'Try Again'

master = Tk()

Label(master, text="").grid(row=1, column=0)

Label(master, text="Cmd").grid(row=0, column=1)
Label(master, text="Response").grid(row=0, column=2)

response = StringVar()
Label(master, textvariable=response).grid(row=1,column=2)

cmd = StringVar()

def on_enter(event):
    global cmd
    response.set(send(cmd.get()))
    cmd.set('')
entry = Entry(master, textvariable=cmd, width=7)
entry.grid(row=1, column=1)
entry.bind('<Return>', on_enter)

response.set('Enter Cmd')

master.wm_title("MCal LED Test")

mainloop( )



#import socket
#MCALLED=('192.168.1.177', 8888)
#s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#s.connect(MCALLED)


s.settimeout(1)
