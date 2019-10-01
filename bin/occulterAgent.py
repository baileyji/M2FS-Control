#!/usr/bin/env python2.7
import sys
sys.path.append(sys.path[0]+'/../lib/')
from agent import Agent
from m2fsConfig import m2fsConfig
from haydonidea import IdeaDrive
import haydonidea
import threading

OCCULTER_AGENT_VERSION_STRING='Occulter Agent v1.0'
OCCULTER_AGENT_VERSION_STRING_SHORT='v1.0'


# AL04HIJN MSB
# AL04HJ3G LSB
# AL04HIOL HSB

#TODO add soft limits of 2.3" for stepping and other commands, decide re inclusion here vs haydon
#LSB max ~2.37509375
#MSB max ~ 2.3

def longTest(s):
    """ Return true if s can be cast as a long, false otherwise """
    try:
        long(s)
        return True
    except ValueError:
        return False


def floatTest(s):
    """ Return true if s can be cast as a long, false otherwise """
    try:
        float(s)
        return True
    except ValueError:
        return False


class OcculterAgent(Agent):
    """
    This control program is responsible for controlling a singler Occulter mask.
    Three instances are run, one for each of the IFUs.
    
    Low level device functionality is handled by the HaydonKerk IDEA driver. The
    proprietary code run on the drive is found in the files in ../haydonkerk/*.idea,
    one per subroutine. (TODO place files!)
    """
    def __init__(self):
        Agent.__init__(self, 'OcculterAgent')
        self.IFU = self.args.IFU
        #Initialize the occulter drive
        if not self.args.DEVICE:
            self.args.DEVICE = '/dev/occulter'+self.IFU
        self.connections['occulter'] = IdeaDrive(port=self.args.DEVICE)
        self.command_handlers.update({
            #Send the command string directly to the drive
            'OCCRAW': self.RAW_command_handler,
            #Get/Set the position of the occulter. The move is carried out closedloop by the controller
            'OCC': self.OCC_command_handler,
            #Move by a relative step amount
            'OCC_STEP': self.OCC_STEP_command_handler,
            'OCC_ABORT': self.OCC_ABORT_command_handler,
            'OCC_STOP': self.OCC_ABORT_command_handler,
            #Calibrate the occulter
            'OCC_CALIBRATE': self.OCC_CALIBRATE_command_handler})
    
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
                                     type=str, help='H, M, L')
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
            Drivers:[Powered| Off]
            On: string of tetri numbers that are on e.g. '1 4 6' or None
            Moving: string of tetri numbers that are moving
            Calibrated: string of tetri numbers that are calibrated
        """
        #Name & cookie
        status_list = [(self.name+' '+OCCULTER_AGENT_VERSION_STRING_SHORT, self.cookie)]
        try:
            state = self.connections['occulter'].state()
            status_list.extend([('Driver', 'Online'),
                                ('Calibrated', str(state.calibrated)),
                                ('Moving', str(state.moving)),
                                ('Home', str(state.io.home_tripped)),
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
            self.connections['occulter'].move_to(m2fsConfig.getOcculterDefaults(self.IFU)['stow'])
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
            elif state.errorPresent:
                resp = 'ERROR ({}) FC:'+state.faultString
            elif not state.calibrated:
                resp = 'UNCALIBRATED ({})'
            else:
                resp = '{}'
            command.setReply(resp.format(state.position))
        else:
            #Vet the command
            command_parts = command.string.split(' ')
            try:
                pos = float(command_parts[1])
            except ValueError:
                self.bad_command_handler(command)
            #First check to make sure the command is allowed (calibrated and not moving)
            try:
                state = self.connections['occulter'].state()
            except IOError as e:
                command.setReply('ERROR: %s' % str(e))
                return
            if state.errorPresent:
                command.setReply('ERROR: Fault Codes Present ({})'.format(state.faultString))
                return
            # This is permitted by the drive, allow it, won't get here as command blocks self
            # if state.moving:
            #     command.setReply('ERROR: Move in progress.')
            #     return
            command.setReply('OK')
            self.startWorkerThread(command, 'MOVING', self.occulter_mover,
                                   args=(pos, not state.calibrated),
                                   block=('OCC', 'OCC_STEP', 'OCC_CALIBRATE'))

    def occulter_mover(self, pos, calibrate):
        """
        TODO Unfinished function
        """
        #TODO sort this out, might be the cause of the bug, might should be moved into agent
        command_name = threading.currentThread().getName()
        if calibrate:
            try:
                self.connections['occulter'].calibrate()
            except RuntimeError:  # calibration failed.
                response = 'ERROR: Calibration failed ({})'.format(self.connections['occulter'].state().faultString)
                self.returnFromWorkerThread(command_name, finalState=response)
                return
            except IOError as e:
                response = str(e)
                response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
                self.returnFromWorkerThread(command_name, finalState=response)
                return

        if pos is not None:
            try:
                self.connections['occulter'].move_to(pos)
                state = self.connections['occulter'].state()
            except IOError as e:
                response = str(e)
                response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
                self.returnFromWorkerThread(command_name, finalState=response)
                return

        resp = 'ERROR: Move issue ({})'.format(state.failcode) if state.errorPresent else ''
        self.returnFromWorkerThread(command_name, finalState=resp)

    def OCC_CALIBRATE_command_handler(self, command):
        """
        Command the haydon drive to perform the calibration routine. This can cause motion
        to last for several seconds even though the command will not block.
        
        This command has no arguments
        """
        command.setReply('OK')
        self.startWorkerThread(command, 'MOVING', self.occulter_mover, args=(None, True),
                               block=('OCC', 'OCC_STEP', 'OCC_CALIBRATE'))

    def OCC_STEP_command_handler(self, command):
        """
        Command a relative, uncalibrated move a specified number of steps
        
        This command has one argument: the number of steps
        to move. The full range of travel of an occulter corresponds to about
        ? +/-? steps. Extending is in the positive direction.
        """
        command_parts = command.string.split(' ')
        #Vet the command
        if not (len(command_parts) > 1 and floatTest(command_parts[1])):
            self.bad_command_handler(command)
            return
        try:
            state = self.connections['occulter'].state()
            if state.errorPresent:
                command.setReply('ERROR: Fault codes present ({})'.format(state.faultString))
                return
            d = float(command_parts[1])
            if state.calibrated and not (0 <= state.position+d <= haydonidea.MAX_POSITION):
                command.setReply('ERROR: Requested move outside of travel.')
                return
            elif abs(state.position) > haydonidea.MAX_POSITION:
                command.setReply('ERROR: Requested move more than maximum travel.')
                return
            self.connections['occulter'].move_to(float(command_parts[1]), relative=True)
            command.setReply('OK')
        except IOError as e:
            response = str(e)
            response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
            command.setReply(response)

    def OCC_ABORT_command_handler(self, command):
        """
        Command a relative, uncalibrated move a specified number of steps

        This command has one argument: the number of steps
        to move. The full range of travel of an occulter corresponds to about
        ? +/-? steps. Extending is in the positive direction.
        """
        command_parts = command.string.split(' ')
        # Vet the command
        try:
            self.connections['occulter'].abort()
            command.setReply('OK')
        except IOError as e:
            response = str(e)
            response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
            command.setReply(response)


if __name__ == '__main__':
    agent = OcculterAgent()
    agent.main()
