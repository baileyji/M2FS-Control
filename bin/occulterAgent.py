#!/usr/bin/env python2.7
from m2fscontrol.agent import Agent
from m2fscontrol.m2fsConfig import M2FSConfig
from m2fscontrol.haydonidea import IdeaDrive
import m2fscontrol.haydonidea as haydonidea
import threading
from m2fscontrol.utils import longTest

OCCULTER_AGENT_VERSION_STRING='Occulter Agent v1.0'
OCCULTER_AGENT_VERSION_STRING_SHORT='v1.0'


#TODO fix imports make a pip package
# Feb 17 00:46:48 claym2fs systemd[1]: Stopped IFU-M STD Occulter.
# Feb 17 00:46:48 claym2fs systemd[1]: Started IFU-M STD Occulter.
# Feb 17 00:46:48 claym2fs occulterAgent.py[3656]: Traceback (most recent call last):
# Feb 17 00:46:48 claym2fs occulterAgent.py[3656]:   File "/M2FS-Control/bin/occulterAgent.py", line 6, in <module>
# Feb 17 00:46:48 claym2fs occulterAgent.py[3656]:     from haydonidea import IdeaDrive
# Feb 17 00:46:48 claym2fs occulterAgent.py[3656]:   File "/M2FS-Control/bin/../lib/haydonidea.py", line 4, in <module>
# Feb 17 00:46:48 claym2fs occulterAgent.py[3656]:     import lib.SelectedConnection as SelectedConnection
# Feb 17 00:46:48 claym2fs occulterAgent.py[3656]: ImportError: No module named lib.SelectedConnection
# Feb 17 00:46:48 claym2fs systemd[1]: ifum_occulterS.service: Main process exited, code=exited, status=1/FAILURE
# Feb 17 00:46:48 claym2fs systemd[1]: ifum_occulterS.service: Failed with result 'exit-code'.
# Feb 17 00:46:48 claym2fs systemd[1]: ifum_
# Feb 17 01:29:34 claym2fs occulterAgent.py[5884]: Traceback (most recent call last):
# Feb 17 01:29:34 claym2fs occulterAgent.py[5884]:   File "/M2FS-Control/bin/occulterAgent.py", line 9, in <module>
# Feb 17 01:29:34 claym2fs occulterAgent.py[5884]:     from lib.utils import longTest, floatTest
# Feb 17 01:29:34 claym2fs occulterAgent.py[5884]: ImportError: No module named lib.utils

""" Testing procedure
Disconnected USB/motor at startup -> ?
Disconnect USB during move
Disconnect USB while running
program runs w/o device
bad command
recovery from fault: resume operation on retry
autodetect stall (report of stall repair with error)
verify stowed shutdown
verify moves are in steps

OCC ?|# move to position, get postion calibrating as needed
    zero motor: use 'OCCRAW Z0' and OCC ?  
OCC_STEP relative move
OCC_STOP/OCC_ABORT stop movement
OCC_CALIBRATE calibrate
OCC_STALLPREVENT on|off
OCC_LIMITS ?|# # set software limits
STATUS: get_status_list (home, faults, moving, calibrated, pos_error)

Notes:
RESET: clear alarm/recover command
OCC: calibrates on move if needed
only a calibrating move blocks. rest can override a previous move
movement commands check for sanity and starts move



Verify code is integrated into repo at haydonkerk/*.idea,
"""


# AL04HIJN MSB
# AL04HJ3G LSB
# AL04HIOL HSB

#LSB max ~2.37509375
#MSB max ~ 2.3


class OcculterAgent(Agent):
    """
    This control program is responsible for controlling a singler Occulter mask.
    Three instances are run, one for each of the IFUs.

    Stall prevention has the side effect of resetting the drive if a position correction kicks in when
    a move isn't in progress (e.g. if you grab the actuator and pull)

    Low level device functionality is handled by the HaydonKerk IDEA driver. The
    proprietary code run on the drive is found in the files in ../haydonkerk/*.idea,
    one per subroutine.
    """
    def __init__(self):
        Agent.__init__(self, 'OcculterAgent')
        self.IFU = self.args.IFU
        #Initialize the occulter drive
        if not self.args.DEVICE:
            self.args.DEVICE = '/dev/ifum_occulter'+self.IFU
        self.connections['occulter'] = IdeaDrive(port=self.args.DEVICE)
        self.command_handlers.update({
            #Send the command string directly to the drive
            'OCCRAW': self.RAW_command_handler,
            #Get/Set the position of the occulter. The move is carried out closedloop by the controller
            'OCC': self.OCC_command_handler,
            #Move by a relative step amount
            'OCC_STEP': self.STEP_command_handler,
            'OCC_ABORT': self.ABORT_command_handler,
            'OCC_STOP': self.ABORT_command_handler,
            'OCC_RESET': self.RESET_command_handler,
            # Get/Set the soft limits
            'OCC_LIMITS': self.LIMIT_command_handler,
            #Calibrate the occulter
            'OCC_CALIBRATE': self.CALIBRATE_command_handler,
            'OCC_STALLPREVENT': self.STALLPREVENT_command_handler})
    
    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.
        
        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return ("This is the occulter agent. It takes occulter commands via"
                "a socket connection or via CLI arguments.")
    
    def add_additional_cli_arguments(self):
        """
        Additional CLI arguments may be added by implementing this function.
        
        Arguments should be added as:
        self.cli_parser.add_argument(See ArgumentParser.add_argument for syntax)
        """
        self.cli_parser.add_argument('--ifu', dest='IFU', action='store', required=True,
                                     type=str, help='H, S, L')
        self.cli_parser.add_argument('--device', dest='DEVICE', help='the device to control',
                                     action='store', required=False, type=str)
        self.cli_parser.add_argument('command', nargs='*', help='Agent command to execute')
    
    def get_version_string(self):
        """ Return a string with the version."""
        return OCCULTER_AGENT_VERSION_STRING

    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply
        
        Report the Key:Value pairs:
            name:cookie,
            Driver: Online| Disconnected]
            Home: True|False
            Moving: True|False
            Calibrated: True|False
            Faults: None |<faultstring> (see IdeaState.faultString)
            PError: position error string 'microns (64thsteps)'
        """
        #Name & cookie
        status_list = [(self.name+' '+OCCULTER_AGENT_VERSION_STRING_SHORT, self.cookie)]
        try:
            state = self.connections['occulter'].state()
            status_list.extend([('Driver', 'Online'),
                                ('Calibrated', str(state.calibrated)),
                                ('Moving', str(state.moving)),
                                ('Home', str(state.io.home_tripped)),
                                ('PError', state.position_error_str),
                                ('Faults', state.faultString if state.errorPresent else 'None')])
        except IOError, e:
            self.logger.warning('HK Drive failed state query: ()'.format(e))
            status_list.append(('Driver', 'Disconnected'))
        return status_list
    
    def RAW_command_handler(self, command):
        """ 
        Send a raw string to the drive and wait for a response
        
        NB the PC command can generate more than 1024 bytes of data so limit to 60
        """
        arg = command.string.partition(' ')[2].strip()[:60]
        if not arg:
            self.bad_command_handler(command)
        try:
            response = self.connections['occulter'].send_command_to_hk(arg)
            response = response.replace('\r', '\\r').replace('\n', '\\n')
            if not response:
                response = 'IDEA DRIVE GAVE NO RESPONSE'
        except IOError, e:
            response = 'ERROR: %s' % str(e)
        command.setReply(response)

    def _stowShutdown(self):
        """  Perform a stowed shutdown """
        try:
            self.connections['occulter'].move_to(int(M2FSConfig.getOcculterDefaults(self.IFU)['stow']))
        except IOError as e:
            self.logger.warning('Caught {} during stowed shutdown'.format(e))

    def OCC_command_handler(self, command):
        """
        Get/Set the occulter position. Command is of the form OCC #|?
        
        If setting, the command instructs the occulter to move to the
        requested position, closedloop.

        If getting, respond in the form # or STATE (#) where STATE is one of
        UNCALIBRATED, MOVING, ERROR.
        """
        if '?' in command.string:
            #Fetch state and return status
            try:
                state = self.connections['occulter'].state()
            except IOError as e:
                command.setReply('ERROR: %s' % str(e))
            if state.moving:
                if state.errorPresent:
                    self.logger.warning('HK reporting error while moving: ' + state.faultString)
                resp = 'MOVING ({})'
            elif self.connections['occulter'].prevented_hammerstall:
                resp = 'ERROR: Move aborted by hammerstall prevention. FC:' + state.faultString
                self.connections['occulter'].prevented_hammerstall = False
            elif state.errorPresent:
                resp = 'ERROR: ({}) FC:'+state.faultString
            elif not state.calibrated:
                resp = 'UNCALIBRATED ({})'
            else:
                resp = '{}'
            command.setReply(resp.format(state.position))
        else:
            #Vet the command
            command_parts = command.string.split(' ')
            try:
                pos = int(command_parts[1])
            except ValueError:
                self.bad_command_handler(command)
                return
            #First check to make sure the command is allowed (calibrated and not moving)
            try:
                state = self.connections['occulter'].state()
            except IOError as e:
                command.setReply('ERROR: %s' % str(e))
                return
            if state.errorPresent:
                command.setReply('ERROR: Fault Codes Present ({})'.format(state.faultString))
                return
            if not self.positionIsSane(pos):
                command.setReply('ERROR: Position outside of realistic range')
                return
            # This is permitted by the drive, allow it, won't get here as command blocks self
            # if state.moving:
            #     command.setReply('ERROR: Move in progress.')
            #     return
            command.setReply('OK')
            self.startWorkerThread(command, 'MOVING', self.occulter_mover,
                                   args=(pos, not state.calibrated),
                                   block=('OCC_STEP', 'OCC_CALIBRATE'))

    def occulter_mover(self, pos, calibrate):
        """
        Worker thread function to handle an absolute move

        pos - an absolute position or None
        calibrate - True or False

        Function performs calibration per calibrate then starts a move to pos if pos is not None
        Returns from the worker thread then there is an error, the move has successfully started,
        or when calibration is complete if  no move is required. Final state will be OK, MOVING, or ERROR
        """
        command_name = threading.currentThread().getName()
        if calibrate:
            try:
                self.connections['occulter'].calibrate()
                state = self.connections['occulter'].state()
            except RuntimeError:  # calibration failed.
                response = 'ERROR: Calibration failed ({})'.format(state.faultString)
                self.returnFromWorkerThread(command_name, finalState=response)
                return
            except IOError as e:
                response = str(e)
                response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
                self.returnFromWorkerThread(command_name, finalState=response)
                return

        if pos is None:
            self.returnFromWorkerThread(command_name)
            return

        try:
            self.connections['occulter'].move_to(pos, steps=True)
            state = self.connections['occulter'].state()
            if state.errorPresent:
                raise IOError('ERROR: Move issue ({})'.format(state.failcode))
        except IOError as e:
            response = str(e)
            response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
            self.returnFromWorkerThread(command_name, finalState=response)
            return

        self.returnFromWorkerThread(command_name)

    def positionIsSane(self, pos, relative_to=None, calibrated=True):
        """
        Report if the position is sane, that is:

        1) magnitude less than haydonidea.MAX_TRAVEL,
        2) within FW and RV soft limits
        3) within haydonidea.HARD_LIMITS.

        relativeTo may be used to check a relative move
        calibrated must be set to the calibration state of the drive to avoid an overly conservative relative check
        """
        try:
            rv_lim, fw_lim = map(int, M2FSConfig.getOcculterDefaults(self.IFU)['limits'].split(','))
        except Exception:
            self.logger.critical('Could not retrieve software limits, using hardcoded defaults', exc_info=True)
            rv_lim, fw_lim = 0,147200
        if abs(pos) > haydonidea.MAX_TRAVEL:
            return False
        if not calibrated and relative_to is not None:
            return True
        if relative_to is not None:
            pos += relative_to
        return (rv_lim <= pos <= fw_lim) and (haydonidea.HARD_LIMITS[0] <= pos <= haydonidea.HARD_LIMITS[1])

    def STALLPREVENT_command_handler(self, command):
        if '?' in command.string:
            command.setReply('ON' if self.connections['occulter'].prevent_stall else 'OFF')
        elif 'on' in command.string.lower():
            self.connections['occulter'].prevent_stall = True
            command.setReply('OK')
        elif 'off' in command.string.lower():
            self.connections['occulter'].prevent_stall = False
            command.setReply('OK')
        else:
            self.bad_command_handler(command)

    def LIMIT_command_handler(self, command):
        """
        Retrieve or set the soft limits for the occulter

        This command has one or two arguments: the lower and upper limit in steps or a question mark.

        It only affects subsequent moves
        """
        if '?' in command.string:
            response = M2FSConfig.getOcculterDefaults(self.IFU)['limits']
            command.setReply(response)
            return
        command_parts = command.string.split(' ')
        if len(command_parts) == 3 and longTest(command_parts[1]) and longTest(command_parts[2]):
            rv_lim, fw_lim = map(int, command_parts[1:3])
            M2FSConfig.setOcculterDefault(self.IFU, 'limits', '{}, {}'.format(rv_lim, fw_lim))
            command.setReply('OK')
        else:
            self.bad_command_handler(command)

    def CALIBRATE_command_handler(self, command):
        """
        Command the haydon drive to perform the calibration routine. This can cause motion
        to last for several seconds even though the command will not block.
        
        This command has no arguments
        """
        command.setReply('OK')
        self.startWorkerThread(command, 'MOVING', self.occulter_mover, args=(None, True),
                               block=('OCC', 'OCC_STEP', 'OCC_CALIBRATE'))

    def STEP_command_handler(self, command):
        """
        Command a relative, uncalibrated move a specified number of steps
        
        This command has one argument: the number of steps
        to move. The full range of travel of an occulter corresponds to about
        ? +/-? steps. Extending is in the positive direction.
        """
        command_parts = command.string.split(' ')
        #Vet the command
        if not (len(command_parts) > 1 and longTest(command_parts[1])):
            self.bad_command_handler(command)
            return
        try:
            state = self.connections['occulter'].state()
            if state.errorPresent:
                command.setReply('ERROR: Fault codes present ({})'.format(state.faultString))
                return
            d = int(command_parts[1])
            if not self.positionIsSane(d, relative_to=state.position, calibrated=state.calibrated):
                command.setReply('ERROR: Requested move outside of travel.')
                return
            self.connections['occulter'].move_to(d, relative=True)
            command.setReply('OK')
        except IOError as e:
            response = str(e)
            response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
            command.setReply(response)

    def ABORT_command_handler(self, command):
        """ Command an immediate abort of any ongoing moves """
        try:
            self.connections['occulter'].abort()
            command.setReply('OK')
        except IOError as e:
            response = str(e)
            response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
            command.setReply(response)

    def RESET_command_handler(self, command):
        """ Command the drive to reset """
        try:
            self.connections['occulter'].reset()
            command.setReply('OK')
        except IOError as e:
            response = str(e)
            response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
            command.setReply(response)

if __name__ == '__main__':
    agent = OcculterAgent()
    agent.main()
