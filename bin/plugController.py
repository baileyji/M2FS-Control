#!/usr/bin/env python2.7
import logging.handlers
from m2fscontrol.agent import Agent
from m2fscontrol.m2fsConfig import M2FSConfig
from hole_mapper import pathconf

pathconf.ROOT = M2FSConfig.getPlateDir()

from hole_mapper import fibermap, platedata

platedata.get_platenames_for_known_fibermaps()


MAX_ID_STRING_LEN=26 #Based on christop and what the fits header can handle
PLUG_CONTROLLER_VERSION_STRING='Plugging Controller v0.2'

PLATEMANAGER_LOG_LEVEL=logging.DEBUG

class PlugController(Agent):
    """
    This is the M2FS plugging controller, at present, it doesn't do much because
    the plugging subsystem is still manual.

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
        self.map=None
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
        plateList=platedata.get_platenames_for_known_fibermaps()
        plateList=[ p.replace(' ', '_') for p in plateList]
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
            if self.map:
                command.setReply(self.map.plate)
            else:
                command.setReply('None')
        else:
            plate_name=command.string.partition(' ')[2]
            if not plate_name:
                self.bad_command_handler(command)
            else:
                fibermaps=platedata.get_fibermap_names_for_plate(plate_name)
                fibermaps.sort()
                if fibermaps:
                    command.setReply("'"+"' '".join(fibermaps)+"'")
                else:
                    command.setReply('ERROR: No fibermaps found for '
                                     '{}'.format(plate_name))

    def PLATESETUP_command_handler(self, command):
        """
        Get/Set the current plate setup
        """
        if '?' in command.string:
            if self.map:
                command.setReply(self.map.name)
            else:
                command.setReply('None')
        else:
            setup_name=command.string.partition(' ')[2]
            try:
                self.map=platedata.get_fibermap_for_setup(setup_name)
                command.setReply('OK')
            except ValueError:
                command.setReply('!ERROR: Invalid Setup.')
            except fibermap.FibermapError as e:
                command.setReply('!ERROR: {}'.format(str(e)))

    def PLUGPOS_command_handler(self, command):
        """
        Report the current plug positions of the fibers.

        Response consists of a space delimited list of 256 items, UNKNOWN,
        UNPLUGGED, or a HoleUUID
        """
        if self.map==None:
            command.setReply('!ERROR: Pick a setup first')
        else:
            side=command.string.partition(' ')[2]
            if side not in ('R','B'):
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
        nom=self.map.mapping
        nomstate=['{0}:{1}:{2}'.format(tetris, groove,
                   nom.get(fiberID_by_tetris_groove_side(tetris, groove, side),
                           'UNKNOWN')[0:MAX_ID_STRING_LEN])
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
    if side not in ('R','B'):
        raise ValueError('Side must be R or B')
    fiberColor=M2FSConfig.getShoeColorInCradle(side)
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
