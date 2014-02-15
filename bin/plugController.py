#!/usr/bin/env python2.7
import sys, time, threading, os, re
sys.path.append(sys.path[0]+'/../lib/')
import logging
import logging.handlers
from agent import Agent
import plate
from m2fsConfig import m2fsConfig
from fnmatch import fnmatch
from glob import glob
import shutil


MAX_ID_STRING_LEN=26 #Based on christop and what the fits header can handle
PLUG_CONTROLLER_VERSION_STRING='Plugging Controller v0.1'
UPLOAD_CHECK_INTERVAL=5
FILE_SIZE_LIMIT_BYTES=1048576

PLATEMANAGER_LOG_LEVEL=logging.DEBUG

CATERGORIZE_UPLOAD_WARNING='Exception while procesing uploads {file}: {err}'

import contextlib
@contextlib.contextmanager
def working_directory(path):
    """
    A context manager which changes the working directory to the given
    path, and then changes it back to its previous value on exit.
    Taken from http://code.activestate.com/recipes/576620-changedirectory-context-manager/#c3
    
    NB This isn't used, but I might try to learn more about it
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
        """
        Initialize the plate manager thread
        """
        threading.Thread.__init__(self)
        self.daemon=True
        self.lock=threading.Lock()
        self.logger=logging.getLogger('PlateManager')
        self.logger.setLevel(PLATEMANAGER_LOG_LEVEL)
        self._plates={}
        self._plateDir=os.getcwd()+os.sep+m2fsConfig.getPlateDir()
        self._rejectDir=os.getcwd()+os.sep+m2fsConfig.getPlateRejectDir()
        self._uploadDir=os.getcwd()+os.sep+m2fsConfig.getPlateUploadDir()
        #Load all of the existing platefiles as filenames
        for file in glob(self._plateDir+'*.plate'):
            name=os.path.splitext(os.path.basename(file))[0]
            self._plates[name]=file
        self.logger.info("Plate database initialized with %i plates" %
            len(self._plates))
    
    def _lsUploadDir(self):
        """
        Return a list of all files in _uploadDir that we care to process
        
        This list includes all files EXCEPT: dotfiles, symlinks, README,
        and sample.plate. It does not include directories.
        """
        try:
            os.chdir(self._uploadDir)
            files=os.listdir('.')
            def filterFunc(file):
                return not (fnmatch(file, '.*') or fnmatch(file, 'README') or
                            fnmatch(file, 'sample.plate') or
                            os.path.isdir(file) or os.path.islink(file))
            files=filter(filterFunc, files)
            return files
        except OSError:
            files=[]

    def _catergorizeUploads(self, files):
        """
        Divide files into three groups good files, trash files, & reject files
        
        Returns a dict with keys 'good', 'trash', & 'reject'
        Values are (possibly empty) lists of:
        good: file names
        trash: file names
        reject: two element tuples containing ( file name, rejection exception)
        
        Files are trash if they are do not end in .plate (ignoring case), 
        do not have a name, or are larger than the file size limit.
        
        Files are rejects if they can not be loaded into a Plate via 
        Plate(file) or a plate already exists with the same name.
        
        Files are good if they are in neither previous category, that is, they 
        are new, valid plates.
        """
        rejectFiles=[]
        trashFiles=[]
        goodFiles=[]
        os.chdir(self._uploadDir)
        for fname in files:
            try:
                if (len(fname) < 6 or fname[-6:].lower() != '.plate' or
                    os.path.getsize(fname) > FILE_SIZE_LIMIT_BYTES):
                    trashFiles.append(fname)
                else:
                    try:
                        #Reject if plate isn't a valid plate, or plate by
                        # same name already exists, file case is ignored
                        # for name comparison. All plates are stored
                        # in lower case, so use lower for comparison
                        plate.Plate(fname)
                        if os.path.exists(self._plateDir+fname.lower()):
                            raise plate.InvalidPlate('Plate already exists.')
                        goodFiles.append(fname)
                    except plate.InvalidPlate, e:
                        rejectFiles.append((fname,e))
                    except IOError, e:
                        rejectFiles.append((fname,e))
            except Exception, e:
                import traceback
                e=traceback.format_exception_only(type(e),e)[0][0:-1]
                self.logger.warning(CATERGORIZE_UPLOAD_WARNING.format(
                                    file=fname,
                                    err=e))
                trashFiles.append(fname)
        return {'good':goodFiles,'trash':trashFiles,'reject':rejectFiles}
    
    def run(self):
        """
        Main loop for the plate manager thread
        
        Run forever, monitoring the upload directory for files, when found
        (Barring the readme or sample plate) they are:
        1) If ending in .plate and <1MB, checked for validity and and moved to
        either the plate repository or the rejected plates directory. Valid 
        plates are also added to the database of known plates.
        2) If not ending in .plate or >1MB they are deleted.
        
        TODO: add removal of directories in upload directory if we finalize
        decision not to support uploading folders on new plate files. At present
        they won't be copied, but they also won't be removed.
        """
        while True:
            #Get list of files in upload directory
            #import pdb;pdb.set_trace()
            files=self._lsUploadDir()
            #Sort the uploads by good, trash, & reject
            categorizedFiles=self._catergorizeUploads(files)
            #Delete trash files
            os.chdir(self._uploadDir)
            for f in categorizedFiles['trash']:
                try:
                    os.remove(f)
                except:
                    self.logger.warn('Faild to delete trash: %s' % f)
                    pass
            #Log and move bad files to reject directory, with reason
            for f,reason in categorizedFiles['reject']:
                self.logger.info("%s has issue %s" % (f,str(reason)))
                try:
                    if os.path.exists(self._rejectDir+f):
                        os.remove(self._rejectDir+f)
                    shutil.move(f, self._rejectDir)
                    reasonFile=file(self._rejectDir+f+'.reject',"w")
                    reasonFile.write(str(reason))
                    reasonFile.close()
                except Exception, e:
                    self.logger.error('Caught while rejecting plate: %s' % str(e))
            #Log and move good files into plates directory, add to database
            for f in categorizedFiles['good']:
                try:
                    importPath=self._plateDir+f.lower()
                    shutil.move(f, importPath)
                    try:
                        self.lock.acquire(True)
                        #Store plate with name as key, fully qualified path as item
                        self._plates[f.lower()[:-6]]=importPath
                        self.logger.info("Plate %s added to database." % f)
                    except Exception, e:
                        raise e
                    finally:
                        self.lock.release()
                except Exception, e:
                    self.logger.error('Caught while importing plate: %s' % str(e))
            time.sleep(UPLOAD_CHECK_INTERVAL)
    
    def getPlate(self, name):
        """ Return a plate by name, raise KeyError if no such plate"""
        self.lock.acquire(True)
        try:
            return plate.Plate(self._plates[name])
        except IOError:
            import os.path
            err=('Platefile %s has gone missing from the disk.' %
                 os.path.basename(self._plates[name]))
            self.logger.error(err)
            self._plates.pop(name)
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
    """
    This is the M2FS plugging controller, at present, it doesn't do much because
    the slugging subsystem is nowhere near finished.
    
    It is responsible for the instruments awareness of the fiber positions and 
    plug plates. This is accomplished by requiring that the observer upload
    new plates to the instrument (via a samba share or, perhaps in the future, a
    web interface) and pick the plate and setup they are observing via the 
    instrument GUI. It combines this information with the plugging feedback 
    system to generate determine where fibers are plugged and to which targets
    they map.
    """
    def __init__(self):
        Agent.__init__(self,'PlugController')
        #Start the plate manager
        self.plateManager=PlateManager()
        self.plateManager.start()
        self.active_plate=plate.Plate(None)
        self.active_setup=self.active_plate.getSetup(None)
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
        """ Return the version string """
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
        Reply with a space delimited list of available plates and their setups.
        Spaces in plate names are escaped with _
        
        The list of available plates is maintained by the plate manager.
        """
        plateList=self.plateManager.getPlateNames()
        plateList=[ plate.replace(' ', '_') for plate in plateList]
        #\n is required to force sending of empty response if needed
        command.setReply(' '.join(plateList)+'\n')
    
    def PLATE_command_handler(self, command):
        """
        Get/Set the current plate 
        
        If getting, return the name of the currently selected plate
        If setting return the names of setups on the plate
        An invalid platename returns an !ERROR
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
                        setupList=self.active_plate.listSetups()
                        self.active_setup=self.active_plate.getSetup(setupList[0])
                        setups="'"+"' '".join(setupList)+"'"
                        command.setReply(setups)
                    except KeyError, e:
                        command.setReply('ERROR: %s' % str(e))
    
    def PLATESETUP_command_handler(self, command):
        """
        Get/Set the current plate setup 
        """
        if '?' in command.string:
            command.setReply(self.active_setup.name)
        else:
            arg=command.string.partition(' ')[2]
            if self.active_plate.name != plate.Plate(None).name:
                try:
                    self.active_setup=self.active_plate.getSetup(arg)
                    command.setReply('OK')
                except KeyError:
                    command.setReply('!ERROR: Invalid Setup.')
            else:
                command.setReply('!ERROR: Select a plate before picking a setup.')
    
    def PLUGPOS_command_handler(self, command):
        """
        Report the current plug positions of the fibers.
            
        Response consists of a space delimited list of 256 items, UNKNOWN,
        UNPLUGGED, or a HoleUUID
        """
        side=command.string.partition(' ')[2]
        if side !='R' and side != 'B':
            self.bad_command_handler(command)
        else:
            command.setReply(self.get_fiber_plug_positions(side))
    
    def PLUGMODE_command_handler(self, command):
        """
        Start/Stop determination of fiber plug positions.
        
        Not this does not control the FLS pickoff, the secondary calibration
        unit, or the shoes. It only deals with getting the projector and imager
        working. The director is responsible for notifying the Galils to insert
        the FLS pickof mirrors and ensuring they complete sucessfully before 
        telling us to begin plugging. Similarly, the GUI is responsible for 
        telling the calibration unit to insert and telling the instrument to 
        cancel if it fails. 
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
        raise Exception('Not implemented')
    
    def exit_plug_mode(self):
        """ Finish Plugging. Consider determined positions of fibers final """
        pass

    def get_plugmode_status(self):
        """ Tell whether plugmode is on off or in some fault state """
        return 'OFF'
    
    def get_fiber_plug_positions(self, side):
        """ 
        Report the states of the 128 fibers connected to side 'R' or 'B'
        
        Response consists of a space delimited list of 128 items, UNKNOWN,
        Tetris#:Groove#:[UNPLUGGED,HoleUUID, UNKNOWN]:[FiberID, UNKNOWN]
        fiberID is unknown if the show is unplugged
        
        Red CCD first followed by the B CCD.
        """
        #For now return the expected plug positions
        nom=self.active_setup.get_nominal_fiber_hole_dict()
        nomstate=['{0}:{1}:{2}'.format(tetris, groove,
                   nom.get(fiberID_by_tetris_groove_side(tetris, groove, side),
                           'unplugged')[0:MAX_ID_STRING_LEN])
                   for tetris in range(1,9) for groove in range(1,17) ]
        return ' '.join(nomstate)

#        fiberStates=['{0}:{1}:{2}'.format(tetris, groove,
#                        holeID_by_tetris_groove_side(tetris, groove, side))
#                        for tetris in range(1,9) for groove in range(1,17) ]
#        return ' '.join(fiberStates)

def fiberID_by_tetris_groove_side(tetris, groove, side):
    """
    Return the fiberID (e.g. R-04-15) based on the tetris, groove, & side
    If shoes aren't swapped the mapping is direct, if shoes are, it is 
    flipped.
    Side must be R or B
    """
    if side != 'R' and side !='B':
        raise ValueError('Side must be R or B')
    fiberColor=m2fsConfig.getShoeColorInCradle(side)
    if not fiberColor:
        fiberColor='UNKNOWN'
    return '{0}{1:01}-{2:02}'.format(fiberColor,tetris, groove)

def holeID_by_tetris_groove_side(tetris, groove, side):
    """
    Return [UNKNOWN, UNPLUGGED, <HoleUUID>] for specified fiber.
    
    Fiber is specified by tetris - a number from 1-8, fiber - a number 1 - 
    16, and side, the side of the spectrograph. For instance, a return value
    of <holeUUID> to tetris 1, groove 15, side 'R', indicates that 
    <holeUUID> will illuminate the R side CCD via the fiber in tetris 1
    groove 15. The color of the shoe is not relevant to this determination.
    """
    return 'UNKNOWN'

if __name__=='__main__':
    agent=PlugController()
    agent.main()
