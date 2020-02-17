#!/usr/bin/env python2.7
import sys
sys.path.append(sys.path[0] + '/../lib/')
from orientalazd import OrientalMotor
from agent import Agent
from m2fsConfig import m2fsConfig
import time, threading
from utils import longTest
import logging

#TODO getting 'No handlers could be found for logger "orientalazd"'

#TODO deal with incessent stream of these messages to logging: with a connect that doesn't work at startup
# Feb 17 00:47:35 claym2fs selectorAgent.py[3634]: pymodbus.client.sync:ERROR: could not open port /dev/ifuselector: [Errno 2] No such file or directory: '/dev/ifuselector'
# Feb 17 00:47:35 claym2fs selectorAgent.py[3634]: pymodbus.client.sync:ERROR: could not open port /dev/ifuselector: [Errno 2] No such file or directory: '/dev/ifuselector'
# Feb 17 00:47:35 claym2fs selectorAgent.py[3634]: orientalazd:ERROR: Modbus Error: [Connection] Failed to connect[ModbusSerialClient(rtu baud[230400])]

""" Testing procedure
Disconnected USB/motor at startup -> ?
Disconnect USB during move
Disconnect USB while running
program runs w/o device
bad command
recovery from fault: resume operation on retry
detect if drive lost programming
stowed shutdown

SELECTOR_TEMP ?: Get temps
SELECTOR ?|<str>: get position, move to preset
SELECTOR_SELECTORPOS: get/set preset
SELECTOR_MOVE #: move to abs position
SELECTOR_ALARM: get/clear alarm
SELECTOR_STOP: stop
SELECTOR_AUTOBREAK: ?|ON|OFF
STATUS: get status (switches, temps, alarms, torque, break, pos err)

all commands respond with error if alarm is present

Notes:
moves do not block each other.
movement command check for sanity and starts move
start move and respond with ok or error as appropriate
The break is automatically enabled unless autobreak is set to false


TODO 
1) add a homing routine
3) ALARM names
4) do we apply the break at exit?

See photos in docs and schematic for external switch settings. 


MXE02 SOFTWARE (WINDOWS 10)
p32: Configure for mm 6.0mm lead, 10: reduction, mm, m/s^2
min step angle: 0.000600 (no electronic gearing)
(NB wrap setting is not used.)

Set software limits to initial values (p44). Position HW limits in 
about the right spot. Use teaching jog to fine tune position and 
set software limits.

Base settings:
Software over travel: deceleration stop
Pos/neg soft limits ~+-130mm
Stop current: 100%

Motor and mechanism (not default values, see screenshots in doc for all):
mech type: linear
mech lead: 6mm
gear ratio: 10
initial coord gen & wrap: manual
wrap: disable
Home seeking: 1 sensor
home operating speed: 15mm/s


operation data:
0 STOW Absolute positioning 0
1 HR Absolute -100
2 STD Absolute -10
3 LSB Absolute 100
5 PROGRAM_CHECK Absolute 13.3698

Homing procedure: 
1) Move to negative soft or hard limit (or negative of home switch really)
2) set and clear HOME bit
3) wait for moving to end / ready to assert
"""

SELECTOR_AGENT_VERSION_STRING = 'Selector Agent v1.0'


POSITION_TOLERANCE = 1  # in mm


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
            'TEMP': self.TEMP_command_handler,
            # Stop movement
            'SELECTOR_STOP': self.STOP_command_handler,
            #Get or clear (with arg "CLEAR") the current alarm, some alarms can not be cleared
            'SELECTOR_ALARM': self.ALARM_command_handler,
            #Turn on or off the automatic breaking of the stage
            'SELECTOR_AUTOBREAK': self.AUTOBREAK_command_handler,
            'SELECTOR_CALIBRATE': self.CALIBRATE_command_handler})
        self.autobreak = True  #Wheter to automatically apply the break when not moving
        self._autobreak_thread = threading.Thread(target=self._autobreak_main, name='Break when not moving')
        self._autobreak_thread.daemon = True
        self._autobreak_thread.start()
        logging.getLogger('pymodbus').setLevel('INFO')

    def _autobreak_main(self):
        while True:
            time.sleep(.5)
            if not self.autobreak:
                continue
            else:
                with self.connections['ifuselector'].rlock:
                    try:
                        if not self.connections['ifuselector'].moving:
                            self.connections['ifuselector'].turn_on_break()
                    except IOError:
                        pass

    def get_cli_help_string(self):
        """
        Return a brief help string describing the agent.

        Subclasses should override this to provide a description for the cli parser
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
                                     help='the device to control', default='/dev/ifum_selector')
        self.cli_parser.add_argument('command', nargs='*', help='Agent command to execute')

    def get_version_string(self):
        """ Return a string with the version."""
        return SELECTOR_AGENT_VERSION_STRING

    def get_status_list(self):
        """
        Return a list of two element tuples to be formatted into a status reply

        Report the Key:Value pairs:
            name:cookie
            Driver: Online|Error
            Motor:[On|Off]
            Break: [On|Off]
            Current: [<current amount>]
            Moving: [True/False]
            PError: ['microns (steps)']
        """
        # Name & cookie
        status_list = [(SELECTOR_AGENT_VERSION_STRING,  self.cookie)]
        try:
            status = self.connections['ifuselector'].status()
            status_list.extend([('Driver', 'Online'),
                                ('Motor', 'On' if status.motor_powered else 'Off'),
                                ('Break', 'On' if status.brake_on else 'Off'),
                                ('Moving', str(status.moving)),
                                ('Torque', str(status.torque)),
                                ('PError', status.position_error_str),
                                ('Alarm', 'None' if not status.has_fault else str(status.alarm.code))])
        except IOError as e:
            #TODO distinguish between disconnected and other errors
            status_list.append(('Driver', 'ERROR'))
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
                response = '{:.2f} {:.2f}'.format(*self.connections['ifuselector'].get_temps())
            except (IOError, Exception) as e:
                self.logger.error('Error getting temps from driver', exc_info=True)
                response = 'UNKNOWN'
            finally:
                self.connections['ifuselector'].rlock.release()
        else:
            response = 'ERROR: Busy, try again'
        command.setReply(response)

    def ALARM_command_handler(self, command):
        """ Get the current alarm string, clear it if argument is clear """
        if '?' in command.string:
            command.setReply(str(self.connections['ifuselector'].read_alarm(0)))
        elif 'clear' in command.string.lower():
            try:
                self.connections['ifuselector'].reset_alarm()
                command.setReply('OK')
            except IOError as e:
                response = str(e)
                response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
                command.setReply(response)

    def STOP_command_handler(self, command):
        """ Command an immediate stop to any ongoing move """
        try:
            self.connections['ifuselector'].stop()
            command.setReply('OK')
        except IOError as e:
            response = str(e)
            response = response if response.startswith('ERROR: ') else 'ERROR: ' + response
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
                    for name, pos in m2fsConfig.getSelectorDefaults().items():
                        pos = float(pos)
                        if abs(pos-status.position) < POSITION_TOLERANCE:
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
                self.connections['ifuselector'].move_to(int(known_pos[command_parts[1].lower()]))
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
                response = m2fsConfig.getSelectorDefaults().get(name.lower(), 'ERROR: Not a valid preset')
            else:
                position = int(command_parts[2])
                limits = self.connections['ifuselector'].limits
                if position < limits[0]:
                    response = 'ERROR: Position below software reverse limit.'
                elif position > limits[1]:
                    response = 'ERROR: Position above software forward limit.'
                else:
                    m2fsConfig.setSelectorDefault(name.lower(), position)
                    response = 'OK'
            command.setReply(response)
        else:
            self.bad_command_handler(command)

    def MOVE_command_handler(self, command):
        """
        Command a move to a specified absolute position

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

    def AUTOBREAK_command_handler(self, command):
        """
        Enable/Disable Autobreaking, default is on off generates heat

        This command has one argument: ?|ON|OFF

        Respond with OK or ERROR: some text
        """
        command_parts = command.string.split(' ')
        # Vet the command
        if '?' in command.string:
            command.setReply('ON' if self.autobreak else 'OFF')
        elif len(command_parts) == 2 and command_parts[1].upper() in ('ON', 'OFF'):
            self.autobreak = command_parts[1].upper() == 'ON'
            command.setReply('OK')
        else:
            self.bad_command_handler(command)

    def CALIBRATE_command_handler(self, command):
        self.connections['ifuselector'].set_remote_in('RV-POS')
        while self.connections['ifuselector'].moving:
            time.sleep(.1)
        self.connections['ifuselector'].set_remote_in('RV-POS', False)
        self.connections['ifuselector'].set_remote_in('HOME')
        self.connections['ifuselector'].set_remote_in('HOME', False)

        command.setReply(True)


        self.set_remote_in('RV-POS')
        while self.moving:
            time.sleep(.1)
        self.set_remote_in('RV-POS', False)
        self.set_remote_in('HOME')
        self.set_remote_in('HOME', False)

if __name__ == '__main__':
    agent = SelectorAgent()
    agent.main()
