#!/usr/bin/env python2.7
import sys, time, threading, os, re
sys.path.append(sys.path[0]+'/../lib/')
import logging
import logging.handlers
from agent import Agent
from plate import Plate, NullPlate
from m2fsConfig import m2fsConfig
from fnmatch import fnmatch
from glob import glob

PLUG_CONTROLLER_VERSION_STRING='Plugging Controller v0.1'
UPLOAD_CHECK_INTERVAL=5
FILE_SIZE_LIMIT_BYTES=1048576

import contextlib
@contextlib.contextmanager
def working_directory(path):
    """A context manager which changes the working directory to the given
    path, and then changes it back to its previous value on exit.
    Taken from http://code.activestate.com/recipes/576620-changedirectory-context-manager/#c3 for possible future use    
    """
    prev_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)

class PlateManager(threading.Thread):
    """
    Class for Managing database of plates
    
    Runs as a daemon thread, automatically maintaining
    database of plates. The manager check the plate upload directory every
    UPLOAD_CHECK_INTERVAL seconds for files, exclusive of dotfiles, README,
    sample.plate, symlinks, & directories. If it finds any it attempts deletion
    of those larger than 1MB or not ending in .plate (case-insensitive).
    
    Of the remaining files, it verifies that they are valid plates (e.g.
    Plate(file) does not throw an exception). Valid plates are moved to the 
    plates directory, while enforcing lowercase files names, and added to the
    plate database (I use the term loosely). Invalid plates are moved to the
    rejected directory and a file named platefile.reject is created with an
    explanation of why the plate was rejected. A plate with the same name as 
    an existing plate is considered invalid.
    """
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon=True
        self.lock=threading.Lock()
        self.initialize_logger()
        self._plates={}
        self._plateDir=m2fsConfig.getPlateDir()
        self._rejectDir=m2fsConfig.getPlateRejectDir()
        self._uploadDir=m2fsConfig.getPlateUploadDir()
        #Load all of the existing platefiles as filenames
        for file in glob(self._plateDir+'*.plate'):
            self._plates[os.basename(file)]=file
        self.logger.info("Plates database initialized with %i plates" %
            len(self._plates))
    
    def initialize_logger(self):
        """ Configure logging"""
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
        """
        Main loop for the plate manager thread
        
        Run forever, monitoring the upload directory for files, when found
        (Barring the readme or sample plate) they are:
        1) If ending in .plate and <1MB, checked for validity and and moved to
        either the plate repository or the rejected plates directory. Valid 
        plates are also added to the database of known plates.
        2) If not ending in .plate or >1MB they are deleted.
        """
        while True:
            #Get list of files in upload directory
            try:
                #Get list of all non dotfiles, non symlink files in upload dir
                # not having name in EXCLUDE_FILES. Search any subdirectories
                os.chdir(self._uploadDir)
                files=os.listdir('.')
                files=filter(files, lambda x: not (fnmatch(n, '.*') or
                                                   fnmatch(n, 'README') or
                                                   fnmatch(n, 'sample.plate') or
                                                   os.path.isdir(x) or
                                                   os.path.islink(x)))
            except OSError:
                files=[]
            #Filter on size, type and functionality
            rejectFiles=[]
            trashFiles=[]
            goodFiles=[]
            for fname in files:
                try:
                    if (len(fname) < 6 or
                        fname[-6].lower() != '.plate' or
                        os.path.getsize(fname) > FILE_SIZE_LIMIT_BYTES):
                        trashFiles.append(f)
                    else:
                        try:
                            #Reject if plate isn't a valid plate, or plate by
                            # same name already exists, file case is ignored
                            # for name comparison. All plates are copied
                            # in lower case
                            Plate(f)
                            if os.path.exists(self._goodDir+fname.lower()):
                                raise Exception('Plate already exists.')
                            goodFiles.append(f)
                        except Exception, e:
                            rejectFiles.append((f,e))
                except Exception:
                    trashFiles.append(f)
            #Delete all files >1MB or not ending in plate
            for f in trashFiles:
                try:
                    os.remove(f)
                except:
                    pass
            #Log and move bad files to reject directory, with reason
            for f,reason in rejectFiles:
                logger.info("%s has issue %s" % (f,str(reason)))
                try:
                    shutil.move(f, rejectDir)
                    reasonFile=file(rejectDir+fname+'.reject',"w")
                    reasonFile.write(str(reason))
                    reasonFile.close()
                except Exception, e:
                    self.logger.error('Caught while rejecting plate: %s' % str(e))
            #Log and move good files into plates directory, add to database
            for f in goodFiles:
                self.logger.info("Plate %s added to database." % f)
                try:
                    importpath=self._goodDir+f.lower()
                    shutil.move(f, importPath)
                    self.lock.acquire(True)
                    #Store plate with name as key, fully qualified path as item
                    self._plates[f.lower()[:-6]]=importPath
                except Exception, e:
                    self.logger.error('Caught while importing plate: %s' % str(e))
                finally:
                    self.lock.release()
            time.sleep(UPLOAD_CHECK_INTERVAL)
    
    def getPlate(self, name):
        """ Return a plate by name, raise KeyError if no such plate"""
        self.lock.acquire(True)
        try:
            return Plate(self._plates[name])
        except IOError:
            err='Platefile %s has gone missing.' % self._plates[name]
            self.logger.error(err)
            self._plate.pop(name)
            raise KeyError(err)
        finally:
            self.lock.release()

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
        #Start the plate manager
        self.plateManager=PlateManager()
        self.plateManager.start()
        self.active_plate=NullPlate()
        self.command_handlers.update({
            #Return a list of all known plates
            'PLATELIST': self.PLATELIST_command_handler,
            #Get/set the current plate, setting returns number of setups
            'PLATE': self.PLATE_command_handler,
            #Get/Set the setup on the current plate
            'PLATESETUP': self.PLATESETUP_command_handler,
            #Return a list of plate hole IDs for all 256 fibers, ordered
            'PLUGPOS': self.PLUGPOS_command_handler,
            #Enter/Leave plugging mode
            'PLUGMODE': self.PLUGMODE_command_handler})
    
    def get_version_string(self):
        return PLUG_CONTROLLER_VERSION_STRING
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return "This is the M2FS Plugplate manager & plugging controller"
    
    def PLATELIST_command_handler(self, command):
        """
        Get the list of available plates and their setups
        Must not be spaces in plate file names
        """
        plateList=self.plateManager.getPlateNames()
        command.setReply(' '.join(plateList)+'\n')#append \n to force sending of empty response if no plates are found
    
    def PLATE_command_handler(self, command):
        """
        Get/Set the current plate 
        
        If getting, return the name of the plate
        If setting return the number of setups on the plate
        """
        if '?' in command.string:
            command.setReply(self.active_plate.name)
        else:
            plate_name=command.string.partition(' ')[2]
            if not plate_name:
                self.bad_command_handler(command)
            else:
                if not self.plateManager.hasPlate(plate_name):
                    command.setReply('!ERROR: Unknown plate.')
                else:
                    try:
                        self.active_plate=self.plateManager.getPlate(plate_name)
                        command.setReply(str(self.active_plate.n_setups))
                    except KeyError, e:
                        command.setReply('ERROR: %s' % str(e))
    
    def PLATESETUP_command_handler(self, command):
        """
        Get/Set the current plate setup 
        """
        if '?' in command.string:
            command.setReply(str(self.active_plate.active_setup))
        else:
            arg=command.string.partition(' ')[2]
            if self.active_plate:
                try:
                    self.active_plate.setActiveSetup(arg)
                    command.setReply('OK')
                except ValueError:
                    command.setReply('!ERROR: Invalid Setup.')
            else:
                command.setReply('!ERROR: Select a plate before picking a setup.')
    
    def PLUGPOS_command_handler(self, command):
        """
        Report the current plut positions of the fibers.
            
        UNKNOWN, UNPLUGGED, holeID/star? TODO: Decide on this with Mario
        """
        command.setReply(self.get_fiber_plug_positions())
    
    def PLUGMODE_command_handler(self, command):
        """
        Control/Report the plugging mode.
        
        Not this does not control the FLS pickoff, the secondary calibration
        unit, or the shoes. It only deals with getting the projector and imager
        working.
        """
        if '?' in command.string:
            command.setReply(self.get_plugmode_status())
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
        """
        Start the hole process of monitoring the plug position of the fibers
        
        This will involve bootstrapping a complex set of subprograms, both
        and remotely (the projector is on a different computer) which do the
        following:
            Locally the FLS imager is brought online ans processing of its video
            stream to determine the raw illumination levels of the fibers is 
            begun. from this stream of data key points must be extracted to
            synchronize which frame (actually set of frames)was being projected
            while the images (remember each captured image is actually many 
            hundred seperate frames from the imager stitched together by the
            FPGA.
            Remotely the projector begings projecting a video sequence for
            imaging. This video sequence will evolve dynamically based on the 
            outputs of the local processing. how the two communicate is not yet
            determined.
        """
        pass
    
    def exit_plug_mode(self):
        """ Finish Plugging. Consider determined positions of fibers final """
        pass

    def get_plugmode_status(self):
        """ Tell whether plugmode is on off or in some fault state """
        return 'OFF'
    
    def get_fiber_plug_positions(self):
        """ 
        Report the states of all 256 fibers
        
        Red CCD first followed by the B CCD.
        """
        return 256*'UNKNOWN '


if __name__=='__main__':
    agent=PlugController()
    agent.main()
