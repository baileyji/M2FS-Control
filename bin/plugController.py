#!/usr/bin/env python2.7
import sys, time, threading
sys.path.append(sys.path[0]+'/../lib/')
import logging
import logging.handlers
from agent import Agent
from command import Command
from plate import Plate
from m2fsConfig import m2fsConfig

class PlateManager(threading.Thread):
    """
    Class for Managing database of plates
    
    Runs as a daemon thread, automatically maintaining
    database of plates as files are added/removed from plate directory.
    """
    def __init__(self, directory):
        import os
        try:
            os.path.isdir(directory)
        except Exception, e:
            raise e
        threading.Thread.__init__(self)
        self.daemon=True
        self.initialize_logger()
        self._plateDirectory=directory
        self._plates={}
        self.lock=threading.Lock()
        try:
            self.oldcontents=dict ([(f, None) for f in os.listdir(self._plateDirectory)])
        except OSError:
            self.oldcontents=dict()
        for file in self.oldcontents:
            new_plate=Plate(os.path.join(self._plateDirectory,file))
            self._plates[new_plate.name]=new_plate
        self.logger.info("Plates database initialized with %i plates" %
            len(self._plates))
            
    def initialize_logger(self):
        """Configure logging"""
        #create the logger
        self.logger=logging.getLogger('PlateManager')
        self.logger.setLevel(logging.DEBUG)
        # create formatter
        formatter = logging.Formatter('%(name)s:%(levelname)s: %(message)s')
        # create console handler and set level to debug
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        # add formatter to handlers
        ch.setFormatter(formatter)
        # add handlers to logger
        self.logger.addHandler(ch)
    
    def run(self):
        import os, time
        while 1:
            try:
                after = dict ([(f, None) for f in os.listdir(self._plateDirectory)])
            except OSError:
                after = dict()
            added = [f for f in after if not f in self.oldcontents]
            removed = [f for f in self.oldcontents if not f in after]
            self.oldcontents=after
            self.lock.acquire(True)
            if removed:
                removed=[os.path.join(self._plateDirectory,file) for file in removed]
                todrop=[k for k, v in self._plates.iteritems() if v.file in removed]
                for plate in todrop:
                    dropped=self._plates.pop(plate, None)
                    self.logger.info("Plate %s removed from database."%dropped.file)
            if added:
                added=[os.path.join(self._plateDirectory,file) for file in added]
                for new_plate_file in added:
                    new_plate=Plate(new_plate_file)
                    if new_plate.name in self._plates:
                        msg=("%s appears identical to %s, using former." %
                              (new_plate.file, self._plates[new_plate.name].file) +
                             "Please pick correct file and delete other.")
                        self.logger.warning(msg)
                    else:
                        self.logger.info("Plate %s added to database."%new_plate.file)
                    self._plates[new_plate.name]=new_plate
            self.lock.release()
            time.sleep(5)
    
    def getPlate(self, name):
        """ Return a plate by name, raise KeyError if no such plate"""
        self.lock.acquire(True)
        plate=self._plates[name]
        self.lock.release()
        return plate
    
    def getPlateNames(self):
        """ Return a list of all the plate names """
        self.lock.acquire(True)
        names=self._plates.keys()
        self.lock.release()
        return names
        
    def hasPlate(self, name):
        """ Return true iff plate name is in database """
        self.lock.acquire(True)
        have_plate=name in self._plates
        self.lock.release()
        return have_plate
    

class PlugController(Agent):
    def __init__(self):
        Agent.__init__(self,'PlugController')
        self.max_clients=1
        #self.agent_ports=m2fsConfig.getAgentPorts()
        
        #Watch for platefiles
        platefile_path=m2fsConfig.getPlateDirectory()
        self.plateManager=PlateManager(platefile_path)
        self.plateManager.start()
        self.active_plate=None
        self.command_handlers.update({
            'PLATELIST': self.PLATELIST_command_handler,
            'PLATE': self.PLATE_command_handler,
            'PLATESETUP': self.PLATESETUP_command_handler,
            'PLUGPOS': self.PLUGPOS_command_handler,
            'PLUGMODE': self.PLUGMODE_command_handler})
    
    def listenOn(self):
        return ('localhost', self.PORT)
    
    def get_version_string(self):
        return 'Plugging Controller Version 0.1'
    
    def PLATELIST_command_handler(self, command):
        """
        Get the list of available plates and their setups
        Must not be spaces in plate file names
        """
        plateList=self.plateManager.getPlateNames()
        command.setReply(''.join(plateList))
    
    def PLATE_command_handler(self, command):
        """
        Get/Set the current plate 
        
        If getting, return the name of the plate
        If setting return the number of setups on the plate
        """
        if '?' in command.string:
            """ Tell current plate name """
            command.setReply(self.active_plate.name)
        else:
            try:
                plate_name=command.string.partition(' ')[2]
                if not self.plateManager.hasPlate(plate_name):
                    command.setReply('!ERROR: Unknown plate.')
                else:
                    try:
                        self.active_plate=self.plateManager.getPlate(plate_name)
                        command.setReply('%s'% self.active_plate.n_setups)
                    except Exception, e:
                        command.setReply('ERROR: %s' % str(e))
            except IndexError:
                self.bad_command_handler(command)
    
    def PLATESETUP_command_handler(self, command):
        """
        Get/Set the current plate setup 
        """
        if '?' in command.string:
            command.setReply(str(self.active_plate.active_setup))
        else:
            arg=command.string.partition(' ')[2]
            if self.active_plate:
                if arg in self.active_plate.setups:
                    self.active_plate.active_setup=self.active_plate.setups[arg]
                    command.setReply('OK')
                else:
                    command.setReply('!ERROR: Invalid Setup.')
            else:
                command.setReply('!ERROR: Must select a plate prior to picking a setup.')
    
    def PLUGPOS_command_handler(self, command):
        """
        Report the current plut positions of the fibers.
            
        Unknown, holeID/star?, unplugged
        """
        command.setReply(256*'Unknown')
    
    def PLUGMODE_command_handler(self, command):
        """
        Control/Report the plugging mode.
        
        Not this does not control the FLS pickoff, the secondary calibration
        unit, the shoes. It only deals with getting the projector and imager 
        working.
        """
        if '?' in command.string:
            command.setReply(self.plugmode_status)
        else:
            arg=command.string.partition(' ')[2].upper()
            if arg == 'ON':
                try:
                    self.enter_plug_mode()
                    command.setReply('OK')
                except Exception, e:
                    command.setReply('ERROR: %s'%str(e))
            elif arg == 'OFF':
                try:
                    self.exit_plug_mode()
                    command.setReply('OK')
                except Exception, e:
                    command.setReply('ERROR: %s'%str(e))
            else:
                self.bad_command_handler(command)            
    

    def enter_plug_mode(self):
        pass
    
    def exit_plug_mode(self):
        pass
    

if __name__=='__main__':
    agent=PlugController()
    agent.main()
