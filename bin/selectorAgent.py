#!/usr/bin/env python2.7
import sys

sys.path.append(sys.path[0] + '/../lib/')
from orientalazd import OrientalMotor
from agent import Agent
from m2fsConfig import m2fsConfig

SELECTOR_AGENT_VERSION_STRING = 'Selector Agent v1.0'

SW_RV_LIM = -100
SW_FW_LIM = 100
POSITION_TOLERANCE = 1  # in mm

def longTest(s):
    """ Return true if s can be cast as a long, false otherwise """
    try:
        long(s)
        return True
    except ValueError:
        return False


class SelectorAgent(Agent):
    """
    This control program is responsible for controlling the IFU-M selector.

    It instantiates an instance of OrientalMotor to handle commanding.

    The agent supports two simultaneous connections to allow the datalogger to
    request operating temperatures temperature.
    """

    def __init__(self):
        Agent.__init__(self, 'SelectorAgent')
        # Initialize the modbus connection to the controller
        self.connections['ifuselector'] = OrientalMotor(self.args.DEVICE)
        # Allow two connections so the datalogger agent can poll for temperature
        self.max_clients = 2
        self.command_handlers.update({
            # Get/Set the IFU selector by preset position. The move is carried by the AZD-KD controller.
            'SELECTOR': self.SELECTOR_command_handler,
            # Get/Set the step position corresponding to a preset position
            'SELECTOR_SELECTORPOS': self.SELECTORPOS_command_handler,
            # Move to a particular absolute position
            'SELECTOR_MOVE': self.MOVE_command_handler,
            # Get the driver and motor temps
            'SELECTOR_TEMP': self.TEMP_command_handler})

    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.

        Subclasses shuould override this to provide a description for the cli
        parser
        """
        return ("This is the selector agent. It takes IFU selector commands via a socket connection or CLI "
                "arguments.")

    def add_additional_cli_arguments(self):
        """
        Additional CLI arguments may be added by implementing this function.

        Arguments should be added as:
        self.cli_parser.add_argument(See ArgumentParser.add_argument for syntax)
        """
        self.cli_parser.add_argument('--device', dest='DEVICE',
                                     action='store', required=False, type=str,
                                     help='the device to control', default='/dev/ifuselector')
        self.cli_parser.add_argument('command', nargs='*',
                                     help='Agent command to execute')

    def get_version_string(self):
        """ Return a string with the version."""
        return SELECTOR_AGENT_VERSION_STRING

    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply

        Report the Key:Value pairs:
            name:cookie
            Driver: [online|Error|Offline]
            Motor:[On|Off]
            Break: [On|Off]
            Current: <current amount>
            Moving: True/False
        """
        # Name & cookie
        status_list = [(SELECTOR_AGENT_VERSION_STRING,  self.cookie)]
        driverState = 'Online'
        try:
            status = self.connections['ifuselector'].status()
            status_list.extend([
                ('Motor', 'On' if status.motorIsOn else 'Off'),
                ('Break', 'On' if status.breakEngaged else 'Off'),
                ('Moving', str(status.moving)),
                ('Current', status.current)])
        except IOError, e:
            #TODO distinguish between disconnected and other errors
            driverState = 'ERROR'
        status_list.insert(2, ('Driver', driverState))
        return status_list

    def _stowShutdown(self):
        """ Perform a stowed shutdown """
        try:
            self.connections['ifuselector'].move_to(m2fsConfig.getSelectorDefaults()['stow'])
        except IOError as e:
            pass
        except Exception:
            self.logger.error('Error during stowed shutdown', exc_info=True)

    def TEMP_command_handler(self, command):
        """
        Get the current driver and motor temperature

        Responds with the temp or UNKNOWN
        """
        if self.connections['ifuselector'].rlock.acquire(False):
            try:
                response = self.connections['ifuselector'].get_temps()
            except IOError, e:
                response = 'UNKNOWN'
            except Exception:
                self.logger.error('Error getting temps from driver', exc_info=True)
            finally:
                self.connections['ifuselector'].rlock.release()
        else:
            response = 'ERROR: Busy, try again'
        command.setReply(response)

    def SELECTOR_command_handler(self, command):
        """
        Get/Set the position of the IFU selector.

        Command is of the form
        IFU {HSB,MSB,LSB,STOW}
        response: {OK,ERROR}
        or
        IFU ?
        response: {HSB,MSB,LSB,STOW,MOVING,ERROR}

        If setting, the command instructs the selector to move to the
        requested IFU position, using the defined step position for that IFU.

        If getting, respond in the form {HSB,MSB,LSB,STOW,MOVING,ERROR, INTERMEDIATE} (position).
        position is not included in the event of an error.
        """
        if '?' in command.string:
            try:
                status = self.connections['ifuselector'].status()
            except IOError as e:
                response = str(e)
                if not response.startswith('ERROR: '):
                    response = 'ERROR: ' + response
                command.setReply(response)
                return

            if status.has_fault:
                response = 'ERROR: ' + status.error_string
            else:
                if status.moving:
                    state = 'MOVING'
                else:
                    state = 'INTERMEDIATE'
                    for name, pos in m2fsConfig.getSelectorDefaults():
                        if abs(pos-state.position) < POSITION_TOLERANCE:
                            state = name
                            break
                response = '{} ({})'.format(state, status.position)
            command.setReply(response)
        else:
            command_parts = command.string.split(' ')
            known_pos = m2fsConfig.getSelectorDefaults()
            if not len(command_parts) >= 2 or command_parts[1].lower() not in known_pos:
                self.bad_command_handler(command)
                return
            try:
                self.connections['ifuselector'].move_to(known_pos[command_parts[1].lower()])
                status = self.connections['ifuselector'].status()
                response = 'ERROR: ' + status.error_string if status.has_fault else 'OK'
            except IOError as e:
                response = str(e)
                if not response.startswith('ERROR: '):
                    response = 'ERROR: ' + response
            command.setReply(response)

    def SELECTORPOS_command_handler(self, command):
        """
        Retrieve or set the step position of a selector preset

        This command has two arguments: the preset, {HSB,MSB,LSB,STOW}; and the position or a question mark.

        The set position only affects subsequent moves.
        """
        # Vet the command
        command_parts = command.string.split(' ')
        if len(command_parts) > 2 and ('?' in command_parts[2] or longTest(command_parts[2])):
            # Extract the position name
            name = command_parts[1]
            if '?' in command.string:
                response = m2fsConfig.getSelectorDefaults().get(name.lower(),
                                                                'ERROR: Not a valid preset')
            else:
                position = command_parts[2]
                if position < SW_RV_LIM:
                    response = 'ERROR: Position below software reverse limit.'
                elif position > SW_FW_LIM:
                    response = 'ERROR: Position above software forward limit.'
                else:
                    m2fsConfig.setSelectorDefault(name.lower(), position)
                    response = 'OK'
            command.setReply(response)
        else:
            self.bad_command_handler(command)

    def MOVE_command_handler(self, command):
        """
        Command a move to a specified absolute positon

        This command has one argument: the position

        Respond with OK or ERROR: some text
        """
        command_parts = command.string.split(' ')
        # Vet the command
        if len(command_parts) > 1 and longTest(command_parts[1]):
            try:
                self.connections['ifuselector'].move_to(int(command_parts[1]))
                status = self.connections['ifuselector'].status()
                response = 'ERROR: ' + status.error_string if status.has_fault else 'OK'
            except IOError as e:
                response = str(e)
                if not response.startswith('ERROR: '):
                    response = 'ERROR: ' + response
            command.setReply(response)
        else:
            self.bad_command_handler(command)


if __name__ == '__main__':
    agent = SelectorAgent()
    agent.main()
