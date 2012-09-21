#!/usr/bin/env python2.7
import sys, datetime, glob, shutil, argparse, atexit, signal, os
sys.path.append(sys.path[0]+'/../lib/')
import logging, logging.handlers
from plate import Plate
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
    return cli_parser

def on_exit():
    """Prepare to exit"""
    logging.getLogger("Plate Checker").info("exiting")

if __name__=='__main__':

    args=initialize_cli_parser().parse_args()
    initialize_logger()
    logger=logging.getLogger("Plate Checker")
    #register an exit function
    atexit.register(on_exit)
    #Register a terminate signal handler
    signal.signal(signal.SIGTERM, lambda signum, stack_frame: exit(1))
    signal.signal(signal.SIGINT, lambda signum, stack_frame: exit(1))

    platefile_path=m2fsConfig.getPlateDirectory()
    upload_path=m2fsConfig.getUploadDirectory()
    reject_path=m2fsConfig.getRejectDirectory()

    platefile_candidates=glob.glob(os.path.join(upload_path,'*.plt'))
    
    for file in platefile_candidates:
        try:
            Plate(file)
        except Exception as e:
            logger.info("%s has issues." % file)
            dest=reject_path
        else:
            dest=platefile_path

        filename=os.path.basename(file)
        if filename in os.listdir(dest):
            tmp=filename.partition('.')[0]
            bkupfilename=tmp[0]+datetime.utcnow().isoformat()+'.'+tmp[2]
            shutil.move(os.path.join(dest,filename),
                        os.path.join(dest,bkupfilename))
        shutil.move(file,os.path.join(dest,filename))
