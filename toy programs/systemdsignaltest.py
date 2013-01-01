#!/usr/bin/env python2.7
import time, argparse, signal, atexit, sys, select


class Tester(object):
    def __init__(self):
        #register an exit function
        atexit.register(self.on_exit)
        #Register a terminate signal handler
        signal.signal(signal.SIGHUP, self.sighup)
        signal.signal(signal.SIGINT, self.sigint)
        signal.signal(signal.SIGTERM, self.sigterm)
        #signal.signal(signal.SIGKILL, self.sigkill)
    
    def main(self):
        while True:
            pass
    
    def sigint(self,signum, stack_frame):
        print("sigint")
        print(self,signum, stack_frame)
        exit(1)
    
    def sigterm(self,signum, stack_frame):
        print("sigterm")
        print(self,signum, stack_frame)
        exit(1)
    
    def sighup(self,signum, stack_frame):
        print("sighup")
        print(self,signum, stack_frame)
        exit(1)
    
    def sigkill(self,signum, stack_frame):
        print("sigkill")
        print(self,signum, stack_frame)
        exit(1)
    
    def on_exit(self):
        print("exiting")

if __name__=='__main__':
    agent=Tester()
    agent.main()