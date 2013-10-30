#!/opt/local/bin/python2.7
import time
import argparse
import socket
import signal
import logging
import logging.handlers
import atexit
import serial
import sys
import select        
from m2fsConfig import m2fsConfig


def get_version_string():
    return 'Plate Checker Version 0.1'

def initialize_logger():
    """Configure logging"""
    #Configure the root logger
    logger=logging.getLogger()
    logger.setLevel(logging.DEBUG)
    # create formatter
    formatter = logging.Formatter('%(name)s:%(levelname)s: %(message)s')
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    # add formatter to handlers
    ch.setFormatter(formatter)
    # add handlers to logger
    logger.addHandler(ch)
    
def initialize_cli_parser():
    """Configure the command line interface"""
    #Create a command parser with the default agent commands
    helpdesc="Check uploaded platefiles for validity"
    cli_parser = argparse.ArgumentParser(description=helpdesc, add_help=True)
    cli_parser.add_argument('--version', action='version',
                            version=get_version_string())
    cli_parser.add_argument('--device', dest='DEVICE',
                            action='store', required=False, type=str,
                            help='the device to control')
    return cli_parser
    
def on_exit():
    """Prepare to exit"""
    shoe.write('DS\n')
    logging.getLogger("tetrisTester").info("exiting")

if __name__=='__main__':
    
    args=initialize_cli_parser().parse_args()
    initialize_logger()
    logger=logging.getLogger("tetrisTester")
    #register an exit function
    atexit.register(on_exit)
    #Register a terminate signal handler
    signal.signal(signal.SIGTERM, lambda signum, stack_frame: exit(1))
    signal.signal(signal.SIGINT, lambda signum, stack_frame: exit(1))

    shoe=ShoeSerial(self.args.DEVICE, 115200, self.logger, timeout=1)

    command,_,arg=args.command.partition(' ')
    
    while True:
        command,_,arg=raw_input(">").partition(' ')
        command=command.lower()
        if command in ['exit','quit']:
            break
        if command in ['?', 'help','-h','--help']:
            print "status   - Print status and config info"
            print "cycle #  - Cycle Tetris 1 # times"
            print "slit  #  - Move Tetris 1 to slit # (if valid)"
            print "stress # - Cycle Tetris 1, intentionally straining the cam glue"
            print "r        - Send any text following r directly to the shoe"
        if command == 'status':
            
    command == 'cycle'
        #cycle the slit N times
    command == 'slit'
        #go to slit N
    command == 'stress'
        #cycle with stall N times
        shoe.connect()
        n=cycles=int(arg)
        while n>0:
            shoe.write('DHA\n')
            time.sleep(32)
            shoe.write('SLA7\n')
            time.sleep(32)
            n-=1
            reportStatus(command, cycles, n)
    command =='r'
        #raw
    
    
    
        
        