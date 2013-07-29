#!/usr/bin/env python2.7
import sys
sys.path.append(sys.path[0]+'/../lib/')
import SelectedConnection
from agent import Agent
import time
from iorequest import *
import logging

GUIDER_AGENT_VERSION_STRING='Guider Agent v0.1'

#Maestro is confiugured in USB chained mode

FOCUS_CHANNEL='\x00'
FILTER_CHANNEL='\x01'

#NB these aren't set here. These should reflect whatever is programmed into
# the Maestro with the Pololu utility.
DEFAULT_FOCUS_POSITION=0.0
DEFAULT_FILTER_POSITION=0.0

MAX_FILTER_ROTATION=1260.0
MAX_FOC_ROTATION=90.0

FOCUS_NUDGE=3
JITTER_STOP_MOVE=1

FILTER_HOME_TIME=3.6
FOCUS_SLEW_TIME=0.8

FILTER_DEGREE_POS_FW={
    1: 19,
    2: 58,
    3: 100,
    4: 140,
    5: 180,
    6: 222}

MAX_PWIDTH=2100.0
MIN_PWIDTH=900.0

GET_POSITION='\x90{channel}'
SET_TARGET='\x84{channel}{target}'
GET_ERRORS='\xA1'
GET_MOVING='\x93'

MAESTRO_NOT_RESPONDING_STRING='Device not responding'


class GuiderSerial(SelectedConnection.SelectedSerial):
    """
    The guider connection class
    
    This is just a simple wrapper for selectedserial that removes the default
    line terminator on sent messages and whitespace remover on received messages
    """
    def _terminateMessage(self, message):
        """ Protocol is binary """
        return message

    def _cleanMessage(self, message):
        """ Protocol is binary """
        return message

class GuiderAgent(Agent):
    """ 
    This is the M2FS Guider agent. It is in charge of the guider box focus and
    filter, each of which are driver by an RC servo connected to a Pololu
    Micro Maestro Servo Controller. The general idea is that a command comes in 
    and the agent get/sets the target angle of the servo. In in the case of the 
    filter, that angle is converted from/to a filter id, based on an
    emperically determined relationship.
    
    As M2FS agents go this is very basic.
    """
    def __init__(self):
        Agent.__init__(self,'GuiderAgent')
        self.focus=0
        self.commanded_position={FOCUS_CHANNEL:None, FILTER_CHANNEL:None}
        self.connections['guider']=GuiderSerial('/dev/guider', 115200, timeout=1)
        self.command_handlers.update({
            #Get/Set the guider filter (1, 2, 3, or 4)
            'GFILTER':self.GFILTER_command_handler,
            #Get/Set the guider focus value
            'GFOCUS':self.GFOCUS_command_handler})
        self.logger.setLevel(logging.DEBUG)
    
    def get_version_string(self):
        """ Return a string with the version."""
        return GUIDER_AGENT_VERSION_STRING
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return ("This is the guider agent. It controls the guider filter "+
            "wheel & guider focus.")
    
    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pairs name:cookie, Filter:position, Focus:value,
        & ErrByte:value pairs.
        """
        filterStatus=self.getFilterPos()
        focusStatus=self.getFocusPos()
        return [(self.get_version_string(), self.cookie),
                ('Filter',filterStatus),
                ('Focus', focusStatus)]
    
    def GFOCUS_command_handler(self, command):
        """ 
        Handle geting/setting the guider focus
        
        Responds with the current value, MOVING, or ERROR if the controller is
        offline. !ERROR if the command is invalid (focus out of range 0-90)
        
        Responds OK if the requested position is within 0 - 90.
        """
        if '?' in command.string:
            command.setReply(self.getFocusPos())
        else:
            focus=command.string.partition(' ')[2]
            if not validFocusValue(focus):
                command.setReply('ERROR: Valid values are %i to 90, +, & -.'%JITTER_STOP_MOVE)
                return
            command.setReply('OK')
            self.startWorkerThread(command, 'MOVING', self.setFocusPos,
                                   args=(focus,))
    
    def setFocusPos(self, focus):
        """ 
        Translate focus to a command to the Maestro and send it
        
        Focus must be  in the range 0 - 90. Raise an Exception if there are any
        errors.
        """
        if focus=='+':
            focus=self.focus+FOCUS_NUDGE
        elif focus=='-':
            focus=self.focus-FOCUS_NUDGE
        focus=max(min(90, float(focus)), JITTER_STOP_MOVE)
        #Determine the move direction so we can nudge backwards after
        # Otherwise the motor might dance
        if focus > self.focus:
            dir=JITTER_STOP_MOVE
        elif focus < self.focus:
            dir=-JITTER_STOP_MOVE
        else:
            dir=0
        pwid=deg2pwid(focus, MAX_FOC_ROTATION)
        msg=SET_TARGET.format(channel=FOCUS_CHANNEL, target=pwid2bytes(pwid))
        #move to focus pos
        ioRequest=SendRequest(((msg,), {}) , 'guider')
        self.request_io(ioRequest)
        ioRequest.serviced.wait()
        if not ioRequest.success:
            self.logger.info("Focus move failed initial move")
            self.returnFromWorkerThread('GFOCUS', 'ERROR: ' + ioRequest.response)
            return
        self.focus=focus
        #give the move enough time
        time.sleep(FOCUS_SLEW_TIME)
        #Nudge the focus backwards so the servo doesn't dance
        focus-=dir
        pwid=deg2pwid(focus, MAX_FOC_ROTATION)
        msg=SET_TARGET.format(channel=FOCUS_CHANNEL, target=pwid2bytes(pwid))
        ioRequest=SendRequest(((msg,),{}), 'guider')
        self.request_io(ioRequest)
        ioRequest.serviced.wait()
        if not ioRequest.success:
            self.logger.debug("Focus move failed jitter correction move")
            self.returnFromWorkerThread('GFOCUS', 'ERROR: '+ ioRequest.response)
            return
        self.focus=focus
        self.returnFromWorkerThread('GFOCUS')
    
    def getFocusPos(self):
        """
        Get the focus angle from the Maestro
        """
        try:
            state=self.getChannelState(FOCUS_CHANNEL)
        except IOError:
            return 'ERROR: '+MAESTRO_NOT_RESPONDING_STRING
        if state != 'MOVING':
            state=pwid2deg(state, MAX_FOC_ROTATION)
        return str(state)
    
    def GFILTER_command_handler(self, command):
        """
        Handle geting/setting the guider filter
        
        Responds with the current filter, INTERMEDIATE, MOVING, or ERROR (if the
        controller is offline. !ERROR if the command is invalid
        
        Responds OK if the requested filter is valid.
        """
        if '?' in command.string:
            command.setReply(self.getFilterPos())
        else:
            filter=command.string.partition(' ')[2]
            if not validFilterValue(filter):
                self.bad_command_handler(command)
                return
            command.setReply('OK')
            self.startWorkerThread(command, 'MOVING', self.setFilterPos,
                                   args=(filter,))
    
    def setFilterPos(self, filter):
        """
        Translate filter to a degree position and command Maestro to target
        
        Filter must be a key in FILTER_DEGREE_POS_FW. Raise an Exception if there
        are any errors.
        """
        self.set_command_state('GFILTER', 'MOVING')
        new_filt=int(float(filter))
        #move to home
        pwid=deg2pwid(0, MAX_FILTER_ROTATION)
        msg=SET_TARGET.format(channel=FILTER_CHANNEL, target=pwid2bytes(pwid))
        ioRequest=SendRequest(((msg,), {}) , 'guider')
        self.request_io(ioRequest, description="Request move to home" )
        ioRequest.serviced.wait()
        if not ioRequest.success:
            self.logger.debug("Request move to home FAILED")
            self.returnFromWorkerThread('GFILTER', 'ERROR: ' + ioRequest.response)
            return
        #give the move enough time
        time.sleep(FILTER_HOME_TIME)
        #now move to the filter
        pwid=deg2pwid(FILTER_DEGREE_POS_FW[new_filt], MAX_FILTER_ROTATION)
        msg=SET_TARGET.format(channel=FILTER_CHANNEL, target=pwid2bytes(pwid))
        ioRequest=SendRequest(((msg,),{}), 'guider')
        self.request_io(ioRequest, description="Request move to filter")
        ioRequest.serviced.wait()
        if not ioRequest.success:
            self.logger.debug("Request move to filter FAILED")
            self.returnFromWorkerThread('GFILTER', 'ERROR: '+ ioRequest.response)
            return
        time.sleep(FILTER_HOME_TIME)
        self.returnFromWorkerThread('GFILTER')
    
    def getFilterPos(self):
        """
        Get the filter based on the angle reported by the Maestro
        
        Responds with the current filter, INTERMEDIATE, or ERROR (if the
        controller is offline.
        """
        try:
            pwid=self.getChannelState(FILTER_CHANNEL)
        except IOError:
            return 'ERROR: '+MAESTRO_NOT_RESPONDING_STRING
        if pwid == 'MOVING':
            filter=pwid
        else:
            try:
                filter=str(filterAngle2Filter(pwid2deg(pwid, MAX_FILTER_ROTATION)))
            except ValueError:
                filter='INTERMEDIATE'
        return filter
    
    def getChannelState(self, channel):
        """
        Returns MOVING or the pulse width for the specified channel.
        
        NB will always return the pullse width as written
        
        Raises IOError if any errors
        """
        guider=self.connections['guider']
        guider.sendMessageBlocking(GET_POSITION.format(channel=channel))
        bytes=guider.receiveMessageBlocking(nBytes=2)
        if len(bytes)!=2:
            msg='Did not get expected response from controller.'
            self.logger.error(msg)
            raise IOError(msg)
        return bytes2pwid(bytes)

def filterAngle2Filter(angle):
    """ 
    Convert angle to the filter ID. Raise ValueError if no matching filter
    """
    try:
        angle=int(round(angle))
        filter=[x[0] for x in FILTER_DEGREE_POS_FW.items() if x[1]==angle][0]
    except Exception:
        raise ValueError
    return filter

def deg2pwid(deg, max_rotation):
    """
    Convert an angular position to a servo pulse width.
    
    max_rotation should be a number corresponding to the servo angle at maximum
    pulse width.

    Assumes the maximum and minimum pulse widths of the servos are specified
    in the constants MAX_PWIDTH & MIN_PWIDTH.
        
    Raise ValueError if degree is not in the range 0 - max_rotation
    """
    if not (0 <= deg <= max_rotation):
        raise ValueError
    return MIN_PWIDTH + (MAX_PWIDTH-MIN_PWIDTH) * deg/max_rotation

def pwid2deg(pwid, max_rotation):
    """
    Convert a servo pulse width to an angle.
    
    max_rotation should be a number corresponding to the servo angle at maximum
    pulse width.

    Assumes the maximum and minimum pulse widths of the servos are specified
    in the constants MAX_PWIDTH & MIN_PWIDTH. 
    
    """
    return (pwid-MIN_PWIDTH)/(MAX_PWIDTH-MIN_PWIDTH) * max_rotation

def pwid2bytes(pwid):
    """
    Convert a pulse width to the two byte form needed to command the Maestro
    
    See p. 40 of maestro.pdf
    """
    target=int(round(pwid*4))
    targetH, targetL = (target&0x3f80)>>7, (target  &0x007F)
    return chr(targetL)+chr(targetH)

def bytes2pwid(bytes):
    """
    Convert the two byte position sent by the Maestro to a pulse width.
    
    bytes must be an ascii string of at least length 2. The conversion is
    performed on the first two characters. 
    
    See p. 42 of maestro.pdf
    """
    return round((ord(bytes[0])|(ord(bytes[1])<<8))/4)

def validFocusValue(focus):
    """ Return true iff focus is a valid focus position 
    Valid focus values are JITTER_STOP_MOVE to 90, +, & -
    """
    if focus in ['+', '-']:
        return True
    try:
        valid = (JITTER_STOP_MOVE <= float(focus) <=MAX_FOC_ROTATION)
    except Exception:
        valid=False
    return valid

def validFilterValue(filter):
    """ Return true iff filter is a valid filter """
    try:
        valid=int(float(filter)) in FILTER_DEGREE_POS_FW.keys()
    except ValueError:
        valid=False
    return valid


if __name__=='__main__':
    agent=GuiderAgent()
    agent.main()
